"""Work a stopped API left owed, picked up when the API starts.

Every background job here is an asyncio task of the process that served the request:
analysis, read-aloud scoring, take scoring. A process that stops — quit, slept, killed, a
container restarted — takes its tasks with it, and what they had claimed stays claimed
with nothing left to finish it: a turn at `analyzing`, an attempt or a take at `scoring`.
A desktop app is stopped like that far more often than a container is.

**Before the API serves anything, the claims are released.** A claim belongs to a job of
a running API process. `make analyze` and `make rollup` run inside the API's own
container and the desktop app runs neither, so a claim found while the API is starting
belongs to a process that is gone. A turn at `analyzing` and an attempt at `scoring` go
back to `pending`, and so does a take whose recording was kept. A take whose recording
was not kept cannot be scored again — its bytes lived only in the task — and is closed
with the reason, as a take scored without its sounds is.

**Then, behind the first request, the work.** The attempts and takes at `pending` are
scored by the runners the live paths use; one batch of the turns at `pending` is
analysed, oldest first; and every account whose progress snapshot is stale is rolled up,
last, so that it counts what the first two wrote. Scoring waits for `pron` to load its
model and analysis for the labelling model to answer, rather than running without them:
a reading scored while `pron` is loading would be closed as unscorable, and a turn
analysed while Ollama is down would be stored without its errors for good. What is still
owed when the wait runs out is owed at the next start. A `failed` turn is left to
`make analyze`: one that fails again would otherwise take the head of every batch.

Every row is claimed as the live path claims it, so a request that reaches a row first
keeps it and the runner here skips it.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from config import ANALYSIS_BATCH_SIZE, CATCHUP_POLL_S, CATCHUP_WAIT_S
from db_models import (
    Attempt,
    AudioAsset,
    PresentationSection,
    Rehearsal,
    Turn,
    User,
)
from services.analysis import analyse_turn
from services.audio import AudioPathError, resolve_path
from services.llm import LlmProvider
from services.rehearsal_scoring import score_take
from services.rollup import is_stale, rebuild_user
from services.scoring import score_attempt

log = logging.getLogger("speaklab.catchup")

INTERRUPTED = "analysis was interrupted and will be retried"
NOT_KEPT = (
    "SpeakLab stopped before this take's sounds were scored, and the recording was not "
    "kept, so they cannot be scored now."
)

# Asked whether a service can take work: "pron" once its model is loaded, "llm" once
# the labelling model answers.
Serving = Callable[[str], Awaitable[bool]]


@dataclass
class Released:
    turns: int = 0
    attempts: int = 0
    takes: int = 0
    closed: int = 0


@dataclass
class Done:
    attempts: int = 0
    takes: int = 0
    turns: int = 0
    snapshots: int = 0


async def release_claims(session_factory: async_sessionmaker) -> Released:
    """Put back in the queue what a process that is gone had claimed. One transaction."""
    async with session_factory() as db:
        turns = await db.execute(
            update(Turn)
            .where(Turn.analysis_status == "analyzing")
            .values(analysis_status="pending", analysis_error=INTERRUPTED)
        )
        attempts = await db.execute(
            update(Attempt)
            .where(Attempt.status == "scoring")
            .values(status="pending", error_message=None)
        )
        takes = await db.execute(
            update(Rehearsal)
            .where(
                Rehearsal.pron_status == "scoring",
                Rehearsal.audio_asset_id.is_not(None),
            )
            .values(pron_status="pending", pron_detail=None)
        )
        closed = await db.execute(
            update(Rehearsal)
            .where(
                Rehearsal.pron_status.in_(("pending", "scoring")),
                Rehearsal.audio_asset_id.is_(None),
            )
            .values(
                pron_status="scored",
                pron_detail=NOT_KEPT,
                scored_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()
    released = Released(
        turns=turns.rowcount,
        attempts=attempts.rowcount,
        takes=takes.rowcount,
        closed=closed.rowcount,
    )
    if any(vars(released).values()):
        log.info("claims released at start-up: %s", released)
    return released


async def model_serving(name: str) -> bool:
    """What the health probe says about one service. The production `Serving`."""
    from routers.health import OK, SERVING, probe_model_services

    report = (await probe_model_services()).get(name, {})
    if name == "llm":
        return report.get("status") in SERVING
    return (
        report.get("status") == OK
        and (report.get("reports") or {}).get("model_loaded") is True
    )


async def _wait_for(name: str, serving: Serving, wait_s: float, poll_s: float) -> bool:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + wait_s
    while True:
        if await serving(name):
            return True
        remaining = deadline - loop.time()
        if remaining <= 0:
            return False
        await asyncio.sleep(min(poll_s, remaining))


async def _take_input(
    take_id: int, session_factory: async_sessionmaker
) -> tuple[bytes, str] | None:
    """A kept take's recording and its section's words, or None when either is gone."""
    async with session_factory() as db:
        take = await db.get(Rehearsal, take_id)
        if take is None or take.audio_asset_id is None:
            return None
        section = await db.get(PresentationSection, take.section_id)
        asset = await db.get(AudioAsset, take.audio_asset_id)
        if section is None or asset is None:
            return None
        try:
            path = resolve_path(asset)
        except AudioPathError as exc:
            log.warning("take %s: %s", take_id, exc)
            return None
        body = section.body
    try:
        return await asyncio.to_thread(path.read_bytes), body
    except OSError as exc:
        log.warning("take %s: the recording could not be read: %s", take_id, exc)
        return None


async def _score_owed(
    session_factory: async_sessionmaker, serving: Serving, wait_s: float, poll_s: float
) -> tuple[int, int]:
    async with session_factory() as db:
        attempts = list(
            await db.scalars(
                select(Attempt.id)
                .where(Attempt.status == "pending")
                .order_by(Attempt.id)
            )
        )
        takes = list(
            await db.scalars(
                select(Rehearsal.id)
                .where(Rehearsal.pron_status == "pending")
                .order_by(Rehearsal.id)
            )
        )
    if not attempts and not takes:
        return 0, 0
    if not await _wait_for("pron", serving, wait_s, poll_s):
        log.info(
            "pron did not load its model in %.0f s; %d readings and %d takes wait for "
            "the next start",
            wait_s,
            len(attempts),
            len(takes),
        )
        return 0, 0
    for attempt_id in attempts:
        await score_attempt(attempt_id, session_factory)
    scored_takes = 0
    for take_id in takes:
        loaded = await _take_input(take_id, session_factory)
        if loaded is not None:
            await score_take(take_id, *loaded, session_factory)
            scored_takes += 1
    return len(attempts), scored_takes


async def _analyse_owed(
    session_factory: async_sessionmaker,
    provider: LlmProvider,
    serving: Serving,
    wait_s: float,
    poll_s: float,
    batch: int,
) -> int:
    async with session_factory() as db:
        owed = list(
            await db.scalars(
                select(Turn.id)
                .where(Turn.role == "user", Turn.analysis_status == "pending")
                .order_by(Turn.id)
                .limit(batch)
            )
        )
    if not owed:
        return 0
    if not await _wait_for("llm", serving, wait_s, poll_s):
        log.info(
            "the labelling model did not answer in %.0f s; %d turns wait for the next start",
            wait_s,
            len(owed),
        )
        return 0
    for turn_id in owed:
        await analyse_turn(turn_id, session_factory, provider)
    return len(owed)


async def _roll_up(session_factory: async_sessionmaker) -> int:
    written = 0
    async with session_factory() as db:
        for user_id in list(await db.scalars(select(User.id).order_by(User.id))):
            if await is_stale(db, user_id):
                written += len(await rebuild_user(db, user_id))
        await db.commit()
    return written


async def catch_up(
    session_factory: async_sessionmaker,
    provider: LlmProvider,
    serving: Serving = model_serving,
    wait_s: float = CATCHUP_WAIT_S,
    poll_s: float = CATCHUP_POLL_S,
    batch: int = ANALYSIS_BATCH_SIZE,
) -> Done:
    """Score, analyse and roll up what is owed. Never raises but for a cancellation."""
    done = Done()

    async def scoring() -> None:
        try:
            done.attempts, done.takes = await _score_owed(
                session_factory, serving, wait_s, poll_s
            )
        except Exception:  # noqa: BLE001 — a task nobody awaits; see scoring.py
            log.exception("the start-up scoring failed")

    async def analysis() -> None:
        try:
            done.turns = await _analyse_owed(
                session_factory, provider, serving, wait_s, poll_s, batch
            )
        except Exception:  # noqa: BLE001
            log.exception("the start-up analysis failed")

    await asyncio.gather(scoring(), analysis())
    try:
        done.snapshots = await _roll_up(session_factory)
    except Exception:  # noqa: BLE001
        log.exception("the start-up rollup failed")
    if any(vars(done).values()):
        log.info("owed work done at start-up: %s", done)
    return done


async def begin(
    session_factory: async_sessionmaker, provider: LlmProvider
) -> asyncio.Task | None:
    """Release the claims, then start the work behind the requests.

    Returns the task, for the lifespan to cancel at shutdown, or None when the claims could
    not be released: on a database not yet migrated, say, where there is nothing to do and
    nothing should be done.
    """
    try:
        await release_claims(session_factory)
    except Exception:  # noqa: BLE001 — never a reason for the API not to start
        log.exception("claims could not be released; nothing is caught up this start")
        return None
    return asyncio.create_task(catch_up(session_factory, provider))
