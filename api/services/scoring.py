"""Pronunciation scoring as a background job.

**Only the phoneme half is asynchronous, and the split is deliberate.** A read-aloud
attempt does two things: transcribe the recording, and align it against the passage. The
first cannot be deferred — `audio_assets.duration_ms`, `sample_rate` and `format` are NOT
NULL and only a decoder knows them, so the row cannot exist until the recording has been
decoded (`services/audio.ingest_recording` says the same thing from the other side).
The second can, and should: it needs a 2 GB service that is off by default.

So `POST /attempts` returns 201 with a transcript and a WER already on it, and the phones
arrive afterwards. That ordering is also what makes an attempt survive a missing scorer:
an attempt whose `pron` never answers still has everything the recogniser produced,
because the recogniser ran first and in a different request.

**The job holds no database connection while the models work**, in the same three phases
as `routers/turns.py`:

    A  read      attempt, passage, asset path, mark `scoring`   connection held
    B  model     read the file, call pron                        NO connection
    C  write     phoneme rows, status, scored_at                 connection held

**The session factory is injected, never imported.** `routers/turns.py` records what
happens otherwise: a background task that reaches for the module-level factory points at
whatever `config.DATABASE_URL` names — the development database, even under a test that
had overridden `get_db`. It worked in production and was silently untestable, which is
the worse of the two failure modes. Here the factory arrives as an argument, and
`get_scorer` is a FastAPI dependency so a test replaces the whole launcher in one line.

**A job never raises.** It is a task nobody awaits; an exception escaping it would be
logged by asyncio as an unretrieved future and the attempt would sit in `scoring`
forever. Every failure becomes a row state with a reason on it, which is what a retry
needs in order to mean something.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from db_models import Attempt, AudioAsset, Passage, PhonemeScore
from models.attempt import PronScoring
from services.audio import AudioPathError, resolve_path
from services.pron_client import (
    PronMisconfigured,
    PronProtocolError,
    PronRejected,
    PronUnavailable,
)
from services.pron_client import score as pron_score

log = logging.getLogger("speaklab.scoring")

# Tasks are held here for their lifetime. `asyncio.create_task` returns a reference the
# event loop does NOT own: drop it and the task can be garbage-collected mid-await, which
# presents as a job that silently never finished. The same footgun `infra/asr/app.py`
# guards against in its lifespan.
_running: set[asyncio.Task] = set()


class Scorer:
    """Launches scoring jobs. The seam the tests replace.

    It exists as an object rather than a bare function so that `get_scorer` can be a
    FastAPI dependency: a test overrides it with something that records the ids and runs
    them on demand, which turns "a task completes eventually" into "the job ran, here is
    what it wrote". Nothing about the job itself changes between the two.
    """

    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    def launch(self, attempt_id: int) -> None:
        task = asyncio.create_task(score_attempt(attempt_id, self._session_factory))
        _running.add(task)
        task.add_done_callback(_running.discard)


def get_scorer() -> Scorer:
    """FastAPI dependency. Bound to the application's own session factory."""
    from database import async_session

    return Scorer(async_session)


async def score_attempt(attempt_id: int, session_factory: async_sessionmaker) -> None:
    """One attempt, from `pending` to `scored` or `failed`. Never raises."""
    try:
        await _score(attempt_id, session_factory)
    except Exception as exc:  # noqa: BLE001 — see the module docstring
        log.exception("scoring attempt %s crashed", attempt_id)
        await _fail(attempt_id, session_factory, f"{type(exc).__name__}: {exc}")


async def _score(attempt_id: int, session_factory: async_sessionmaker) -> None:
    # ── Phase A: reads ──────────────────────────────────────────────────────
    async with session_factory() as db:
        attempt = await db.get(Attempt, attempt_id)
        if attempt is None:
            log.warning("attempt %s vanished before scoring", attempt_id)
            return
        if attempt.status not in ("pending", "failed"):
            # Already scoring, or already scored. Two launches for one attempt is not an
            # error worth raising — a double-tapped rescore is the ordinary cause — but
            # it must not produce two sets of phoneme rows.
            log.info("attempt %s is %s; not scoring again", attempt_id, attempt.status)
            return

        passage = await db.get(Passage, attempt.passage_id)
        asset = await db.get(AudioAsset, attempt.audio_asset_id)
        if passage is None or asset is None:
            await _mark(
                db, attempt, "failed", "The passage or the recording is missing."
            )
            return

        try:
            path = resolve_path(asset)
        except AudioPathError as exc:
            await _mark(db, attempt, "failed", str(exc))
            return

        body = passage.body
        attempt.status = "scoring"
        attempt.error_message = None
        await db.commit()

    # ── Phase B: the model, with no database connection held ────────────────
    try:
        data = await asyncio.to_thread(path.read_bytes)
    except OSError as exc:
        await _fail(
            attempt_id, session_factory, f"The recording could not be read: {exc}"
        )
        return

    scoring: PronScoring | None = None
    reason: str | None = None

    try:
        scoring = await pron_score(data, body, filename=f"attempt-{attempt_id}")
    except PronUnavailable as exc:
        # The ordinary case on a laptop: the profile was never started. The attempt
        # keeps its transcript and its WER, and says the phones are missing.
        log.info("pron unavailable for attempt %s: %s", attempt_id, exc)
        reason = "The pronunciation scorer is not running, so this reading has a transcript but no phoneme scores."
    except PronRejected as exc:
        log.info("pron rejected attempt %s: %s", attempt_id, exc.detail)
        reason = f"The pronunciation scorer could not use this reading: {exc.detail}"
    except PronProtocolError as exc:
        log.error("pron protocol skew on attempt %s: %s", attempt_id, exc)
        reason = (
            "The pronunciation scorer answered in a shape this API does not understand."
        )
    except PronMisconfigured as exc:
        # Not transient and not the user's problem. Loud, because the image is wrong and
        # every attempt will hit this until somebody rebuilds it.
        log.error("PHONE MAP GAP — attempt %s: %s", attempt_id, exc)
        reason = "The pronunciation scorer is misconfigured; this has been logged."

    # ── Phase C: writes ─────────────────────────────────────────────────────
    async with session_factory() as db:
        attempt = await db.get(Attempt, attempt_id)
        if attempt is None:  # deleted while the model was working
            return

        if scoring is not None:
            # Replace rather than append. A rescore of an attempt that already has rows
            # must not leave two readings' phones interleaved under one attempt.
            existing = await db.scalars(
                select(PhonemeScore).where(PhonemeScore.attempt_id == attempt_id)
            )
            for row in existing.all():
                await db.delete(row)

            db.add_all(
                [
                    PhonemeScore(
                        attempt_id=attempt_id,
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
            log.info(
                "attempt %s scored: %d phones in %d ms",
                attempt_id,
                len(scoring.phones),
                scoring.latency_ms,
            )

        # `scored` either way. The reading *was* processed — it has a transcript and a
        # WER — and calling it `failed` because an optional service is switched off would
        # tell the user their recording was lost when it was not. The reason travels in
        # `error_message`, which `AttemptDetail` turns into `pronunciation: unavailable`.
        await _mark(db, attempt, "scored", reason)


async def _mark(db, attempt: Attempt, status: str, reason: str | None) -> None:
    attempt.status = status
    attempt.error_message = reason
    attempt.scored_at = datetime.now(timezone.utc)
    await db.commit()


async def _fail(attempt_id: int, session_factory, reason: str) -> None:
    """Record a failure on its own connection. Used when the job itself came apart."""
    try:
        async with session_factory() as db:
            attempt = await db.get(Attempt, attempt_id)
            if attempt is not None:
                await _mark(db, attempt, "failed", reason)
    except Exception:  # noqa: BLE001 — the last line of defence; nothing above it
        log.exception("could not record the failure of attempt %s", attempt_id)
