"""Analysis as a background job: one user turn, three analysers, one transaction.

**Why it is not inline.** A conversational turn already spends a second and a half in
three model services and has a three-second budget. Labelling errors is another model
call, and nobody is waiting for it — the result is read at the end of the session, not in
the reply. So the turn returns and this runs behind it.

**The same three phases as scoring, for the same reason.**

    A  read      the turn, and claim it                      connection held
    B  work      spaCy parse, the labelling model, the       NO connection
                 form each correction was made in
    C  write     fluency, grammar, errors, status            connection held

A pooled connection held across a slow non-database step is how a pool of ten is
exhausted by four users, and phase B here is the slowest step in the system.

**The claim in phase A is what makes this safe to run twice.** A live job and a backfill
can reach the same turn; the first to set `analyzing` owns it and the second returns.
Without it both would write a second copy of every error row.

**A job never raises.** Nobody awaits it, so an escaping exception would be logged by
asyncio as an unretrieved future and the turn would sit in `analyzing` for ever. Every
failure becomes a status with a reason on it, which is what a retry needs to mean
anything.

**Deterministic first, model second.** Fluency and grammar are arithmetic and a parse:
they succeed whether or not Ollama is running, and they are written even when the
labelling call fails. So is the rule layer, which reads the same parse. A turn whose error
labelling was unavailable still has its fluency, its forms and its rule-found errors, and
says so.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from config import ANALYSIS_SESSION_BUDGET_S, ERROR_CONFIDENCE_FLOOR
from db_models import FluencyMetrics, GrammarUsage, LanguageError, Scenario, Turn
from services import errors as error_detector
from services import fluency, forms, grammar, rules
from services.llm import LlmProvider, get_provider

log = logging.getLogger("speaklab.analysis")

# Tasks are held for their lifetime. `asyncio.create_task` returns a reference the event
# loop does not own: drop it and the task can be collected mid-await, which presents as a
# job that silently never finished.
_running: set[asyncio.Task] = set()


@dataclass
class Outcome:
    """What one turn's analysis did, for a caller that ran it directly."""

    status: str
    features: int = 0
    errors: int = 0
    rejected: int = 0
    detail: str | None = None


class Analyser:
    """Launches analysis jobs. The seam the tests replace.

    An object rather than a bare function so a FastAPI dependency can supply it: a test
    overrides `get_analyser` with something that records turn ids and runs them on
    demand, which turns "a task finishes eventually" into "the job ran, here is what it
    wrote".
    """

    def __init__(
        self, session_factory: async_sessionmaker, provider: LlmProvider
    ) -> None:
        self._session_factory = session_factory
        self._provider = provider

    def launch(self, turn_id: int) -> None:
        task = asyncio.create_task(
            analyse_turn(turn_id, self._session_factory, self._provider)
        )
        _running.add(task)
        task.add_done_callback(_running.discard)

    async def ensure_session(self, session_id: int) -> tuple[int, int]:
        """Analyse whatever this session still owes, and wait for it.

        On the object rather than as a loose function so the session factory travels with
        the seam. A caller that reached for the module-level factory instead would point
        at whatever `DATABASE_URL` names — the development database, even under a test
        that had overridden the request's own session.
        """
        return await ensure_session_analysed(
            session_id, self._session_factory, self._provider
        )


def get_analyser() -> Analyser:
    """FastAPI dependency. Bound to the application's own session factory."""
    from database import async_session

    return Analyser(async_session, get_provider())


async def analyse_turn(
    turn_id: int, session_factory: async_sessionmaker, provider: LlmProvider
) -> Outcome:
    """One turn, from `pending` to `analyzed` or `failed`. Never raises."""
    try:
        return await _analyse(turn_id, session_factory, provider)
    except Exception as exc:  # noqa: BLE001 — see the module docstring
        log.exception("analysing turn %s crashed", turn_id)
        detail = f"{type(exc).__name__}: {exc}"
        await _fail(turn_id, session_factory, detail)
        return Outcome(status="failed", detail=detail)


async def _analyse(
    turn_id: int, session_factory: async_sessionmaker, provider: LlmProvider
) -> Outcome:
    # ── Phase A: read and claim ─────────────────────────────────────────────
    async with session_factory() as db:
        turn = await db.get(Turn, turn_id)
        if turn is None:
            log.warning("turn %s vanished before analysis", turn_id)
            return Outcome(status="gone")
        if turn.role != "user":
            return Outcome(status="skipped", detail="only user turns are analysed")
        if turn.analysis_status not in ("pending", "failed", None):
            # Already claimed, or already done. Two launches for one turn is ordinary —
            # a live job and a backfill pass — and must not produce two sets of rows.
            log.info(
                "turn %s is %s; not analysing again", turn_id, turn.analysis_status
            )
            return Outcome(status="claimed-elsewhere")

        transcript = (turn.transcript or "").strip()
        words = turn.words
        turn.analysis_status = "analyzing"
        turn.analysis_error = None
        await db.commit()

    # ── Phase B: the analysers, with no database connection held ────────────
    measures = fluency.analyse(words)

    doc = None
    try:
        doc = await asyncio.to_thread(grammar.parse, transcript)
        features = grammar.count(doc)
        grammar_detail = None
    except Exception as exc:  # noqa: BLE001
        # A missing or broken parser must not cost the turn its fluency numbers, and it
        # is a deployment fault rather than anything about this speaker.
        log.error("grammar parse failed on turn %s: %s", turn_id, exc)
        features, grammar_detail = {}, f"the parser failed: {type(exc).__name__}"

    try:
        ruled = rules.propose(doc)
    except Exception as exc:  # noqa: BLE001
        # A rule that raised is a defect in this code, and the model's labelling and the
        # forms already counted are still worth writing.
        log.exception("the rule layer failed on turn %s", turn_id)
        ruled = []
        grammar_detail = " · ".join(
            part
            for part in (grammar_detail, f"the rule layer failed: {type(exc).__name__}")
            if part
        )

    detection = await error_detector.detect(provider, transcript, words, ruled)

    links = [forms.UNLINKED for _ in detection.errors]
    try:
        links = await asyncio.to_thread(
            forms.link,
            transcript,
            [found.accepted for found in detection.errors],
            doc,
        )
    except Exception as exc:  # noqa: BLE001
        # The corrections are real without their forms; they are stored unlinked and
        # stay out of accuracy per form until the turn is parsed again.
        log.exception("the form join failed on turn %s", turn_id)
        grammar_detail = " · ".join(
            part
            for part in (grammar_detail, f"the form join failed: {type(exc).__name__}")
            if part
        )

    # ── Phase C: writes, one transaction ────────────────────────────────────
    async with session_factory() as db:
        turn = await db.get(Turn, turn_id)
        if turn is None:  # deleted while the analysers were working
            return Outcome(status="gone")

        # Replace rather than append, so re-analysing a turn cannot leave two readings
        # of it interleaved.
        await db.execute(delete(GrammarUsage).where(GrammarUsage.turn_id == turn_id))
        await db.execute(delete(LanguageError).where(LanguageError.turn_id == turn_id))
        existing = await db.get(FluencyMetrics, turn_id)
        if existing is not None:
            await db.delete(existing)
            await db.flush()

        db.add(FluencyMetrics(turn_id=turn_id, **measures.as_columns()))
        db.add_all(
            [
                GrammarUsage(turn_id=turn_id, feature=feature, count=count)
                for feature, count in sorted(features.items())
            ]
        )
        db.add_all(
            [
                LanguageError(
                    turn_id=turn_id,
                    category=found.accepted.category,
                    subcategory=found.accepted.subcategory,
                    span_start=found.accepted.span_start,
                    span_end=found.accepted.span_end,
                    original=found.accepted.original,
                    correction=found.accepted.correction,
                    explanation=found.accepted.explanation,
                    form=link.form,
                    corrected_form=link.corrected_form,
                    detector=found.detector,
                    confidence=found.accepted.confidence,
                    asr_suspect=found.asr_suspect,
                )
                for found, link in zip(detection.errors, links, strict=True)
            ]
        )

        turn.analysis_rejects = detection.not_stored() or None
        turn.analyzed_at = datetime.now(timezone.utc)

        # `analyzed` even when the labelling model was down, and the reason travels in
        # `analysis_error`. The fluency and the forms are real and were computed; calling
        # the whole turn `failed` would hide them and invite a retry that recomputes work
        # that already succeeded. `failed` is reserved for a turn with nothing on it.
        detail = _detail(detection, grammar_detail)
        status = (
            "analyzed"
            if detection.status in ("ok", "skipped") or measures.word_count or features
            else "failed"
        )
        turn.analysis_status = status
        turn.analysis_error = detail
        await db.commit()

    log.info(
        "turn %s analysed: %d forms, %d errors, %d rejected",
        turn_id,
        len(features),
        len(detection.errors),
        len(detection.rejected),
    )
    return Outcome(
        status=status,
        features=len(features),
        errors=len(detection.errors),
        rejected=len(detection.rejected),
        detail=detail,
    )


def _detail(detection, grammar_detail: str | None) -> str | None:
    parts = [
        part
        for part in (
            grammar_detail,
            (
                None
                if detection.status == "ok"
                else f"error labelling {detection.status}: {detection.detail}"
            ),
        )
        if part
    ]
    return " · ".join(parts)[:1000] or None


async def _fail(turn_id: int, session_factory, reason: str) -> None:
    """Record a failure on its own connection, for when the job itself came apart."""
    try:
        async with session_factory() as db:
            turn = await db.get(Turn, turn_id)
            if turn is not None:
                turn.analysis_status = "failed"
                turn.analysis_error = reason[:1000]
                turn.analyzed_at = datetime.now(timezone.utc)
                await db.commit()
    except Exception:  # noqa: BLE001 — the last line of defence; nothing above it
        log.exception("could not record the failure of turn %s", turn_id)


@dataclass
class Reparsed:
    """What re-deriving one turn from its transcript changed."""

    turn_id: int
    forms_before: dict[str, int]
    forms_after: dict[str, int]
    corrections: int
    linked: int


async def reparse_turn(
    turn_id: int, session_factory: async_sessionmaker
) -> Reparsed | None:
    """Recount an analysed turn's forms and relink its corrections. No model is called.

    Everything here is a function of the stored transcript and the stored corrections, so
    a change to the parser or to the join reaches turns analysed before it without asking
    the model anything again. The corrections themselves are left as they are, rule rows
    included: which rule row and which model row a turn holds was decided together, and
    re-running one side alone could store a correction the other already made.

    None when the turn is not an analysed user turn.
    """
    async with session_factory() as db:
        turn = await db.get(Turn, turn_id)
        if turn is None or turn.role != "user" or turn.analysis_status != "analyzed":
            return None
        transcript = (turn.transcript or "").strip()
        before = dict(
            (
                await db.execute(
                    select(GrammarUsage.feature, GrammarUsage.count).where(
                        GrammarUsage.turn_id == turn_id
                    )
                )
            ).all()
        )
        rows = list(
            (
                await db.scalars(
                    select(LanguageError)
                    .where(LanguageError.turn_id == turn_id)
                    .order_by(LanguageError.id)
                )
            ).all()
        )

    doc = await asyncio.to_thread(grammar.parse, transcript)
    features = grammar.count(doc)
    links = await asyncio.to_thread(forms.link, transcript, rows, doc)

    async with session_factory() as db:
        turn = await db.get(Turn, turn_id)
        if turn is None:
            return None
        await db.execute(delete(GrammarUsage).where(GrammarUsage.turn_id == turn_id))
        db.add_all(
            [
                GrammarUsage(turn_id=turn_id, feature=feature, count=count)
                for feature, count in sorted(features.items())
            ]
        )
        for row, link in zip(rows, links, strict=True):
            stored = await db.get(LanguageError, row.id)
            if stored is not None:
                stored.form = link.form
                stored.corrected_form = link.corrected_form
        # The rows under this turn changed, so every snapshot computed from them is older
        # than what it summarises and the next rollup rebuilds it.
        turn.analyzed_at = datetime.now(timezone.utc)
        await db.commit()

    return Reparsed(
        turn_id=turn_id,
        forms_before=before,
        forms_after=features,
        corrections=len(rows),
        linked=sum(1 for link in links if link.linked),
    )


async def analysed_turn_ids(db) -> list[int]:
    """Every analysed user turn, oldest first."""
    return list(
        (
            await db.scalars(
                select(Turn.id)
                .where(Turn.role == "user", Turn.analysis_status == "analyzed")
                .order_by(Turn.id)
            )
        ).all()
    )


async def pending_turn_ids(db, session_id: int | None = None) -> list[int]:
    """User turns still owed analysis, oldest first.

    `failed` is included: a turn whose labelling model was down is exactly the turn a
    later pass should pick up, and there is no separate retry queue to put it in.
    """
    query = (
        select(Turn.id)
        .where(Turn.role == "user")
        .where(Turn.analysis_status.in_(("pending", "failed")))
        .order_by(Turn.id)
    )
    if session_id is not None:
        query = query.where(Turn.session_id == session_id)
    return list((await db.scalars(query)).all())


async def ensure_session_analysed(
    session_id: int,
    session_factory: async_sessionmaker,
    provider: LlmProvider,
    budget_s: float = ANALYSIS_SESSION_BUDGET_S,
) -> tuple[int, int]:
    """Analyse whatever this session still owes, within a time budget.

    Returns how many turns were analysed here and how many are still outstanding. It is
    called when a session ends, because the report is stored once and a report written
    before its last turn was analysed would be permanently missing it.

    Turns are done one at a time rather than concurrently: they queue behind one Ollama
    anyway, and a burst of parallel calls would make the wait less predictable rather
    than shorter.
    """
    async with session_factory() as db:
        outstanding = await pending_turn_ids(db, session_id)

    if not outstanding:
        return 0, 0

    loop = asyncio.get_running_loop()
    deadline = loop.time() + budget_s
    analysed = 0

    for turn_id in outstanding:
        if loop.time() >= deadline:
            break
        remaining = deadline - loop.time()
        try:
            await asyncio.wait_for(
                analyse_turn(turn_id, session_factory, provider), timeout=remaining
            )
        except TimeoutError:
            # The turn keeps whatever state the job left it in. `analyzing` would strand
            # it, so it is put back where a later pass will find it.
            await _release(turn_id, session_factory)
            break
        analysed += 1

    async with session_factory() as db:
        still_owed = len(await pending_turn_ids(db, session_id))
    return analysed, still_owed


async def _release(turn_id: int, session_factory) -> None:
    """Put a turn abandoned mid-flight back in the queue."""
    try:
        async with session_factory() as db:
            turn = await db.get(Turn, turn_id)
            if turn is not None and turn.analysis_status == "analyzing":
                turn.analysis_status = "pending"
                turn.analysis_error = "analysis ran out of time and will be retried"
                await db.commit()
    except Exception:  # noqa: BLE001
        log.exception("could not release turn %s", turn_id)


async def summarise(db, session_id: int, scenario: Scenario | None) -> dict:
    """Everything the analysers produced for one session, as the report carries it.

    Read from the stored rows rather than recomputed, so the report and any later trend
    are looking at the same numbers. Nothing here is written by a model: the counts are
    counts, and the error rows an LLM proposed are reported with the suspect ones held
    apart rather than folded in.
    """
    turn_ids = list(
        (
            await db.scalars(
                select(Turn.id)
                .where(Turn.session_id == session_id, Turn.role == "user")
                .order_by(Turn.idx)
            )
        ).all()
    )
    states = dict(
        (
            await db.execute(
                select(Turn.analysis_status, func.count())
                .where(Turn.session_id == session_id, Turn.role == "user")
                .group_by(Turn.analysis_status)
            )
        ).all()
    )

    if not turn_ids:
        return {
            "complete": True,
            "turns_analysed": 0,
            "turns_outstanding": 0,
            "fluency": None,
            "grammar_usage": {},
            "target_forms": _target_forms(scenario, {}),
            "form_accuracy": {},
            "errors": _empty_errors(),
        }

    measures = list(
        (
            await db.scalars(
                select(FluencyMetrics).where(FluencyMetrics.turn_id.in_(turn_ids))
            )
        ).all()
    )
    features = dict(
        (
            await db.execute(
                select(GrammarUsage.feature, func.sum(GrammarUsage.count))
                .where(GrammarUsage.turn_id.in_(turn_ids))
                .group_by(GrammarUsage.feature)
                .order_by(GrammarUsage.feature)
            )
        ).all()
    )
    found = list(
        (
            await db.scalars(
                select(LanguageError)
                .where(LanguageError.turn_id.in_(turn_ids))
                .order_by(LanguageError.turn_id, LanguageError.span_start)
            )
        ).all()
    )
    rejects = list(
        (
            await db.scalars(select(Turn.analysis_rejects).where(Turn.id.in_(turn_ids)))
        ).all()
    )

    outstanding = states.get("pending", 0) + states.get("analyzing", 0)
    return {
        "complete": outstanding == 0,
        "turns_analysed": states.get("analyzed", 0),
        "turns_outstanding": outstanding,
        "fluency": weighted_fluency(measures),
        "grammar_usage": {feature: int(count) for feature, count in features.items()},
        "target_forms": _target_forms(scenario, features),
        "form_accuracy": form_accuracy(features, found),
        "errors": _errors(found, measures, rejects),
    }


def form_accuracy(features: dict, found: list[LanguageError]) -> dict:
    """How correctly each verb form was used, from the forms counted and the corrections.

    Only the corrections that may reach a rate, for the reason `is_counted` gives. Shared
    with the rollups, so a session and the month it belongs to divide the same way.
    """
    links = [
        forms.Link(row.form, row.corrected_form) for row in found if is_counted(row)
    ]
    return {
        form: tally.as_dict()
        for form, tally in forms.tally(
            {feature: int(count) for feature, count in features.items()}, links
        ).items()
    }


def is_counted(row: LanguageError) -> bool:
    """Whether this error may reach a rate.

    Two exclusions, and they are different facts. `asr_suspect` means the words under the
    correction may not be what the speaker said. Below the confidence floor means the
    model that proposed it hedged. Both rows are shown to the learner; neither is counted.

    One function rather than the condition written wherever it is needed, because the
    session report and the trend must exclude exactly the same rows — a rate that differs
    between the two screens showing it is worse than either number alone.
    """
    return not row.asr_suspect and row.confidence >= ERROR_CONFIDENCE_FLOOR


def weighted_fluency(measures: list[FluencyMetrics]) -> dict | None:
    """Fluency across many turns, weighted by how much was said in each.

    A plain mean across turns would let "Thank you." count as much as a sixty-word
    answer, which is how a session ends up reporting a speech rate nobody spoke at.

    Shared with the rollups rather than reimplemented there, so a month of practice is
    averaged the same way one session is and the two cannot disagree about the same
    speech.
    """
    words = sum(m.word_count or 0 for m in measures)
    if not measures or not words:
        return None

    def weighted(field: str) -> float | None:
        pairs = [
            (getattr(m, field), m.word_count or 0)
            for m in measures
            if getattr(m, field) is not None and m.word_count
        ]
        if not pairs:
            return None
        total = sum(weight for _, weight in pairs)
        return round(sum(value * weight for value, weight in pairs) / total, 2)

    fillers = sum(m.filler_count or 0 for m in measures)
    return {
        "words_spoken": words,
        "speech_rate_wpm": weighted("speech_rate_wpm"),
        "articulation_rate_wpm": weighted("articulation_rate"),
        "pause_ratio": weighted("pause_ratio"),
        "mean_length_run": weighted("mean_length_run"),
        "filler_count": fillers,
        "fillers_per_100_words": round(fillers * 100 / words, 2),
        # Silence before the first word of each recording, averaged. A floor on response
        # latency: the clock starts at the button, not at the end of the persona's reply.
        "mean_pause_before_speaking_ms": (
            round(
                sum(
                    m.response_latency_ms
                    for m in measures
                    if m.response_latency_ms is not None
                )
                / max(1, sum(1 for m in measures if m.response_latency_ms is not None))
            )
            if any(m.response_latency_ms is not None for m in measures)
            else None
        ),
    }


def _target_forms(scenario: Scenario | None, features: dict) -> dict:
    """Which declared target forms the speaker actually produced.

    A set difference, not a judgement. The scenario names the forms it was built to
    elicit in the same vocabulary the parser counts in, which is the whole reason that
    vocabulary is closed.
    """
    declared = list((scenario.target_grammar or []) if scenario else [])
    elicited = [form for form in declared if features.get(form)]
    return {
        "declared": declared,
        "elicited": elicited,
        "not_elicited": [form for form in declared if form not in elicited],
    }


def _empty_errors() -> dict:
    return {
        "total": 0,
        "counted": 0,
        "asr_suspect": 0,
        "low_confidence": 0,
        "per_100_words": None,
        "by_category": {},
        "items": [],
        "by_detector": {},
        "rejected": 0,
        "superseded": 0,
        "rejection_rate": None,
        "rejected_reasons": {},
    }


def _errors(found: list[LanguageError], measures, rejects) -> dict:
    """The error rows, with the ones that must not reach a trend held apart.

    Two exclusions and they are different. `asr_suspect` means the words may not be what
    the speaker said. Below the confidence floor means the model itself hedged. Both are
    shown to the learner and neither is counted, and they are reported separately because
    the first is a fact about the recogniser and the second about the labeller.

    **Which detector found each row is reported too**, because it changes how the split
    by category reads: the rule layer covers agreement and missing articles and nothing
    else, so those two are found more reliably than the other seven categories.
    """
    words = sum(m.word_count or 0 for m in measures) if measures else 0

    counted = [row for row in found if is_counted(row)]
    by_category: dict[str, int] = {}
    for row in counted:
        by_category[row.category] = by_category.get(row.category, 0) + 1
    by_detector: dict[str, int] = {}
    for row in found:
        by_detector[row.detector] = by_detector.get(row.detector, 0) + 1

    reasons: dict[str, int] = {}
    rejected = superseded = 0
    for record in rejects:
        for entry in record or []:
            reason = str(entry.get("reason", "unknown"))
            if reason == error_detector.SUPERSEDED:
                # Passed the gate and lost to a rule that made the same correction. Not
                # a refusal, so it does not move the model's rejection rate.
                superseded += 1
                continue
            rejected += 1
            reasons[reason] = reasons.get(reason, 0) + 1

    # The model's proposals, whatever became of them. Rule rows are not the model's.
    proposed = by_detector.get("llm", 0) + rejected + superseded
    return {
        "total": len(found),
        "counted": len(counted),
        "asr_suspect": sum(1 for row in found if row.asr_suspect),
        "low_confidence": sum(
            1 for row in found if row.confidence < ERROR_CONFIDENCE_FLOOR
        ),
        "per_100_words": round(len(counted) * 100 / words, 2) if words else None,
        "by_category": dict(sorted(by_category.items())),
        "items": [
            {
                "turn_id": row.turn_id,
                "category": row.category,
                "subcategory": row.subcategory,
                "span_start": row.span_start,
                "span_end": row.span_end,
                "original": row.original,
                "correction": row.correction,
                "explanation": row.explanation,
                "confidence": row.confidence,
                "asr_suspect": row.asr_suspect,
                "counted": row in counted,
                "detector": row.detector,
                "form": row.form,
                "corrected_form": row.corrected_form,
            }
            for row in found
        ],
        "by_detector": dict(sorted(by_detector.items())),
        "rejected": rejected,
        "superseded": superseded,
        # The measurement that says whether the labelling model is strong enough. It is
        # in the report rather than only in the logs because it is the number a decision
        # to change models would be made from.
        "rejection_rate": round(rejected / proposed, 4) if proposed else None,
        "rejected_reasons": dict(sorted(reasons.items())),
    }
