"""What to practise next, and the measurement that chose it.

**A transparent weighted score, and no model anywhere near it.** Three sources — the error
categories that come up most, the forms this speaker never reaches for, and the sounds
that score worst against their own baseline — each normalised within itself, weighted, and
decayed by how old the evidence is. The arithmetic is a dozen lines and every suggestion
carries the number it came from.

**Why not something cleverer.** A learned ranker would need training data this project
does not have and could not explain the result if it had it. The whole value of a
recommendation here is that a learner can check it: *"six verb-tense corrections in a
hundred and twenty words"* is a claim they can go and look at. A score with no traceable
reason is indistinguishable from a guess, and a guess dressed as a measurement is the
thing this system exists not to do.

**Thin evidence is reported, not hidden.** Everything below still ranks correctly on three
observations; it just should not be trusted. `confidence` says which situation the reader
is in, and it is computed from the same sample counts the charts are gated on.
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import (
    PROGRESS_MIN_ATTEMPTS,
    PROGRESS_MIN_PHONE_SAMPLES,
    PROGRESS_MIN_WORDS,
    PROGRESS_TREND_DAYS,
    RECOMMEND_LIMIT,
)
from db_models import Passage, ProgressSnapshot, Scenario
from models.progress import Recommendation, RecommendationsOut

# What each kind of evidence is worth, before severity and age are applied.
#
# Errors lead because a correction is the most concrete thing this system knows about a
# speaker. Sounds come next: a phone score rests on an acoustic model that heard the
# waveform, which is a stronger claim than anything read off a transcript. Unused forms
# come last because "you have not said this" is an absence, and an absence has more
# innocent explanations than the other two — nobody asked, or it did not come up.
WEIGHTS: dict[str, float] = {
    "error_category": 1.0,
    "weak_phone": 0.9,
    "unused_form": 0.8,
}

# How much a suggestion loses for resting on old evidence. Practice from this week counts
# fully; practice at the far edge of the window counts half. It never falls to zero — a
# weakness measured a month ago is still the best guess available about a speaker who has
# not practised since.
RECENCY_FLOOR = 0.5

# Instances of a form before it stops counting as neglected. Below this the suggestion is
# scaled rather than dropped, so a form used once still outranks one used four times.
FORM_FAMILIARITY = 5

_READABLE = str.maketrans({"_": " "})


def readable(name: str) -> str:
    """`present_perfect` and `VERB_TENSE` both become something a learner can read."""
    return name.lower().translate(_READABLE)


def _recency(evidence_day: date | None, until: date, window: int) -> float:
    """1.0 for this week's evidence, falling to RECENCY_FLOOR at the window's edge."""
    if evidence_day is None:
        return RECENCY_FLOOR
    age = max(0, (until - evidence_day).days)
    if age <= 7 or window <= 7:
        return 1.0
    fraction = min(1.0, (age - 7) / (window - 7))
    return 1.0 - (1.0 - RECENCY_FLOOR) * fraction


def _normalise(values: list[float]) -> list[float]:
    """Scale within a kind so three sources of different units can be compared.

    Relative to the largest value rather than to a range, because the bottom of each of
    these scales is a real zero — no errors of that category, a sound at its own baseline
    — and stretching the smallest observation to 0 would make the mildest weakness in a
    list of three look like no weakness at all.
    """
    top = max(values, default=0.0)
    return [value / top if top > 0 else 0.0 for value in values]


async def build(
    db: AsyncSession, user_id: int, days: int | None = None
) -> RecommendationsOut:
    """Rank what this speaker should practise next, from their own stored snapshots."""
    window = days or PROGRESS_TREND_DAYS
    until = date.today()
    since = until - timedelta(days=window)

    # The weekly rows, because they are the ones with enough speech in them to rank
    # anything. Daily rows over the same window would double-count every turn.
    snapshots = list(
        (
            await db.scalars(
                select(ProgressSnapshot)
                .where(
                    ProgressSnapshot.user_id == user_id,
                    ProgressSnapshot.period == "week",
                    ProgressSnapshot.period_start >= since - timedelta(days=7),
                )
                .order_by(ProgressSnapshot.period_start)
            )
        ).all()
    )

    words = sum(int((row.sample_counts or {}).get("words") or 0) for row in snapshots)
    attempts = sum(
        int((row.sample_counts or {}).get("attempts") or 0) for row in snapshots
    )

    items: list[Recommendation] = []
    items += await _from_errors(db, snapshots, until, window)
    items += await _from_phones(db, snapshots, until, window)
    items += await _from_forms(db, snapshots, until, window, words)

    items.sort(key=lambda item: (-item.score, item.kind, item.title))
    chosen = items[:RECOMMEND_LIMIT]

    if not chosen:
        return RecommendationsOut(
            items=[
                Recommendation(
                    kind="practise",
                    title="Have a conversation",
                    reason=(
                        "There is nothing measured to go on yet. A scenario produces "
                        "corrections, forms and timings in one sitting, which is what "
                        "everything on this page is built from."
                    ),
                )
            ],
            confidence="none",
            detail="Nothing has been analysed for this account yet.",
        )

    return RecommendationsOut(
        items=chosen, **_confidence(words, attempts, len(snapshots))
    )


def _confidence(words: int, attempts: int, periods: int) -> dict:
    """How much the ranking above should be trusted, in the same units the gates use."""
    if words >= PROGRESS_MIN_WORDS * 10 and attempts >= PROGRESS_MIN_ATTEMPTS * 2:
        return {"confidence": "good", "detail": None}
    if words >= PROGRESS_MIN_WORDS * 2 and periods >= 2:
        return {
            "confidence": "moderate",
            "detail": (
                f"Based on {words} words across {periods} weeks. The ranking is right "
                "about the order; the sizes are still moving."
            ),
        }
    return {
        "confidence": "low",
        "detail": (
            f"Based on {words} words and {attempts} scored reading"
            f"{'' if attempts == 1 else 's'}. That is enough to notice a pattern and "
            "not enough to be sure of one — practise a few more times and these will "
            "change."
        ),
    }


async def _from_errors(
    db: AsyncSession, snapshots: list[ProgressSnapshot], until: date, window: int
) -> list[Recommendation]:
    """The categories this speaker is corrected on most, per hundred words."""
    totals: dict[str, int] = {}
    latest: dict[str, date] = {}
    words = 0

    for row in snapshots:
        words += int((row.sample_counts or {}).get("words") or 0)
        for category, count in ((row.accuracy or {}).get("by_category") or {}).items():
            totals[category] = totals.get(category, 0) + int(count)
            latest[category] = row.period_start

    if not totals or not words:
        return []

    rates = {
        category: count * 100 / words for category, count in sorted(totals.items())
    }
    scaled = dict(zip(rates, _normalise(list(rates.values())), strict=True))

    # "Your most frequent" only when one category actually is. Two tied at the top would
    # otherwise both claim it, which reads as a system that has not looked at its own
    # numbers — and on a corpus this size ties are the normal case, not the edge one.
    top = max(totals.values())
    alone = sum(1 for count in totals.values() if count == top) == 1

    return [
        Recommendation(
            kind="error_category",
            title=readable(category),
            reason=(
                f"{totals[category]} correction"
                f"{'' if totals[category] == 1 else 's'} in {words} words — "
                f"{rate:.1f} per 100 words"
                + (
                    ", your most frequent category."
                    if alone and totals[category] == top
                    else "."
                )
            ),
            measured=round(rate, 2),
            samples=totals[category],
            score=round(
                WEIGHTS["error_category"]
                * scaled[category]
                * _recency(latest.get(category), until, window),
                4,
            ),
        )
        for category, rate in rates.items()
    ]


async def _from_phones(
    db: AsyncSession, snapshots: list[ProgressSnapshot], until: date, window: int
) -> list[Recommendation]:
    """The sounds scoring worst, with a passage that drills them.

    Only sounds with enough instances behind them, and only from the most recent period
    that has any: a sound the speaker fixed last week should not be recommended because
    of how it went a month ago.
    """
    # Gated on instances of the sound, not on the number of readings the *chart* waits
    # for. The two answer different questions: a trend needs several readings because it
    # claims a change over time, and this claims only where a sound sits today relative
    # to the speaker's others. Fifty instances in one reading is enough to say that, and
    # the reason says what it does not cover.
    for row in reversed(snapshots):
        phones = (row.pronunciation or {}).get("phones") or {}
        samples = (row.sample_counts or {}).get("phone_samples") or {}
        scored = {
            phone: values
            for phone, values in phones.items()
            if int(samples.get(phone, 0)) >= PROGRESS_MIN_PHONE_SAMPLES
        }
        if not scored:
            continue

        # Severity is how far below the speaker's own baseline the sound sits, where
        # there is a baseline. Where there is not — a first month — the raw score is the
        # only signal available, and it is used with the weakness that implies: it is
        # partly a fact about the microphone.
        severity = {
            phone: (
                -values["z"]
                if values.get("z") is not None
                else -values["mean_gop"] / 10
            )
            for phone, values in scored.items()
        }
        positive = {phone: max(0.0, value) for phone, value in severity.items()}
        if not any(positive.values()):
            return []

        scaled = dict(zip(positive, _normalise(list(positive.values())), strict=True))
        drills = await _passages_for(db, list(scored))

        return [
            Recommendation(
                kind="weak_phone",
                title=f"the /{phone}/ sound",
                reason=(
                    f"{samples.get(phone, 0)} instances scored, "
                    + (
                        f"{values['z']:+.1f} standard deviations from your own recent "
                        "readings of it."
                        if values.get("z") is not None
                        else f"scoring {values['mean_gop']:.1f}, among the weakest of "
                        "the sounds in your readings so far. There is no baseline for "
                        "this one yet, so that places it against your other sounds "
                        "today rather than saying whether it is getting better — and no "
                        "pass mark is calibrated, so it is a ranking, not a verdict."
                    )
                ),
                measured=values.get("z", values["mean_gop"]),
                samples=int(samples.get(phone, 0)),
                passage_slug=drills.get(phone),
                score=round(
                    WEIGHTS["weak_phone"]
                    * scaled[phone]
                    * _recency(row.period_start, until, window),
                    4,
                ),
            )
            for phone, values in scored.items()
            if positive[phone] > 0
        ]
    return []


async def _from_forms(
    db: AsyncSession,
    snapshots: list[ProgressSnapshot],
    until: date,
    window: int,
    words: int,
) -> list[Recommendation]:
    """Forms the product offers practice in that this speaker has not reached for.

    The candidate pool is what the scenarios actually declare, not the parser's whole
    vocabulary. Recommending a form nothing in the catalogue is built to elicit would be
    advice with nowhere to act on it.
    """
    if not words:
        return []

    used: dict[str, int] = {}
    for row in snapshots:
        for form, count in ((row.complexity or {}).get("by_form") or {}).items():
            used[form] = used.get(form, 0) + int(count)

    scenarios = list(
        (
            await db.scalars(
                select(Scenario)
                .where(Scenario.is_active.is_(True))
                .order_by(Scenario.slug)
            )
        ).all()
    )

    offered: dict[str, str] = {}
    for scenario in scenarios:
        for form in scenario.target_grammar or []:
            offered.setdefault(form, scenario.slug)

    severity = {
        form: 1.0 - min(1.0, used.get(form, 0) / FORM_FAMILIARITY)
        for form in sorted(offered)
    }
    wanted = {form: value for form, value in severity.items() if value > 0}
    if not wanted:
        return []

    scaled = dict(zip(wanted, _normalise(list(wanted.values())), strict=True))
    newest = snapshots[-1].period_start if snapshots else None

    return [
        Recommendation(
            kind="unused_form",
            title=readable(form),
            reason=(
                f"Not once in {words} words of practice."
                if used.get(form, 0) == 0
                else f"{used[form]} time{'' if used[form] == 1 else 's'} in {words} "
                "words — the scenarios that ask for it are a way to use it more."
            ),
            measured=float(used.get(form, 0)),
            samples=words,
            scenario_slug=offered[form],
            score=round(
                WEIGHTS["unused_form"] * scaled[form] * _recency(newest, until, window),
                4,
            ),
        )
        for form in wanted
    ]


async def _passages_for(db: AsyncSession, phones: list[str]) -> dict[str, str]:
    """A passage engineered around each sound, where one exists."""
    passages = list(
        (
            await db.scalars(
                select(Passage)
                .where(Passage.is_active.is_(True))
                .order_by(Passage.slug)
            )
        ).all()
    )
    drills: dict[str, str] = {}
    for passage in passages:
        for phone in passage.phoneme_focus or []:
            if phone in phones:
                drills.setdefault(phone, passage.slug)
    return drills
