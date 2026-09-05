"""Starting, listing, reading, ending and deleting a practice session.

Five operations. The sixth — `POST /sessions/{id}/turns`, the one the product is
actually about — is in `routers/turns.py`, because it is the only endpoint in this
system that calls three services and holds a transaction across them, and burying it
under four pieces of CRUD would misrepresent how much of this milestone it is.

Every route here is scoped with `get_owned_or_404`, so a session belonging to somebody
else is **404 and never 403**. Session ids are sequential integers, which makes
`GET /sessions/41` a guess anybody can make; a 403 would confirm the guess was right.

**Where the database connection is held.** `POST /sessions` generates an opening turn,
which is a model call taking a second or more. `database.get_db` warns about exactly this
— a pooled connection held across a slow non-database step is how a pool of ten is
exhausted by four users — so the reads are committed before the model call and the writes
open a fresh transaction after it. `tests/test_sessions.py` asserts the pool is empty
while the model is working, so the property survives somebody moving a query.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import SESSION_PAGE_MAX, SESSION_PAGE_SIZE
from database import get_db
from db_models import PracticeSession, Scenario, Turn, User
from dependencies import current_user, get_owned_or_404
from models.session import SessionCreate, SessionDetail, SessionPage, SessionSummary
from models.turn import TurnOut
from services.analysis import Analyser, get_analyser, summarise
from services.audio import delete_unreferenced_assets
from services.conversation import build_messages, build_report, narrate_report
from services.llm import LlmError, LlmProvider, LlmRejected, get_provider
from services.turns import persist_reply, reply_to

router = APIRouter(prefix="/sessions", tags=["sessions"])
log = logging.getLogger("speaklab.sessions")


def _unavailable(exc: LlmError) -> HTTPException:
    """Generation failed, so there is no reply. Say so; never invent one.

    503 for both `LlmUnavailable` and `LlmRejected`, and the collapse is deliberate.
    They are genuinely different faults — nobody answered, versus the model is not
    pulled — but the difference is one only an operator can act on, and it is preserved
    where an operator looks, which is the log line and the detail string. To the person
    holding the microphone both mean the same thing: the persona cannot answer right now
    and their recording was not lost.

    This is the opposite mapping from `AsrRejected`, which becomes a 422 because there
    the rejected thing *is* the user's audio and re-recording genuinely helps.
    """
    log.warning("generation failed: %s: %s", type(exc).__name__, exc)
    detail = (
        f"The conversation model is not available: {exc}"
        if isinstance(exc, LlmRejected)
        else "The conversation model is not responding. Your recording was not lost."
    )
    return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=detail)


async def _summary_rows(db: AsyncSession, user: User, limit: int, offset: int):
    """One query for the page, counting turns in the same statement.

    A LEFT JOIN with a GROUP BY rather than a relationship and a length: `len(session.turns)`
    would load every turn of every session on the page to produce twenty integers, which
    is the N+1 that turns a history screen into a table scan somewhere around session 200.
    """
    turn_count = func.count(Turn.id).label("turn_count")
    query = (
        select(
            PracticeSession,
            Scenario.slug.label("scenario_slug"),
            Scenario.title.label("scenario_title"),
            turn_count,
        )
        .outerjoin(Scenario, PracticeSession.scenario_id == Scenario.id)
        .outerjoin(Turn, Turn.session_id == PracticeSession.id)
        .where(PracticeSession.user_id == user.id)
        .group_by(PracticeSession.id, Scenario.slug, Scenario.title)
        .order_by(PracticeSession.started_at.desc(), PracticeSession.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return (await db.execute(query)).all()


def _summary(session: PracticeSession, slug, title, turn_count: int) -> SessionSummary:
    return SessionSummary(
        id=session.id,
        scenario_slug=slug,
        scenario_title=title,
        mode=session.mode,
        status=session.status,
        started_at=session.started_at,
        ended_at=session.ended_at,
        turn_count=turn_count,
    )


@router.post("", response_model=SessionDetail, status_code=status.HTTP_201_CREATED)
async def start_session(
    body: SessionCreate,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    provider: LlmProvider = Depends(get_provider),
) -> SessionDetail:
    """Start a conversation and return the persona's opening turn.

    The opening line is generated rather than seeded, because a scenario that always
    opens with the same sentence is a scenario you have already heard. It costs a model
    call before the user has said anything, which is the one place in the product where
    latency is genuinely free: nobody is waiting mid-conversation for it.

    **Nothing is written if generation fails.** The session row is created in the same
    transaction as its first turn, so a 503 here leaves no empty session in the history —
    which would otherwise be the most common row in the table on a machine with no Ollama.
    """
    scenario = await db.scalar(
        select(Scenario).where(
            Scenario.slug == body.scenario_slug, Scenario.is_active.is_(True)
        )
    )
    if scenario is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active scenario with slug '{body.scenario_slug}'",
        )

    # Release the connection before the model call. See the module docstring.
    persona = build_messages(scenario, None, [], None)
    scenario_id, scenario_slug, scenario_title = (
        scenario.id,
        scenario.slug,
        scenario.title,
    )
    await db.commit()

    try:
        reply = await reply_to(provider, persona)
    except LlmError as exc:
        raise _unavailable(exc) from exc

    session = PracticeSession(
        user_id=user.id, scenario_id=scenario_id, mode="conversation", status="active"
    )
    db.add(session)
    await db.flush()

    turn = await persist_reply(
        db, user, session, reply, idx=0, latency_ms=reply.elapsed_ms
    )
    await db.flush()

    return SessionDetail(
        **_summary(session, scenario_slug, scenario_title, 1).model_dump(),
        turns=[TurnOut.of(turn)],
        report=None,
    )


@router.get("", response_model=SessionPage)
async def list_sessions(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(SESSION_PAGE_SIZE, ge=1, le=SESSION_PAGE_MAX),
    offset: int = Query(0, ge=0),
) -> SessionPage:
    """This user's sessions, newest first.

    `le=SESSION_PAGE_MAX` on the limit is a server-side ceiling rather than advice:
    `?limit=100000` is answered with a 422 naming the maximum, not with a query that
    reads a year of history into memory to satisfy a client that asked without thinking.
    """
    rows = await _summary_rows(db, user, limit, offset)
    total = await db.scalar(
        select(func.count(PracticeSession.id)).where(PracticeSession.user_id == user.id)
    )
    return SessionPage(
        items=[_summary(*row) for row in rows],
        total=total or 0,
        limit=limit,
        offset=offset,
    )


@router.get("/{session_id}", response_model=SessionDetail)
async def get_session(
    session_id: int,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> SessionDetail:
    """One session with its whole transcript. This is what a page reload reads."""
    session = await get_owned_or_404(db, PracticeSession, session_id, user)

    turns = list(
        (
            await db.scalars(
                select(Turn).where(Turn.session_id == session.id).order_by(Turn.idx)
            )
        ).all()
    )
    scenario = (
        await db.get(Scenario, session.scenario_id) if session.scenario_id else None
    )

    return SessionDetail(
        **_summary(
            session,
            scenario.slug if scenario else None,
            scenario.title if scenario else None,
            len(turns),
        ).model_dump(),
        turns=[TurnOut.of(turn) for turn in turns],
        report=session.report,
    )


@router.post("/{session_id}/end", response_model=SessionDetail)
async def end_session(
    session_id: int,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    provider: LlmProvider = Depends(get_provider),
    analyser: Analyser = Depends(get_analyser),
) -> SessionDetail:
    """Close the session and produce its report.

    **Idempotent.** Ending an already-ended session returns the stored report rather
    than writing a new one. Regenerating would spend a model call to produce a
    *different* narrative for a conversation that has not changed, and a report that
    reads differently every time you open it is not a record of anything.

    **Ending never depends on the model being up.** The counts in `measured` are computed
    from rows; only the prose needs Ollama, and if it is down that section says so and
    the session still closes. A session stuck in `active` because a container was
    restarting would be a worse failure than a report with a missing paragraph.
    """
    session = await get_owned_or_404(db, PracticeSession, session_id, user)

    turns = list(
        (
            await db.scalars(
                select(Turn).where(Turn.session_id == session.id).order_by(Turn.idx)
            )
        ).all()
    )
    scenario = (
        await db.get(Scenario, session.scenario_id) if session.scenario_id else None
    )

    if session.status != "active":
        # Already ended. The stored report is returned rather than regenerated — a
        # narrative that reads differently every time you open it is not a record of
        # anything — **unless** it was written before its own turns had been analysed.
        # In that case the counts are rebuilt from the rows that have since appeared and
        # the stored prose is kept, so a report cannot be permanently missing a turn
        # because a model was slow on the evening it was written.
        if _is_incomplete(session.report):
            await db.commit()
            await analyser.ensure_session(session.id)
            session.report = build_report(
                session,
                scenario,
                turns,
                (session.report or {}).get("narrative"),
                await summarise(db, session.id, scenario),
            )
            await db.flush()

        return SessionDetail(
            **_summary(
                session,
                scenario.slug if scenario else None,
                scenario.title if scenario else None,
                len(turns),
            ).model_dump(),
            turns=[TurnOut.of(turn) for turn in turns],
            report=session.report,
        )

    await db.commit()  # the narration is a model call; do not hold a connection for it

    # Analysis runs behind each turn, so the only one usually outstanding here is the
    # last thing the speaker said. It is waited for because the report is stored once:
    # written a turn early, it would be missing that turn for ever.
    await analyser.ensure_session(session.id)

    narrative = await narrate_report(provider, scenario, turns)

    session.ended_at = func.now()
    await db.flush()
    await db.refresh(session, ["ended_at"])

    session.status = "completed"
    session.report = build_report(
        session, scenario, turns, narrative, await summarise(db, session.id, scenario)
    )
    await db.flush()

    return SessionDetail(
        **_summary(
            session,
            scenario.slug if scenario else None,
            scenario.title if scenario else None,
            len(turns),
        ).model_dump(),
        turns=[TurnOut.of(turn) for turn in turns],
        report=session.report,
    )


def _is_incomplete(report: dict | None) -> bool:
    """Whether a stored report was written before its session's analysis had finished."""
    if not report:
        return False
    analysis = report.get("analysis")
    return analysis is None or not analysis.get("complete", False)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: int,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a session, its turns, and any recording left with nothing pointing at it.

    The turns go by `ON DELETE CASCADE`. The audio does not — `turns.audio_asset_id` has
    no cascade, on purpose, because an asset is content-addressed and can be shared — so
    the assets this session referenced are collected first and then deleted only if
    nothing else still refers to them.

    Rows are removed and committed before the files are unlinked. A crash between the two
    leaves a blob nothing points at, which wastes disk; the other order would leave a row
    pointing at a file that no longer exists, which is a 404 on a recording the user was
    never told had gone.
    """
    session = await get_owned_or_404(db, PracticeSession, session_id, user)

    asset_ids = {
        row
        for row in (
            await db.scalars(
                select(Turn.audio_asset_id).where(
                    Turn.session_id == session.id, Turn.audio_asset_id.isnot(None)
                )
            )
        ).all()
    }

    await db.delete(session)
    await db.flush()

    paths = await delete_unreferenced_assets(db, asset_ids)
    await db.commit()

    for path in paths:
        path.unlink(missing_ok=True)
