"""One spoken turn: audio in, transcript, persona reply, speech out, persisted. FR-7.

This is the endpoint the product is about, and the only one in the system that talks to
three services inside a single request. Almost everything unusual in it follows from
that, so it is worth reading the shape before the code.

**The request runs in three phases, and the database connection is held for only two of
them.**

    A  reads      session, scenario, history                    ~2 ms, connection held
    B  models     transcribe, generate, synthesise              ~1-2 s, NO connection
    C  writes     audio assets, both turns, digest bookkeeping  ~5 ms, connection held

`database.get_db` warned about this a milestone before there was anything to warn about:
a pooled connection held across a slow non-database step is how a pool of ten is
exhausted by four simultaneous users. Phase A therefore ends with a commit, which returns
the connection to the pool; `expire_on_commit=False` is what keeps the rows loaded in
phase A usable in phase C without a refresh.
`tests/test_turns.py::test_no_database_connection_is_held_while_the_models_work` asserts
the pool is empty during phase B, so this survives somebody adding one innocent query.

**A turn is atomic: both halves or neither.** If generation fails after the recording was
transcribed, nothing is written and the endpoint answers 503. The alternative — keeping
the user's half — leaves a conversation whose last turn is a question nobody answered,
and a retry then has to decide whether it is continuing that turn or starting a new one.
The recording is not lost in any sense that matters: the browser still holds the blob and
the same bytes produce the same asset when the turn is retried.

**A failure of the voice does not fail the turn.** ASR failing means there is nothing to
reply to; generation failing means there is no reply; but synthesis failing means there is
a perfectly good reply that cannot be spoken, and 502-ing it would be the API deciding
that no answer is better than a silent one. The turn returns 200 with `speech.status`
saying what happened, the same way `/health` reports degraded rather than dead (I6).
"""

import logging
import time

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from db_models import PracticeSession, Scenario, Turn, User
from dependencies import current_user, get_owned_or_404
from models.audio import Transcription
from models.turn import SpeechOut, TurnOut, TurnResponse, TurnTiming
from routers.sessions import _unavailable
from services.asr_client import (
    AsrProtocolError,
    AsrRejected,
    AsrUnavailable,
    transcribe,
)
from services.audio import AudioTooLarge, store_recording
from services.conversation import build_messages, select_history, summarise
from services.llm import LlmError, LlmProvider, get_provider
from services.turns import persist_reply, reply_to

router = APIRouter(prefix="/sessions", tags=["sessions"])
log = logging.getLogger("speaklab.turns")


@router.post(
    "/{session_id}/turns",
    response_model=TurnResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        409: {
            "description": "The session is not active, or a turn is already in flight."
        },
        413: {"description": "The recording is over MAX_UPLOAD_BYTES."},
        422: {
            "description": "The recording could not be decoded. Re-recording may help."
        },
        502: {"description": "A model service answered with something unparseable."},
        503: {"description": "A model service is not available. Nothing was written."},
    },
)
async def add_turn(
    session_id: int,
    file: UploadFile = File(
        ..., description="The recording. Any container ffmpeg reads."
    ),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    provider: LlmProvider = Depends(get_provider),
) -> TurnResponse:
    """Speak; be heard; be answered. FR-7."""
    started = time.perf_counter()

    # ── Phase A: reads ──────────────────────────────────────────────────────
    session = await get_owned_or_404(db, PracticeSession, session_id, user)
    if session.status != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"This session is {session.status}; it cannot take another turn.",
        )
    if session.scenario_id is None:
        # A read-aloud session has no persona to reply as. m8's `POST /attempts` is the
        # endpoint for those; answering here with a generic 404 would be a worse error
        # than saying which endpoint this session belongs to.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This session has no scenario, so it has no conversation to continue.",
        )

    scenario = await db.get(Scenario, session.scenario_id)
    history = list(
        (
            await db.scalars(
                select(Turn).where(Turn.session_id == session.id).order_by(Turn.idx)
            )
        ).all()
    )
    next_idx = max((turn.idx for turn in history), default=-1) + 1
    digest = session.context_digest
    retain_audio = user.retain_audio

    data = await file.read()

    # Everything phase C needs is now in memory. Let go of the connection: the next
    # second and a half belongs to the models, and holding a pooled connection through
    # it is what makes this endpoint the one that exhausts the pool.
    await db.commit()

    # ── Phase B: the models, with no database connection held ───────────────
    transcription = await _transcribe(data, file)
    asr_ms = transcription.latency_ms

    window = select_history(scenario, digest, history, transcription.text)
    messages = build_messages(scenario, digest, window.kept, transcription.text)

    try:
        reply = await reply_to(provider, messages)
    except LlmError as exc:
        raise _unavailable(exc) from exc

    # ── Phase C: writes, one transaction ────────────────────────────────────
    try:
        user_turn = await _persist_user_turn(
            db, user, session, data, transcription, next_idx, retain_audio
        )
        reply_turn = await persist_reply(
            db,
            user,
            session,
            reply,
            idx=next_idx + 1,
            latency_ms=round((time.perf_counter() - started) * 1000),
        )
        await db.flush()
    except IntegrityError as exc:
        # `uq_turns_session_id_idx`. Two recordings for one session arrived at once and
        # both computed the same next index. 409 rather than 500: the second one is a
        # real request that simply cannot be sequenced, and the client can retry it.
        await db.rollback()
        log.warning("turn index collision on session %s: %s", session_id, exc)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Another turn is already being recorded for this session.",
        ) from exc

    if window.should_summarise:
        # The turn first, and committed, before anything else is attempted with it.
        await db.commit()
        await _fold_digest(db, session.id, provider)

    total_ms = round((time.perf_counter() - started) * 1000)

    # Serialised once and read twice. `low_confidence` is on the envelope as well as on
    # the turn, and deriving it here a second time from `transcription.confidence` would
    # be a second copy of the comparison — which is how the envelope and the turn come to
    # disagree the day the threshold moves (Q11).
    spoken = TurnOut.of(user_turn)

    return TurnResponse(
        session_id=session.id,
        user_turn=spoken,
        reply_turn=TurnOut.of(reply_turn),
        speech=SpeechOut(
            status=reply.speech_status,
            detail=reply.speech_detail,
            voice=reply.voice,
            duration_ms=reply.duration_ms,
            sample_rate=reply.sample_rate,
            sentences=reply.sentences,
        ),
        timing=TurnTiming(
            total_ms=total_ms,
            asr_ms=asr_ms,
            generation_ms=reply.generation_ms,
            synthesis_ms=reply.synthesis_ms,
            reply_ms=reply.elapsed_ms,
            model_load_ms=reply.load_ms,
            prompt_tokens=reply.prompt_tokens,
            completion_tokens=reply.completion_tokens,
        ),
        low_confidence=spoken.low_confidence,
    )


async def _transcribe(data: bytes, file: UploadFile) -> Transcription:
    """The recogniser, with its three failure modes mapped to three different answers.

    The mapping is the point of keeping the taxonomy separate in `asr_client`:

    * `AsrRejected` is a 422 because the rejected thing is **the user's audio** and
      re-recording genuinely helps. This is the one place in the turn where a 4xx is the
      honest answer — contrast `LlmRejected`, which is this system's misconfiguration and
      becomes a 503.
    * `AsrUnavailable` is a 503: the recording is fine, the system is not.
    * `AsrProtocolError` is a 502: something answered 200 with a body this code cannot
      read, which is a version skew between two containers and must not be reported as
      either of the above.
    """
    try:
        return await transcribe(
            data, filename=file.filename or "recording", content_type=file.content_type
        )
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


async def _persist_user_turn(
    db: AsyncSession,
    user: User,
    session: PracticeSession,
    data: bytes,
    transcription: Transcription,
    idx: int,
    retain_audio: bool,
) -> Turn:
    """The speaker's half of the exchange.

    **FR-26 is honoured here, and m6 is the first milestone where it means anything.**
    `users.retain_audio` has been settable since m3 and nothing has stored a waveform
    until now. When it is off the recording is transcribed and then not kept: no file is
    written, no `audio_assets` row is created, and the turn carries the transcript, the
    word timings and the confidence — everything every later metric is computed from.
    The setting drops the audio and keeps the derived data, which is exactly what the
    requirement asks for.

    The persona's own audio is stored either way. It is synthesised speech, not the
    user's voice, and it is what `GET /sessions/{id}` needs to replay a conversation.
    """
    asset_id = None
    if retain_audio:
        try:
            asset, _ = await store_recording(
                db, user, data, transcription.source, device_hint=None
            )
        except AudioTooLarge as exc:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc)
            ) from exc
        asset_id = asset.id

    turn = Turn(
        session_id=session.id,
        idx=idx,
        role="user",
        transcript=transcription.text,
        audio_asset_id=asset_id,
        words=[word.model_dump() for word in transcription.words],
        asr_confidence=transcription.confidence,
        asr_model=transcription.model,
    )
    db.add(turn)
    return turn


async def _fold_digest(
    db: AsyncSession, session_id: int, provider: LlmProvider
) -> None:
    """Summarise the oldest turns into the running digest. FR-8.

    Runs after the turn has been committed, on the request's own session, and never
    raises. Three things are deliberate about that sentence.

    **After the commit.** The turn is already safe, so a failure here cannot take it
    down. If the fold fails the digest simply does not advance; the turns it would have
    covered are still rows, and the next turn that crosses the high-water mark tries
    again. A failure here costs a little context later. It must never cost a reply now.

    **On the request's session, not a new one.** An earlier version opened its own
    session from the module-level factory, which pointed at whatever database
    `config.DATABASE_URL` names — the *production* one, even under a test that had
    overridden `get_db`. It worked in production and was silently untestable, which is
    the worse of the two failure modes.

    **In the same three phases as the endpoint.** Read, release, summarise, re-acquire.
    The model call in the middle takes about as long as the reply did, and holding a
    pooled connection through it would undo the property the rest of this module exists
    to keep — including under the test that watches the pool.

    It is awaited rather than fired into the background, and that is a stated limitation:
    the response is a few hundred milliseconds later on roughly one turn in ten.
    `BackgroundTasks` would hide that cost from the caller and the failure from the log,
    and m9 is where the background-job machinery is actually built (Q3). Two answers to
    the same question in one codebase is worse than one answer that is honest about what
    it costs.
    """
    try:
        session = await db.get(PracticeSession, session_id)
        if session is None or session.scenario_id is None:
            return

        already = session.digest_through_idx
        turns = list(
            (
                await db.scalars(
                    select(Turn)
                    .where(
                        Turn.session_id == session_id,
                        Turn.idx > (already if already is not None else -1),
                    )
                    .order_by(Turn.idx)
                )
            ).all()
        )
        scenario = await db.get(Scenario, session.scenario_id)
        previous = session.context_digest

        # Re-select against what is now stored, so the fold covers exactly the turns
        # that have fallen out rather than everything since the last fold.
        window = select_history(scenario, previous, turns, None)
        if not window.overflow:
            return
        through = max(turn.idx for turn in window.overflow)
        overflow = list(window.overflow)

        await db.commit()  # let go before the model call

        digest = await summarise(provider, previous, overflow)

        session = await db.get(PracticeSession, session_id)
        if session is None:
            return
        session.context_digest = digest
        session.digest_through_idx = through
        await db.commit()
    except Exception as exc:  # noqa: BLE001 — see the docstring
        log.warning("digest fold failed for session %s: %s", session_id, exc)
        await db.rollback()
