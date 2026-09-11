"""Per-turn rows collapsed into one row per user per period.

**Why materialise at all.** The progress page reads snapshots and nothing else. Computing
a thirty-day chart from raw turns on every page load works beautifully for the first
month and gets slower every week after it, and the day it stops being acceptable is the
day the user has practised enough for the chart to be worth looking at. So the arithmetic
happens once, when the data changes, and the page reads the answer.

**Nothing here is written by a language model.** Every number below is counted from stored
rows: word timings the recogniser produced, forms a dependency parse found, error rows
whose spans were checked against the transcript, phone scores an acoustic model assigned
to a waveform. A model's *opinion* about a session is in that session's report and stops
there. This is the layer everything plotted comes from, and it is deterministic — the same
rows produce the same snapshot every time, which is what makes a rebuild safe.

**Two granularities, computed together.** A day is what a single evening's practice looks
like; a week is what shows a trend without a weekend of silence reading as a collapse.
Neither is derived from the other — a weekly snapshot is computed from turns, not from
seven daily snapshots — because averaging averages weights a quiet Tuesday the same as a
long Sunday.

**Periods are UTC days.** The alternative is the speaker's local day, which needs a time
zone this system does not ask for, and would silently reshuffle history the first time
somebody travelled. A late-evening session west of Greenwich therefore lands on the next
day's row. It is a real limitation, stated rather than hidden, and it is invisible at the
weekly granularity that the trend line actually uses.

**Everything the gate needs is stored beside what it gates.** `sample_counts` carries the
turns, words, attempts and per-phone instance counts behind every figure in the same row,
so a chart can decline to draw a point without going back to the source rows to find out
whether it should.
"""

from __future__ import annotations

import logging
import re
import statistics
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import (
    PROGRESS_BASELINE_DAYS,
    PROGRESS_MIN_PHONE_SAMPLES,
)
from db_models import (
    Attempt,
    AudioAsset,
    FluencyMetrics,
    GrammarUsage,
    LanguageError,
    PhonemeScore,
    PracticeSession,
    ProgressSnapshot,
    Turn,
)
from services.analysis import form_accuracy, is_counted, weighted_fluency

log = logging.getLogger("speaklab.rollup")

PERIODS: tuple[str, ...] = ("day", "week")

# Clause features are counted separately from the forms a learner would recognise by
# name, because the subordination index is a ratio of two of them rather than a count of
# either. Kept beside the arithmetic that uses them so a renamed feature breaks here
# rather than producing a quietly wrong ratio.
_MAIN_CLAUSE = "main_clause"
_EMBEDDED_CLAUSES = ("subordinate_clause", "relative_clause")

# Stress digits, as `g2p_en` emits them: AH0 and AH1 are the same sound said with
# different emphasis. A learner is told to work on a sound, so the trend is per sound —
# leaving the digits on would split one phone's history across three thin series, each
# too small to pass its own sample gate.
_STRESS = re.compile(r"[0-2]$")


def unstressed(phone: str) -> str:
    """`AH1` -> `AH`. The 39 symbols the phone map and the passages are written in."""
    return _STRESS.sub("", phone)


# ── Periods ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True, order=True)
class Period:
    """One row of `progress_snapshots`, before it has been computed."""

    period: str
    start: date

    @property
    def end(self) -> date:
        """Exclusive. The first day this period does not cover."""
        return self.start + timedelta(days=7 if self.period == "week" else 1)

    def covers(self, day: date) -> bool:
        return self.start <= day < self.end


def period_start(day: date, period: str) -> date:
    """The first day of the period `day` falls in.

    Weeks start on Monday, which is the ISO convention and the one every date library
    here already agrees on. A configurable week start would be a setting whose only
    effect is to make two people's charts incomparable.
    """
    if period == "week":
        return day - timedelta(days=day.weekday())
    if period == "day":
        return day
    raise ValueError(f"unknown period {period!r}")


def periods_for(days: set[date]) -> set[Period]:
    """Every period, at both granularities, that any of these days falls in."""
    return {
        Period(period, period_start(day, period)) for day in days for period in PERIODS
    }


def _utc_day(moment: datetime) -> date:
    """The UTC calendar day a timestamp falls on.

    Timestamps arrive from asyncpg as aware datetimes; a naive one would be a row written
    by something that bypassed the schema's `timestamptz`, and treating it as UTC is the
    only defensible reading left.
    """
    if moment.tzinfo is None:
        return moment.date()
    return moment.astimezone(timezone.utc).date()


# ── The corpus this user has produced ───────────────────────────────────────


@dataclass
class TurnRow:
    """One analysed user turn, with everything derived from it."""

    id: int
    session_id: int
    day: date
    changed_at: datetime | None
    measures: FluencyMetrics | None = None
    features: dict[str, int] = field(default_factory=dict)
    errors: list[LanguageError] = field(default_factory=list)


@dataclass
class AttemptRow:
    """One scored reading, with its per-phone means."""

    id: int
    day: date
    changed_at: datetime | None
    device_hint: str | None
    # phone -> (instances, mean gop). Per attempt, because a reading is the unit a
    # baseline varies over: the forty instances of one phone inside a single reading were
    # produced in one room at one distance from one microphone, and treating them as
    # forty independent samples would make every baseline look far tighter than it is.
    phones: dict[str, tuple[int, float]] = field(default_factory=dict)


@dataclass
class Corpus:
    """Everything one user has produced, read once and bucketed in memory.

    Read once rather than per period, because the same turn belongs to a daily snapshot
    and a weekly one, and a month of practice is a few hundred rows. The cost of the
    whole rollup is this load; the arithmetic on top of it is free.
    """

    turns: list[TurnRow] = field(default_factory=list)
    attempts: list[AttemptRow] = field(default_factory=list)

    @property
    def days(self) -> set[date]:
        return {row.day for row in self.turns} | {row.day for row in self.attempts}

    def turns_in(self, period: Period) -> list[TurnRow]:
        return [row for row in self.turns if period.covers(row.day)]

    def attempts_in(self, period: Period) -> list[AttemptRow]:
        return [row for row in self.attempts if period.covers(row.day)]

    def attempts_before(self, start: date, days: int) -> list[AttemptRow]:
        """The readings a pronunciation baseline is drawn from.

        Strictly before the period, so a period is never compared against itself: a
        baseline that included today's reading would move towards it, and the more
        unusual the reading the more the baseline would absorb it.
        """
        floor = start - timedelta(days=days)
        return [row for row in self.attempts if floor <= row.day < start]


async def load(db: AsyncSession, user_id: int) -> Corpus:
    """Everything this user has that a snapshot is computed from.

    Only *analysed* turns and *scored* attempts. A turn still waiting for its analysis is
    not a turn with no errors in it, and rolling it up as though it were would put a
    number on the chart that changes the moment the analyser catches up.
    """
    corpus = Corpus()

    turn_rows = (
        await db.execute(
            select(Turn.id, Turn.session_id, Turn.created_at, Turn.analyzed_at)
            .join(PracticeSession, PracticeSession.id == Turn.session_id)
            .where(
                PracticeSession.user_id == user_id,
                Turn.role == "user",
                Turn.analysis_status == "analyzed",
            )
            .order_by(Turn.id)
        )
    ).all()

    by_turn = {
        turn_id: TurnRow(
            id=turn_id,
            session_id=session_id,
            day=_utc_day(created_at),
            changed_at=analyzed_at,
        )
        for turn_id, session_id, created_at, analyzed_at in turn_rows
    }
    corpus.turns = list(by_turn.values())
    turn_ids = list(by_turn)

    if turn_ids:
        for measures in (
            await db.scalars(
                select(FluencyMetrics).where(FluencyMetrics.turn_id.in_(turn_ids))
            )
        ).all():
            by_turn[measures.turn_id].measures = measures

        for turn_id, feature, count in (
            await db.execute(
                select(
                    GrammarUsage.turn_id, GrammarUsage.feature, GrammarUsage.count
                ).where(GrammarUsage.turn_id.in_(turn_ids))
            )
        ).all():
            by_turn[turn_id].features[feature] = count

        for row in (
            await db.scalars(
                select(LanguageError).where(LanguageError.turn_id.in_(turn_ids))
            )
        ).all():
            by_turn[row.turn_id].errors.append(row)

    attempt_rows = (
        await db.execute(
            select(
                Attempt.id,
                Attempt.created_at,
                Attempt.scored_at,
                AudioAsset.device_hint,
            )
            .join(PracticeSession, PracticeSession.id == Attempt.session_id)
            .outerjoin(AudioAsset, AudioAsset.id == Attempt.audio_asset_id)
            .where(PracticeSession.user_id == user_id, Attempt.status == "scored")
            .order_by(Attempt.id)
        )
    ).all()

    by_attempt = {
        attempt_id: AttemptRow(
            id=attempt_id,
            day=_utc_day(created_at),
            changed_at=scored_at,
            device_hint=device_hint,
        )
        for attempt_id, created_at, scored_at, device_hint in attempt_rows
    }
    corpus.attempts = list(by_attempt.values())

    if by_attempt:
        # Grouped in the database rather than loaded row by row. A reading is 250 phones
        # and a month of practice is tens of thousands of them, none of which anything
        # here looks at individually — the unit is a phone's mean within one reading.
        grouped = (
            await db.execute(
                select(
                    PhonemeScore.attempt_id,
                    PhonemeScore.canonical_phone,
                    func.count(),
                    func.avg(PhonemeScore.gop),
                )
                .where(PhonemeScore.attempt_id.in_(list(by_attempt)))
                .group_by(PhonemeScore.attempt_id, PhonemeScore.canonical_phone)
            )
        ).all()

        # Stress variants are folded together here rather than in the query, because
        # merging two weighted means is arithmetic and stripping a suffix in SQL is a
        # string function per row.
        for attempt_id, phone, count, mean_gop in grouped:
            phones = by_attempt[attempt_id].phones
            symbol = unstressed(phone)
            seen, running = phones.get(symbol, (0, 0.0))
            total = seen + count
            phones[symbol] = (
                total,
                (running * seen + float(mean_gop) * count) / total,
            )

    return corpus


# ── The arithmetic ──────────────────────────────────────────────────────────


def zscore(value: float, baseline: list[float]) -> float | None:
    """Where `value` sits in this speaker's own recent history, in standard deviations.

    `None` rather than a number whenever the baseline cannot support one: fewer than two
    prior readings, or a spread of zero. Both are real states — a first reading has
    nothing to be compared against — and answering them with 0.0 would draw a speaker at
    exactly their own average, which is a claim about them rather than about the data.

    A *sample* standard deviation, not a population one. The prior readings are a sample
    of how this speaker says this sound, not the whole of it.

    Sign follows the metric: goodness-of-pronunciation is a log-probability difference
    that is at most zero, so larger is better and a positive z is an improvement on this
    speaker's own recent form. Nothing here compares one speaker against another, because
    the raw number is as much a property of the microphone as of the mouth.
    """
    if len(baseline) < 2:
        return None
    spread = statistics.stdev(baseline)
    if spread == 0:
        return None
    return round((value - statistics.fmean(baseline)) / spread, 3)


def _fluency_of(turns: list[TurnRow]) -> dict:
    """Speech rate, articulation, pausing and fillers over a period.

    The same weighting the session report uses, from the same function, so the figure a
    learner reads at the end of a session and the point that session contributes to a
    chart are computed once rather than twice.
    """
    measures = [row.measures for row in turns if row.measures is not None]
    return weighted_fluency(measures) or {}


def _accuracy_of(turns: list[TurnRow], words: int) -> dict:
    """Errors per hundred words, the same by category, and accuracy per verb form.

    Only the rows that may reach a rate. An error sitting on words the recogniser was
    unsure of, or one the labelling model hedged on, is shown to the learner in the
    session it came from and excluded here — the exclusions are reported alongside so a
    thin-looking month can be told apart from a clean one.
    """
    rows = [error for turn in turns for error in turn.errors]
    counted = [row for row in rows if is_counted(row)]
    used: dict[str, int] = {}
    for turn in turns:
        for feature, count in turn.features.items():
            used[feature] = used.get(feature, 0) + count

    by_category: dict[str, int] = {}
    for row in counted:
        by_category[row.category] = by_category.get(row.category, 0) + 1

    return {
        "errors_per_100_words": (
            round(len(counted) * 100 / words, 2) if words else None
        ),
        "by_category": dict(sorted(by_category.items())),
        "by_category_per_100_words": (
            {
                category: round(count * 100 / words, 2)
                for category, count in sorted(by_category.items())
            }
            if words
            else {}
        ),
        # Per verb form: used, right, wrong, missed, and right over used plus missed. The
        # same function the session report uses, over the same rows.
        "by_form": form_accuracy(used, rows),
        "excluded": {
            "asr_suspect": sum(1 for row in rows if row.asr_suspect),
            "low_confidence": sum(
                1 for row in rows if not row.asr_suspect and not is_counted(row)
            ),
        },
    }


def _complexity_of(turns: list[TurnRow]) -> dict:
    """Breadth: which forms were used, how many of them, and how much subordination.

    This is the half of the picture that stops a falling error rate from being read as
    improvement on its own. A learner who retreats to the present simple produces fewer
    errors and a smaller repertoire, and only one of those two numbers says so.
    """
    totals: dict[str, int] = {}
    for turn in turns:
        for feature, count in turn.features.items():
            totals[feature] = totals.get(feature, 0) + count

    main = totals.get(_MAIN_CLAUSE, 0)
    embedded = sum(totals.get(name, 0) for name in _EMBEDDED_CLAUSES)

    return {
        "distinct_forms": len(totals),
        "form_instances": sum(totals.values()),
        "by_form": dict(sorted(totals.items())),
        # Embedded clauses per main clause. `None` rather than 0 when there are no main
        # clauses at all: a period with nothing to divide by has no ratio, and zero would
        # read as speech with no subordination in it.
        "subordination_index": round(embedded / main, 3) if main else None,
    }


def _pronunciation_of(
    attempts: list[AttemptRow], baseline_attempts: list[AttemptRow]
) -> tuple[dict, dict[str, int]]:
    """Mean goodness-of-pronunciation per phone, and where it sits against this speaker.

    Returns the values and the per-phone instance counts, because the counts are what
    decide whether any of it is drawn and belong in the row's sample counts rather than
    duplicated inside the values.
    """
    period_totals: dict[str, tuple[int, float]] = {}
    for attempt in attempts:
        for phone, (count, mean_gop) in attempt.phones.items():
            seen, running = period_totals.get(phone, (0, 0.0))
            total = seen + count
            period_totals[phone] = (total, (running * seen + mean_gop * count) / total)

    # One value per prior reading, not per instance. The spread that matters is how much
    # this speaker's readings of a sound differ from each other.
    baseline: dict[str, list[float]] = {}
    for attempt in baseline_attempts:
        for phone, (count, mean_gop) in attempt.phones.items():
            if count >= PROGRESS_MIN_PHONE_SAMPLES:
                baseline.setdefault(phone, []).append(mean_gop)

    phones = {}
    for phone, (count, mean_gop) in sorted(period_totals.items()):
        prior = baseline.get(phone, [])
        phones[phone] = {
            "mean_gop": round(mean_gop, 4),
            "z": zscore(mean_gop, prior),
            "baseline_mean": round(statistics.fmean(prior), 4) if prior else None,
            "baseline_readings": len(prior),
        }

    instances = sum(count for count, _ in period_totals.values())
    values = {
        "phones": phones,
        "mean_gop": (
            round(
                sum(count * mean for count, mean in period_totals.values()) / instances,
                4,
            )
            if instances
            else None
        ),
    }
    return values, {phone: count for phone, (count, _) in sorted(period_totals.items())}


def snapshot_values(corpus: Corpus, period: Period) -> dict:
    """One snapshot's five families, computed from rows and nothing else.

    A pure function of the corpus, which is what makes the arithmetic testable without a
    database and the rebuild safe to run at any time: the same rows always produce the
    same row.
    """
    turns = corpus.turns_in(period)
    attempts = corpus.attempts_in(period)

    fluency = _fluency_of(turns)
    words = int(fluency.get("words_spoken") or 0)
    pronunciation, phone_samples = _pronunciation_of(
        attempts, corpus.attempts_before(period.start, PROGRESS_BASELINE_DAYS)
    )
    accuracy = _accuracy_of(turns, words)

    return {
        "fluency": fluency,
        "accuracy": accuracy,
        "complexity": _complexity_of(turns),
        "pronunciation": pronunciation,
        "sample_counts": {
            "turns": len(turns),
            "words": words,
            "sessions": len({turn.session_id for turn in turns}),
            "attempts": len(attempts),
            "phones": sum(phone_samples.values()),
            "phone_samples": phone_samples,
            "errors_counted": sum(
                1 for turn in turns for error in turn.errors if is_counted(error)
            ),
            "errors_excluded": sum(
                1 for turn in turns for error in turn.errors if not is_counted(error)
            ),
            # Which microphones this period's readings came from. Pronunciation scores
            # move with the recording setup, so a period that mixes two of them is a
            # period whose comparison against the last one is partly about hardware. The
            # column that answers this is not populated by anything yet, so the list is
            # empty in practice and the chart has nothing to annotate — recorded here so
            # that the day it is populated, the annotation is already being computed.
            "devices": sorted(
                {
                    attempt.device_hint
                    for attempt in attempts
                    if attempt.device_hint is not None
                }
            ),
        },
    }


# ── Writing ─────────────────────────────────────────────────────────────────


def latest_input(corpus: Corpus, period: Period) -> datetime | None:
    """When anything in this period was last analysed or scored."""
    changes = [
        row.changed_at
        for row in (*corpus.turns_in(period), *corpus.attempts_in(period))
        if row.changed_at is not None
    ]
    return max(changes) if changes else None


async def rebuild(
    db: AsyncSession, user_id: int, corpus: Corpus, period: Period
) -> ProgressSnapshot:
    """Compute one period and write it, replacing whatever was there.

    Replace rather than merge: a snapshot is a function of the rows underneath it, and a
    turn that was deleted or re-analysed has to be able to make a number go down. Merging
    would let a correction only ever add.
    """
    row = await db.scalar(
        select(ProgressSnapshot).where(
            ProgressSnapshot.user_id == user_id,
            ProgressSnapshot.period == period.period,
            ProgressSnapshot.period_start == period.start,
        )
    )
    if row is None:
        row = ProgressSnapshot(
            user_id=user_id, period=period.period, period_start=period.start
        )
        db.add(row)

    values = snapshot_values(corpus, period)
    row.fluency = values["fluency"]
    row.accuracy = values["accuracy"]
    row.complexity = values["complexity"]
    row.pronunciation = values["pronunciation"]
    row.sample_counts = values["sample_counts"]
    row.updated_at = datetime.now(timezone.utc)
    return row


async def rebuild_user(
    db: AsyncSession, user_id: int, force: bool = False
) -> list[Period]:
    """Bring every one of this user's snapshots up to date. Returns what was written.

    **Idempotent, and that is the property it is built around.** Running it twice writes
    the same numbers; running it after one new turn rewrites only the periods that turn
    belongs to. A period whose newest input is older than its snapshot is skipped, which
    is what keeps the endpoint that calls this cheap enough to call on every session end.

    Snapshots for periods that no longer have any data are deleted rather than left
    behind. A deleted session must not keep contributing a point to a chart.
    """
    corpus = await load(db, user_id)
    wanted = periods_for(corpus.days)

    existing = {
        Period(row.period, row.period_start): row
        for row in (
            await db.scalars(
                select(ProgressSnapshot).where(ProgressSnapshot.user_id == user_id)
            )
        ).all()
    }

    for period, row in existing.items():
        if period not in wanted:
            await db.delete(row)

    written: list[Period] = []
    for period in sorted(wanted):
        current = existing.get(period)
        newest = latest_input(corpus, period)
        fresh = (
            current is not None
            and newest is not None
            and current.updated_at is not None
            and _aware(current.updated_at) >= _aware(newest)
        )
        if fresh and not force:
            continue
        await rebuild(db, user_id, corpus, period)
        written.append(period)

    await db.flush()
    if written:
        log.info("rolled up %d periods for user %s", len(written), user_id)
    return written


def _aware(moment: datetime) -> datetime:
    """Compare timestamps without tripping over one that arrived naive."""
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=timezone.utc)


async def is_stale(db: AsyncSession, user_id: int) -> bool:
    """Whether anything has been analysed or scored since the last rollup.

    Three aggregates rather than a scan, because this is asked on every page load and the
    answer only decides whether to offer a rebuild. It is deliberately coarse: it says
    that *something* is newer, not which period, and finding that out is the rollup's own
    job.
    """
    newest_turn = await db.scalar(
        select(func.max(Turn.analyzed_at))
        .join(PracticeSession, PracticeSession.id == Turn.session_id)
        .where(PracticeSession.user_id == user_id, Turn.role == "user")
    )
    newest_attempt = await db.scalar(
        select(func.max(Attempt.scored_at))
        .join(PracticeSession, PracticeSession.id == Attempt.session_id)
        .where(PracticeSession.user_id == user_id)
    )
    newest_snapshot = await db.scalar(
        select(func.max(ProgressSnapshot.updated_at)).where(
            ProgressSnapshot.user_id == user_id
        )
    )

    inputs = [moment for moment in (newest_turn, newest_attempt) if moment is not None]
    if not inputs:
        return False
    if newest_snapshot is None:
        return True
    return _aware(max(inputs)) > _aware(newest_snapshot)
