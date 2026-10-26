"""The progress page's writing lines: how often English was asked for, and how the person
wrote it themselves.

Four series over the same periods as the rest of the page, each a count of rows:
captures, attempts, counted written mistakes per hundred written words, and the share of
attempts with none. If the first falls while the third falls too, the person needs the
English less and writes it better without it.

**Counted on read, not materialised.** They are counts over two small tables, kept out of
the snapshots so that the rollups behind every spoken figure stay exactly as they are; a
written mistake lives in `written_errors` and no spoken line reads that table. The rate
and the share have the floor the spoken rates have: a period with fewer words written is
a hole with its reason.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import ERROR_CONFIDENCE_FLOOR, PROGRESS_MIN_POINTS, PROGRESS_MIN_WORDS
from db_models import Capture, CaptureAttempt, WrittenError
from models.progress import Gate, Point, Series, Writing, WritingTotals
from services.rollup import period_start

CAVEAT = (
    "A capture is one release of fn, one Enter in the panel, or one translation or check "
    "of something you copied, while saving is on. A written mistake counts when the "
    "dictionary finds a misspelling, or when the grammar rules or the language model "
    "propose it inside the closed list of mistake types, at or above the confidence floor "
    "speech uses. Mistakes in English you typed count; English you said is shown on the "
    "panel and never counted here, because speech is measured in conversations. No model "
    "draws any of these lines: each is a count of stored rows."
)


def _day(moment: datetime) -> date:
    return moment.astimezone(timezone.utc).date() if moment.tzinfo else moment.date()


def _counts_series(
    metric: str, label: str, unit: str, counts: dict, starts: list[date]
) -> Series:
    points = [
        Point(
            start=start, value=float(counts.get(start, 0)), samples=counts.get(start, 0)
        )
        for start in starts
    ]
    total = sum(counts.values())
    return Series(
        metric=metric,
        label=label,
        unit=unit,
        points=points,
        gate=(
            Gate(shown=True, have=total, need=1)
            if total
            else Gate(shown=False, reason="Nothing yet in this window.", have=0, need=1)
        ),
    )


def _rate_series(
    metric: str,
    label: str,
    unit: str,
    better: str,
    values: dict[date, float],
    words: dict[date, int],
    starts: list[date],
) -> Series:
    points = []
    for start in starts:
        written = words.get(start, 0)
        if written == 0:
            points.append(Point(start=start, withheld="nothing written yourself"))
        elif written < PROGRESS_MIN_WORDS:
            points.append(
                Point(
                    start=start,
                    samples=written,
                    withheld=f"only {written} words — a rate needs {PROGRESS_MIN_WORDS}",
                )
            )
        else:
            points.append(Point(start=start, value=values[start], samples=written))
    measured = [p for p in points if p.value is not None]
    best = max(words.values(), default=0)
    gate = (
        Gate(shown=True, have=len(measured), need=1)
        if measured
        else Gate(
            shown=False,
            reason=f"No period yet has {PROGRESS_MIN_WORDS} words written yourself"
            + (f" — the most any has is {best}." if best else "."),
            have=best,
            need=PROGRESS_MIN_WORDS,
        )
    )
    change = direction = None
    if len(measured) >= PROGRESS_MIN_POINTS:
        change = round(measured[-1].value - measured[0].value, 3)
        if change == 0:
            direction = "flat"
        else:
            direction = (
                "improving" if (change > 0) == (better == "higher") else "slipping"
            )
    return Series(
        metric=metric,
        label=label,
        unit=unit,
        better=better,
        points=points,
        gate=gate,
        change=change,
        direction=direction,
    )


async def build(
    db: AsyncSession, user_id: int, period: str, starts: list[date]
) -> Writing:
    """The four lines over the window that starts at `starts[0]`."""
    since = datetime.combine(starts[0], time.min, tzinfo=timezone.utc)
    step = timedelta(days=7 if period == "week" else 1)
    last = starts[-1] + step

    captured: dict[date, int] = {}
    for moment in (
        await db.scalars(
            select(Capture.created_at).where(
                Capture.user_id == user_id, Capture.created_at >= since
            )
        )
    ).all():
        start = period_start(_day(moment), period)
        if start < last:
            captured[start] = captured.get(start, 0) + 1

    counted_errors = func.count(WrittenError.id).filter(
        WrittenError.confidence >= ERROR_CONFIDENCE_FLOOR
    )
    rows = (
        await db.execute(
            select(CaptureAttempt.created_at, CaptureAttempt.word_count, counted_errors)
            .join(Capture, Capture.id == CaptureAttempt.capture_id)
            .outerjoin(WrittenError, WrittenError.attempt_id == CaptureAttempt.id)
            .where(Capture.user_id == user_id, CaptureAttempt.created_at >= since)
            .group_by(CaptureAttempt.id)
        )
    ).all()
    attempts: dict[date, int] = {}
    words: dict[date, int] = {}
    mistakes: dict[date, int] = {}
    clean: dict[date, int] = {}
    for moment, word_count, errors in rows:
        start = period_start(_day(moment), period)
        if start >= last:
            continue
        attempts[start] = attempts.get(start, 0) + 1
        words[start] = words.get(start, 0) + word_count
        mistakes[start] = mistakes.get(start, 0) + errors
        clean[start] = clean.get(start, 0) + (errors == 0)

    rate = {
        start: round(mistakes.get(start, 0) * 100 / words[start], 2)
        for start in words
        if words[start]
    }
    share = {start: round(clean[start] / attempts[start], 3) for start in attempts}
    return Writing(
        label="Writing on your own",
        description="How often you asked SpeakLab for English, and how you wrote it "
        "yourself afterwards. Counted apart from speech.",
        series=[
            _counts_series(
                "captures", "asked for English", "captures", captured, starts
            ),
            _counts_series(
                "attempts", "written on your own", "attempts", attempts, starts
            ),
            _rate_series(
                "written_errors_per_100_words",
                "mistakes in what you wrote",
                "per 100 words",
                "lower",
                rate,
                words,
                starts,
            ),
            _rate_series(
                "clean_share",
                "written with no counted mistake",
                "share of attempts",
                "higher",
                share,
                words,
                starts,
            ),
        ],
        totals=WritingTotals(
            captures=sum(captured.values()),
            attempts=sum(attempts.values()),
            words=sum(words.values()),
            counted=sum(mistakes.values()),
        ),
        caveat=CAVEAT,
    )
