"""Snapshots into the series the progress page draws, with every gate applied here.

**The gate is the feature.** Seven turns of practice can be plotted; what it cannot do is
mean anything, and a chart that draws a confident line through two points is worse than no
chart at all — it invites a learner to act on noise, and it makes the system look certain
about something it is not. So a period below the sample floor produces a hole with a
reason attached, and a series with no periods above the floor is returned suppressed,
saying what it is waiting for.

**A number is drawn; a verdict is earned.** Every series carries its points. Only a series
whose metric has a defensibly better end *and* enough points to compare gets a direction.
Most fluency measures have no better end at all — a speaker who got faster may have got
more nervous, and one who paused less may have stopped thinking — so they are reported and
not judged. Saying "improving" about a speech rate would be the easiest sentence on this
page to write and the least defensible one on it.

**One thing this page cannot do, stated where somebody would look for it.** There is no
accuracy figure per grammatical form. Errors are filed under a taxonomy category and forms
are counted by a parser, and nothing in the schema links an error to the form it occurred
in. A per-form accuracy chart would be an invented join dressed as a measurement.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import (
    PROGRESS_MIN_ATTEMPTS,
    PROGRESS_MIN_PHONE_SAMPLES,
    PROGRESS_MIN_POINTS,
    PROGRESS_MIN_WORDS,
    PROGRESS_TREND_DAYS,
)
from db_models import ProgressSnapshot
from models.progress import (
    Family,
    Gate,
    PhoneTrend,
    Point,
    ProgressOut,
    ProgressTotals,
    Repertoire,
    Series,
)
from services.rollup import PERIODS, is_stale, period_start


@dataclass(frozen=True)
class Metric:
    """One line on a chart, and everything needed to decide whether to claim anything."""

    family: str
    key: str
    label: str
    unit: str | None = None
    # Which end is better, where saying so is defensible. `None` means the series is
    # drawn and no direction is claimed, which is the honest answer for most of fluency.
    better: str | None = None


# The four families. Order is the order they are read in: how much was said, how much of
# it was wrong, how varied it was, and how it sounded.
METRICS: tuple[Metric, ...] = (
    Metric("fluency", "speech_rate_wpm", "speech rate", "wpm"),
    Metric("fluency", "articulation_rate_wpm", "articulation rate", "wpm"),
    Metric("fluency", "pause_ratio", "time spent paused", "ratio"),
    Metric("fluency", "mean_length_run", "words between pauses", "words"),
    # The one fluency measure with a defensible direction. Fewer fillers is the goal
    # every speaker recognises, and unlike speed it does not trade off against care.
    Metric("fluency", "fillers_per_100_words", "fillers", "per 100 words", "lower"),
    Metric(
        "accuracy", "errors_per_100_words", "errors", "per 100 words", better="lower"
    ),
    Metric("complexity", "distinct_forms", "different forms used", "forms", "higher"),
    Metric("complexity", "form_instances", "form instances", "instances"),
    # Not a percentage, whatever it looks like: it is embedded clauses *per* main clause,
    # so 1.4 is ordinary and 0.36 means roughly one subordinate clause every three
    # sentences. Labelling it a ratio would have the interface render it as 36 %.
    Metric(
        "complexity",
        "subordination_index",
        "clauses inside clauses",
        "per main clause",
        "higher",
    ),
    # Against this speaker's own recent readings, in standard deviations. The raw score
    # below it moves with the microphone, so only this one is comparable across weeks.
    Metric("pronunciation", "mean_z", "against your own baseline", "sd", "higher"),
    Metric("pronunciation", "mean_gop", "raw score", "nats"),
)

FAMILY_LABELS: dict[str, tuple[str, str]] = {
    "fluency": (
        "How you speak",
        "Arithmetic over word timings. Speech rate spends the pauses; articulation rate "
        "takes them out.",
    ),
    "accuracy": (
        "What you get wrong",
        "Counted from stored corrections, per hundred words, so a long month does not "
        "read as a bad one.",
    ),
    "complexity": (
        "How much you reach for",
        "Which forms you actually produced. Breadth is here because a shrinking range "
        "of forms lowers an error rate without anybody getting better.",
    ),
    "pronunciation": (
        "How you sound",
        "Per-sound scores from the acoustic model, expressed against your own recent "
        "readings rather than against other people.",
    ),
}

# The one family whose numbers rest on a language model's labelling, and the measured
# quality of that labelling. Carried onto the screen rather than left in a decision
# document: the rate is a count of rows and is exact, but the categories those rows are
# grouped by came from a model that filed roughly half of them correctly.
ACCURACY_CAVEAT = (
    "The rate is counted from stored corrections and is exact. The categories those "
    "corrections are filed under were proposed by a language model whose labelling "
    "measured 0.50 precision on this project's hand-checked set — so read the total as a "
    "measurement and the split by category as an indication. Corrections sitting on "
    "words the recogniser was unsure of are excluded from every figure here."
)


def _periods_in_window(period: str, since: date, until: date) -> list[date]:
    """Every period start in the window, including the ones with no practice in them.

    Gaps are periods too. A chart drawn only from the periods that have data compresses
    a fortnight of silence into the space between two adjacent points, which reads as
    continuous practice.
    """
    step = timedelta(days=7 if period == "week" else 1)
    starts: list[date] = []
    cursor = period_start(since, period)
    last = period_start(until, period)
    while cursor <= last:
        starts.append(cursor)
        cursor += step
    return starts


def _value(snapshot: ProgressSnapshot, metric: Metric) -> float | None:
    """One metric out of one snapshot, or None if this period has no reading of it."""
    if metric.family == "pronunciation" and metric.key == "mean_z":
        return _mean_z(snapshot)
    family = getattr(snapshot, metric.family) or {}
    raw = family.get(metric.key)
    return None if raw is None else float(raw)


def _mean_z(snapshot: ProgressSnapshot) -> float | None:
    """This period's average distance from the speaker's own baseline, across sounds.

    Only sounds that had a baseline to be compared against, which in a first month is
    none of them. Averaging in the sounds with no baseline as if they were zero would
    draw a speaker sitting exactly on a baseline that does not exist.
    """
    phones = ((snapshot.pronunciation or {}).get("phones") or {}).values()
    scores = [phone["z"] for phone in phones if phone.get("z") is not None]
    return round(sum(scores) / len(scores), 3) if scores else None


def _samples(snapshot: ProgressSnapshot, metric: Metric) -> int:
    """What this metric's gate is applied to: words for speech, phones for sound."""
    counts = snapshot.sample_counts or {}
    if metric.family == "pronunciation":
        return int(counts.get("phones") or 0)
    return int(counts.get("words") or 0)


def _series(
    metric: Metric,
    snapshots: dict[date, ProgressSnapshot],
    starts: list[date],
    enough_readings: bool,
) -> Series:
    points: list[Point] = []
    best_sample = 0

    for start in starts:
        snapshot = snapshots.get(start)
        if snapshot is None:
            points.append(Point(start=start, withheld="nothing recorded"))
            continue

        samples = _samples(snapshot, metric)
        best_sample = max(best_sample, samples)
        floor = 0 if metric.family == "pronunciation" else PROGRESS_MIN_WORDS

        if samples < floor:
            points.append(
                Point(
                    start=start,
                    samples=samples,
                    withheld=f"only {samples} words — a rate needs {floor}",
                )
            )
            continue

        value = _value(snapshot, metric)
        points.append(
            Point(
                start=start,
                value=value,
                samples=samples,
                withheld=None if value is not None else "not measured in this period",
            )
        )

    measured = [point for point in points if point.value is not None]

    if metric.family == "pronunciation" and not enough_readings:
        gate = Gate(
            shown=False,
            reason=(
                "Pronunciation scores move with the microphone and the room, so a trend "
                "needs a few readings behind it before it says anything about you."
            ),
            have=0,
            need=PROGRESS_MIN_ATTEMPTS,
        )
    elif measured:
        gate = Gate(shown=True, have=len(measured), need=1)
    else:
        gate = Gate(
            shown=False,
            reason=(
                f"No period yet has {PROGRESS_MIN_WORDS} words in it"
                if metric.family != "pronunciation"
                else "No period yet has a score for this"
            )
            + (f" — the most any has is {best_sample}." if best_sample else "."),
            have=best_sample,
            need=PROGRESS_MIN_WORDS if metric.family != "pronunciation" else 1,
        )

    change: float | None = None
    direction: str | None = None
    if metric.better and len(measured) >= PROGRESS_MIN_POINTS:
        change = round(measured[-1].value - measured[0].value, 3)
        if change == 0:
            direction = "flat"
        else:
            improving = (change > 0) == (metric.better == "higher")
            direction = "improving" if improving else "slipping"

    return Series(
        metric=metric.key,
        label=metric.label,
        unit=metric.unit,
        better=metric.better,
        points=points,
        gate=gate,
        change=change,
        direction=direction,
    )


def _phone_trends(
    snapshots: dict[date, ProgressSnapshot], starts: list[date]
) -> list[PhoneTrend]:
    """The most recent reading of each sound, worst first.

    The latest period that has any, rather than an average across the window: a learner
    working on one sound wants to know where it is now, and averaging four weeks of it
    together hides the week they fixed it.
    """
    for start in reversed(starts):
        snapshot = snapshots.get(start)
        if snapshot is None:
            continue
        phones = (snapshot.pronunciation or {}).get("phones") or {}
        samples = (snapshot.sample_counts or {}).get("phone_samples") or {}
        trends = [
            PhoneTrend(
                phone=phone,
                mean_gop=values["mean_gop"],
                z=values.get("z"),
                baseline_mean=values.get("baseline_mean"),
                baseline_readings=values.get("baseline_readings", 0),
                samples=int(samples.get(phone, 0)),
            )
            for phone, values in phones.items()
            if int(samples.get(phone, 0)) >= PROGRESS_MIN_PHONE_SAMPLES
        ]
        if trends:
            # Worst first: by distance from the speaker's own baseline where there is
            # one, and by raw score where there is not. Sorting the two together on the
            # raw score would rank a sound that is merely difficult above one that has
            # actually got worse.
            trends.sort(
                key=lambda trend: (
                    trend.z if trend.z is not None else 0,
                    trend.mean_gop,
                )
            )
            return trends
    return []


def _repertoire(
    snapshots: dict[date, ProgressSnapshot], starts: list[date]
) -> Repertoire:
    """The forms used most recently, and a warning when the range of them narrowed.

    The warning fires on one specific combination — fewer forms *and* fewer errors —
    because that is the one a chart would otherwise render as unambiguous progress.
    """
    measured = [
        (start, snapshots[start])
        for start in starts
        if start in snapshots
        and int((snapshots[start].sample_counts or {}).get("words") or 0)
        >= PROGRESS_MIN_WORDS
    ]
    if not measured:
        return Repertoire()

    start, latest = measured[-1]
    complexity = latest.complexity or {}
    repertoire = Repertoire(
        latest_period=start,
        forms=dict(complexity.get("by_form") or {}),
        distinct_forms=int(complexity.get("distinct_forms") or 0),
    )

    if len(measured) < 2:
        return repertoire

    _, previous = measured[-2]
    before = int((previous.complexity or {}).get("distinct_forms") or 0)
    repertoire.previous_distinct_forms = before

    errors_now = (latest.accuracy or {}).get("errors_per_100_words")
    errors_before = (previous.accuracy or {}).get("errors_per_100_words")
    narrowed = repertoire.distinct_forms < before
    safer = (
        errors_now is not None
        and errors_before is not None
        and errors_now < errors_before
    )
    if narrowed and safer:
        repertoire.warning = (
            f"You used {repertoire.distinct_forms} different forms, down from {before}, "
            f"and your error rate fell from {errors_before} to {errors_now} per 100 "
            "words. Fewer mistakes across a narrower range is not the same as improving "
            "— it is what sticking to what you already know looks like on a chart."
        )
    return repertoire


async def build(
    db: AsyncSession, user_id: int, period: str = "week", days: int | None = None
) -> ProgressOut:
    """The whole progress page for one user, read from snapshots and nothing else."""
    if period not in PERIODS:
        raise ValueError(f"unknown period {period!r}")

    window = days or PROGRESS_TREND_DAYS
    until = date.today()
    since = until - timedelta(days=window)
    starts = _periods_in_window(period, since, until)

    rows = (
        await db.scalars(
            select(ProgressSnapshot)
            .where(
                ProgressSnapshot.user_id == user_id,
                ProgressSnapshot.period == period,
                ProgressSnapshot.period_start >= starts[0],
                ProgressSnapshot.period_start <= starts[-1],
            )
            .order_by(ProgressSnapshot.period_start)
        )
    ).all()
    snapshots = {row.period_start: row for row in rows}

    totals = ProgressTotals(periods=len(rows))
    for row in rows:
        counts = row.sample_counts or {}
        totals.sessions += int(counts.get("sessions") or 0)
        totals.turns += int(counts.get("turns") or 0)
        totals.words += int(counts.get("words") or 0)
        totals.attempts += int(counts.get("attempts") or 0)
        totals.phones += int(counts.get("phones") or 0)

    enough_readings = totals.attempts >= PROGRESS_MIN_ATTEMPTS

    families = []
    for name, (label, description) in FAMILY_LABELS.items():
        families.append(
            Family(
                name=name,
                label=label,
                description=description,
                caveat=ACCURACY_CAVEAT if name == "accuracy" else None,
                series=[
                    _series(metric, snapshots, starts, enough_readings)
                    for metric in METRICS
                    if metric.family == name
                ],
            )
        )

    phone_gate = (
        Gate(shown=True, have=totals.attempts, need=PROGRESS_MIN_ATTEMPTS)
        if enough_readings
        else Gate(
            shown=False,
            reason=(
                f"{totals.attempts} scored reading"
                f"{'' if totals.attempts == 1 else 's'} so far. Per-sound trends start "
                f"at {PROGRESS_MIN_ATTEMPTS}, because the first few readings describe "
                "your microphone as much as your mouth."
            ),
            have=totals.attempts,
            need=PROGRESS_MIN_ATTEMPTS,
        )
    )

    return ProgressOut(
        period=period,
        since=starts[0],
        until=until,
        totals=totals,
        families=families,
        phones=_phone_trends(snapshots, starts) if enough_readings else [],
        phone_gate=phone_gate,
        repertoire=_repertoire(snapshots, starts),
        stale=await is_stale(db, user_id),
    )
