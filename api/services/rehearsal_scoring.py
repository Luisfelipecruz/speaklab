"""Scoring a take's sounds as a background job.

The same shape as the read-aloud scorer and for the same reasons — the phones need a 2 GB
service that is off by default, so a take is stored with its transcript, its alignment and
its counts first, and the sounds arrive afterwards. A take whose scorer never answers
keeps everything the recogniser produced.

**One difference, and it is the reason this is not the same module: the recording is
passed in, not read back.** A reading is fetched from disk by the job, which is possible
because `attempts.audio_asset_id` is NOT NULL and a reading is refused without audio
retention. A take is not refused: an account that keeps no recordings still gets
everything but the replay. So the bytes live in the task's closure for as long as the
scoring takes and are then gone — they are never written anywhere for an account that
asked for them not to be.

**A job never raises.** It is a task nobody awaits, so every failure becomes a state on
the row with a reason on it, which is the only kind of failure a person can be told about.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from db_models import Rehearsal, RehearsalPhone
from models.attempt import PronScoring
from services.pron_client import (
    PronMisconfigured,
    PronProtocolError,
    PronRejected,
    PronUnavailable,
)
from services.pron_client import score as pron_score

log = logging.getLogger("speaklab.rehearsal_scoring")

# Held for their lifetime: `asyncio.create_task` returns a reference the loop does not
# own, and a dropped one can be collected mid-await — a job that silently never finished.
_running: set[asyncio.Task] = set()


class RehearsalScorer:
    """Launches scoring jobs for takes. The seam the tests replace."""

    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    def launch(self, rehearsal_id: int, data: bytes, text: str) -> None:
        task = asyncio.create_task(
            score_take(rehearsal_id, data, text, self._session_factory)
        )
        _running.add(task)
        task.add_done_callback(_running.discard)


def get_rehearsal_scorer() -> RehearsalScorer:
    """FastAPI dependency. Bound to the application's own session factory."""
    from database import async_session

    return RehearsalScorer(async_session)


async def score_take(
    rehearsal_id: int,
    data: bytes,
    text: str,
    session_factory: async_sessionmaker,
) -> None:
    """One take, from `pending` to `scored` or `failed`. Never raises."""
    try:
        await _score(rehearsal_id, data, text, session_factory)
    except Exception as exc:  # noqa: BLE001 — see the module docstring
        log.exception("scoring take %s crashed", rehearsal_id)
        await _fail(rehearsal_id, session_factory, f"{type(exc).__name__}: {exc}")


async def _score(
    rehearsal_id: int,
    data: bytes,
    text: str,
    session_factory: async_sessionmaker,
) -> None:
    # ── Phase A: reads ──────────────────────────────────────────────────────
    async with session_factory() as db:
        take = await db.get(Rehearsal, rehearsal_id)
        if take is None:
            log.warning("take %s vanished before scoring", rehearsal_id)
            return
        if take.pron_status not in ("pending", "failed"):
            # Already scoring, or already scored. Two launches for one take is not worth
            # raising over, but it must not produce two sets of phone rows.
            log.info("take %s is %s; not scoring again", rehearsal_id, take.pron_status)
            return

        take.pron_status = "scoring"
        take.pron_detail = None
        await db.commit()

    # ── Phase B: the model, with no database connection held ────────────────
    scoring: PronScoring | None = None
    reason: str | None = None

    try:
        scoring = await pron_score(data, text, filename=f"rehearsal-{rehearsal_id}")
    except PronUnavailable as exc:
        # The ordinary case on a laptop that never started the profile. The take keeps
        # its transcript, its alignment and its counts, and says the sounds are missing.
        log.info("pron unavailable for take %s: %s", rehearsal_id, exc)
        reason = (
            "The pronunciation scorer is not running, so this take was compared and "
            "counted but not scored sound by sound."
        )
    except PronRejected as exc:
        log.info("pron rejected take %s: %s", rehearsal_id, exc.detail)
        reason = f"The pronunciation scorer could not use this take: {exc.detail}"
    except PronProtocolError as exc:
        log.error("pron protocol skew on take %s: %s", rehearsal_id, exc)
        reason = (
            "The pronunciation scorer answered in a shape this API does not understand."
        )
    except PronMisconfigured as exc:
        log.error("PHONE MAP GAP — take %s: %s", rehearsal_id, exc)
        reason = "The pronunciation scorer is misconfigured; this has been logged."

    # ── Phase C: writes ─────────────────────────────────────────────────────
    async with session_factory() as db:
        take = await db.get(Rehearsal, rehearsal_id)
        if take is None:  # deleted while the model was working
            return

        if scoring is not None:
            existing = await db.scalars(
                select(RehearsalPhone).where(
                    RehearsalPhone.rehearsal_id == rehearsal_id
                )
            )
            for row in existing.all():
                await db.delete(row)

            db.add_all(
                [
                    RehearsalPhone(
                        rehearsal_id=rehearsal_id,
                        word=phone.word,
                        word_idx=phone.word_idx,
                        phone_idx=phone.phone_idx,
                        canonical_phone=phone.canonical_phone,
                        recognized_phone=phone.recognized_phone,
                        start_ms=phone.start_ms,
                        end_ms=phone.end_ms,
                        gop=phone.gop,
                        posterior=phone.posterior,
                    )
                    for phone in scoring.phones
                ]
            )
            take.pron_summary = scoring.summary.model_dump()
            log.info(
                "take %s scored: %d phones in %d ms",
                rehearsal_id,
                len(scoring.phones),
                scoring.latency_ms,
            )

        # `scored` either way. The take *was* processed — it has a transcript, an
        # alignment and its counts — and calling it failed because an optional service is
        # switched off would say the recording was lost when it was not.
        await _mark(db, take, "scored", reason)


async def _mark(db, take: Rehearsal, status: str, reason: str | None) -> None:
    take.pron_status = status
    take.pron_detail = reason
    take.scored_at = datetime.now(timezone.utc)
    await db.commit()


async def _fail(rehearsal_id: int, session_factory, reason: str) -> None:
    """Record a failure on its own connection, when the job itself came apart."""
    try:
        async with session_factory() as db:
            take = await db.get(Rehearsal, rehearsal_id)
            if take is not None:
                await _mark(db, take, "failed", reason)
    except Exception:  # noqa: BLE001 — the last line of defence; nothing above it
        log.exception("could not record the failure of take %s", rehearsal_id)
