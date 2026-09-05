"""Read-aloud: record a passage, get it back scored phone by phone. FR-12 … FR-16.

The second of the product's two practice modes, and the one the m0 spike was run for.
Where `POST /sessions/{id}/turns` is a conversation — a persona answers — this is a
measurement: there is a right answer, the passage text, and the question is how close the
reading came to it at the level of individual sounds.

**Two clocks, and the endpoint returns on the first one.** Transcription happens inside
the request because the `audio_assets` row cannot be written without a decoder's account
of the file; alignment happens after it, as a background job, because it needs a service
that is off by default and because FR-15 says the client polls. So `POST /attempts`
answers in about as long as a conversational turn, with a transcript and a WER already
on the row, and the phones appear underneath a moment later. `services/scoring.py` is
that job.

**Ownership runs through the session, not through a column.** `attempts` has no
`user_id` — it has `session_id`, and sessions have owners — so `get_owned_or_404` does
not apply here and `_owned_attempt` below does the join. It is one query, not a fetch
followed by a comparison, for the reason `dependencies.py` gives: the comparison is what
gets forgotten. Cross-user reads are 404, never 403, so an id cannot be probed.
"""

import logging

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import SESSION_PAGE_MAX, SESSION_PAGE_SIZE
from database import get_db
from db_models import Attempt, Passage, PhonemeScore, PracticeSession, User
from dependencies import current_user
from models.attempt import (
    AttemptDetail,
    AttemptOut,
    AttemptPage,
    PhonemeScoreOut,
    PronSummary,
)
from services.asr_client import AsrProtocolError, AsrRejected, AsrUnavailable
from services.audio import AudioTooLarge, ingest_recording
from services.scoring import Scorer, get_scorer
from services.wer import wer

router = APIRouter(prefix="/attempts", tags=["attempts"])
log = logging.getLogger("speaklab.attempts")


@router.post(
    "",
    response_model=AttemptDetail,
    status_code=status.HTTP_201_CREATED,
    responses={
        404: {"description": "No such passage, or no such session."},
        409: {
            "description": "The session is not a read-aloud session, is not active, "
            "or the account has audio retention switched off."
        },
        413: {"description": "The recording is over MAX_UPLOAD_BYTES."},
        422: {"description": "The recording could not be decoded."},
        502: {"description": "The recogniser answered with something unparseable."},
        503: {"description": "The recogniser is not available. Nothing was written."},
    },
)
async def create_attempt(
    file: UploadFile = File(
        ..., description="The reading. Any container ffmpeg reads."
    ),
    passage_slug: str = Form(..., description="Which passage was read."),
    session_id: int | None = Form(
        None, description="Join an existing read-aloud sitting. Omit to open a new one."
    ),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    scorer: Scorer = Depends(get_scorer),
) -> AttemptDetail:
    """Read a passage aloud. FR-12."""
    passage = await db.scalar(select(Passage).where(Passage.slug == passage_slug))
    if passage is None or not passage.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No passage with slug {passage_slug!r}",
        )

    # **FR-26 and FR-16 genuinely conflict here, and this is the resolution.**
    # `attempts.audio_asset_id` is NOT NULL by design — an attempt without its audio
    # cannot be rescored, and FR-16 would be a promise the schema could not keep. An
    # account with retention off has asked for the waveform not to be stored. Rather than
    # quietly keeping it anyway, or silently dropping rescoring, the endpoint refuses and
    # names the setting. A conversation still works with retention off; only read-aloud
    # needs the file to survive the request. See docs/decisions/0005 §6 and handoff Q14.
    if not user.retain_audio:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Read-aloud scoring keeps your recording so a reading can be scored "
                "again later. Your account has audio retention switched off. Turn it on "
                "in settings to practise passages, or use conversation practice, which "
                "does not store audio."
            ),
        )

    session = await _read_aloud_session(db, user, session_id)

    data = await file.read()
    try:
        asset, _, transcription = await ingest_recording(
            db,
            user,
            data,
            filename=file.filename or "reading",
            content_type=file.content_type,
        )
    except AudioTooLarge as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc)
        ) from exc
    except AsrRejected as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"The recording could not be read: {exc.detail}",
        ) from exc
    except AsrUnavailable as exc:
        log.warning("asr unavailable: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The speech recogniser is not responding. Your recording was not lost.",
        ) from exc
    except AsrProtocolError as exc:
        log.error("asr protocol skew: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The speech recogniser answered in a shape this API does not understand.",
        ) from exc

    # WER against the passage, computed here rather than in the job. It is arithmetic
    # over two strings, it needs nothing that is not already in this request, and it is
    # the number that says whether the phones below are even meaningful: a reading whose
    # WER is near 1.0 was of some other text, and per-phone GOP against the wrong words
    # is noise with decimal places.
    measured = wer(passage.body, transcription.text)

    attempt = Attempt(
        session_id=session.id,
        passage_id=passage.id,
        audio_asset_id=asset.id,
        transcript=transcription.text,
        wer=measured.rate,
        status="pending",
    )
    db.add(attempt)
    await db.flush()
    attempt_id = attempt.id

    # Committed before the job is launched. The task opens its own connection and would
    # otherwise race an uncommitted row and find nothing.
    await db.commit()
    scorer.launch(attempt_id)

    return AttemptDetail(
        **AttemptOut.of(attempt, passage=passage, phoneme_count=0).model_dump(),
        passage_body=passage.body,
        phonemes=[],
        summary=None,
        pronunciation="ok",
    )


@router.get("", response_model=AttemptPage)
async def list_attempts(
    passage_slug: str | None = Query(None, description="Only this passage's readings."),
    session_id: int | None = Query(None, description="Only this sitting's readings."),
    limit: int = Query(SESSION_PAGE_SIZE, ge=1, le=SESSION_PAGE_MAX),
    offset: int = Query(0, ge=0),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> AttemptPage:
    """This account's readings, newest first.

    Bounded on the server like `GET /sessions`: `?limit=100000` is answered with
    `SESSION_PAGE_MAX`, not with a query that reads a year of practice.

    `session_id` is what `/sessions/{id}` reads for a read-aloud sitting. It is filtered
    inside the same `owned` subquery as everything else rather than checked separately —
    an unowned id returns an empty page, not a 403, so it cannot be used to find out
    which sittings exist.
    """
    owned = select(PracticeSession.id).where(PracticeSession.user_id == user.id)
    conditions = [Attempt.session_id.in_(owned)]
    if session_id is not None:
        conditions.append(Attempt.session_id == session_id)
    if passage_slug is not None:
        conditions.append(
            Attempt.passage_id.in_(
                select(Passage.id).where(Passage.slug == passage_slug)
            )
        )

    total = await db.scalar(
        select(func.count()).select_from(Attempt).where(*conditions)
    )

    # One query for the page, joined to the passage, plus one grouped count for the
    # phones. The alternative is a `phoneme_count` per row lazily loaded, which is the
    # N+1 that turns a twenty-row history into forty-one queries.
    rows = (
        await db.execute(
            select(Attempt, Passage)
            .join(Passage, Passage.id == Attempt.passage_id)
            .where(*conditions)
            .order_by(Attempt.created_at.desc(), Attempt.id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()

    ids = [attempt.id for attempt, _ in rows]
    counts = (
        dict(
            (
                await db.execute(
                    select(PhonemeScore.attempt_id, func.count())
                    .where(PhonemeScore.attempt_id.in_(ids))
                    .group_by(PhonemeScore.attempt_id)
                )
            ).all()
        )
        if ids
        else {}
    )

    return AttemptPage(
        items=[
            AttemptOut.of(
                attempt, passage=passage, phoneme_count=counts.get(attempt.id, 0)
            )
            for attempt, passage in rows
        ],
        total=total or 0,
        limit=limit,
        offset=offset,
    )


@router.get("/{attempt_id}", response_model=AttemptDetail)
async def get_attempt(
    attempt_id: int,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> AttemptDetail:
    """One reading, with its passage and its phones. The poll target. FR-15."""
    attempt = await _owned_attempt(db, attempt_id, user)
    passage = await db.get(Passage, attempt.passage_id)

    phonemes = list(
        (
            await db.scalars(
                select(PhonemeScore)
                .where(PhonemeScore.attempt_id == attempt_id)
                .order_by(PhonemeScore.word_idx, PhonemeScore.phone_idx)
            )
        ).all()
    )

    return _detail(attempt, passage, phonemes)


@router.post("/{attempt_id}/rescore", response_model=AttemptDetail)
async def rescore(
    attempt_id: int,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    scorer: Scorer = Depends(get_scorer),
) -> AttemptDetail:
    """Run the alignment again on a stored reading. FR-16.

    The recording is still on disk — which is the whole reason `audio_asset_id` is NOT
    NULL — so this costs nothing but the model's time and asks the user for nothing. It
    is the endpoint that makes `pron` being profiled tolerable: practise now with the
    service down, start it later, rescore the readings you already have.

    An attempt already in `scoring` is left alone. Re-launching it would produce two jobs
    writing phoneme rows for one attempt, and the second one's delete-then-insert would
    race the first one's insert.
    """
    attempt = await _owned_attempt(db, attempt_id, user)
    if attempt.status == "scoring":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This reading is being scored now.",
        )

    attempt.status = "pending"
    attempt.error_message = None
    await db.commit()
    scorer.launch(attempt_id)

    passage = await db.get(Passage, attempt.passage_id)
    return _detail(attempt, passage, [])


# ── Helpers ─────────────────────────────────────────────────────────────────


async def _owned_attempt(db: AsyncSession, attempt_id: int, user: User) -> Attempt:
    """One attempt belonging to `user`, or 404.

    The join is inside the query rather than a comparison after it, for the reason
    `dependencies.get_owned_or_404` exists — it just cannot be used here, because
    `attempts` reaches its owner through `sessions` rather than through a column of its
    own. 404 rather than 403: a 403 confirms the row exists, which is the fact somebody
    incrementing ids is looking for.
    """
    attempt = await db.scalar(
        select(Attempt)
        .join(PracticeSession, PracticeSession.id == Attempt.session_id)
        .where(Attempt.id == attempt_id, PracticeSession.user_id == user.id)
    )
    if attempt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No attempt with id {attempt_id}",
        )
    return attempt


async def _read_aloud_session(
    db: AsyncSession, user: User, session_id: int | None
) -> PracticeSession:
    """The sitting this reading belongs to — the one named, or a fresh one."""
    if session_id is None:
        session = PracticeSession(
            user_id=user.id, scenario_id=None, mode="read_aloud", status="active"
        )
        db.add(session)
        await db.flush()
        return session

    session = await db.scalar(
        select(PracticeSession).where(
            PracticeSession.id == session_id, PracticeSession.user_id == user.id
        )
    )
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No session with id {session_id}",
        )
    if session.mode != "read_aloud":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That session is a conversation. Readings belong to a read-aloud session.",
        )
    if session.status != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"That session is {session.status}; it cannot take another reading.",
        )
    return session


def _detail(attempt: Attempt, passage: Passage | None, phonemes: list) -> AttemptDetail:
    """Assemble the full view, deriving what is derivable rather than storing it.

    `pronunciation` is two states, not five. The client needs to know whether there are
    phones to look at and, if not, what to say about it — and the four ways `pron` can
    decline are all the same fact from the screen's point of view. The distinction that
    matters operationally is kept where it is actionable: in the log, where
    `services/scoring.py` writes each one under its own level.
    """
    scored = [PhonemeScoreOut.model_validate(row) for row in phonemes]
    summary = _summarise(scored) if scored else None

    unavailable = not scored and attempt.error_message is not None
    return AttemptDetail(
        **AttemptOut.of(
            attempt, passage=passage, phoneme_count=len(scored)
        ).model_dump(),
        passage_body=passage.body if passage is not None else None,
        phonemes=scored,
        summary=summary,
        pronunciation="unavailable" if unavailable else "ok",
        pronunciation_detail=attempt.error_message if unavailable else None,
    )


def _summarise(phonemes: list[PhonemeScoreOut]) -> PronSummary:
    """The same four numbers `infra/pron/gop.py` computes, recomputed from stored rows.

    Recomputed rather than stored, because an aggregate in a column is a number that
    stops matching its inputs the day one of them is corrected — and because a rescore
    would otherwise have to remember to update it.
    """
    gops = sorted(row.gop for row in phonemes)
    count = len(gops)
    k = (count - 1) * 0.05
    low = int(k)
    high = min(low + 1, count - 1)
    return PronSummary(
        phones=count,
        mean_gop=round(sum(gops) / count, 4),
        median_gop=round(gops[count // 2], 4),
        percentile_5=round(gops[low] + (gops[high] - gops[low]) * (k - low), 4),
        r_composites=0,
        blank_dominated=0,
    )
