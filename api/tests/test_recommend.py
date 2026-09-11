"""What to practise next: the ranking, and the reason attached to every entry.

The two properties worth having are that it is **deterministic** — the same stored rows
produce the same order, so a page refresh is not a different opinion — and that every
suggestion carries a number a learner can go and check. A recommendation whose reason
cannot be traced back to something the system measured is indistinguishable from a guess,
and this product's whole claim is that it does not guess.

The third is about honesty at the bottom of the scale. Everything here still ranks
correctly on three observations; it just should not be trusted, and the response has to
say which situation the reader is in.
"""

from datetime import date, timedelta

import pytest

from config import RECOMMEND_LIMIT
from db_models import ProgressSnapshot
from services.recommend import build
from services.rollup import period_start

THIS_WEEK = period_start(date.today(), "week")


def week(offset: int) -> date:
    return THIS_WEEK - timedelta(days=7 * offset)


def snapshot(
    user_id: int,
    start: date = THIS_WEEK,
    *,
    words: int = 400,
    categories: dict | None = None,
    forms: dict | None = None,
    phones: dict | None = None,
    phone_samples: dict | None = None,
    attempts: int = 0,
) -> ProgressSnapshot:
    return ProgressSnapshot(
        user_id=user_id,
        period="week",
        period_start=start,
        fluency={"words_spoken": words},
        accuracy={
            "errors_per_100_words": 4.0,
            "by_category": categories if categories is not None else {"VERB_TENSE": 6},
            "excluded": {"asr_suspect": 0, "low_confidence": 0},
        },
        complexity={
            "distinct_forms": len(forms or {}),
            "form_instances": sum((forms or {}).values()),
            "by_form": forms or {},
            "subordination_index": 0.3,
        },
        pronunciation={"phones": phones or {}, "mean_gop": -2.0},
        sample_counts={
            "turns": 6,
            "words": words,
            "sessions": 2,
            "attempts": attempts,
            "phones": sum((phone_samples or {}).values()),
            "phone_samples": phone_samples or {},
            "errors_counted": sum((categories or {"VERB_TENSE": 6}).values()),
            "errors_excluded": 0,
            "devices": [],
        },
    )


@pytest.fixture
async def learner(db_session, seeded):
    from db_models import User
    from services.security import hash_password
    from tests.conftest import unique_email

    user = User(
        email=unique_email("recommend"),
        password_hash=hash_password("practice-makes-permanent"),
        native_language="es",
    )
    db_session.add(user)
    await db_session.commit()
    return user


def kinds(result) -> list[str]:
    return [item.kind for item in result.items]


# ── Nothing to go on ────────────────────────────────────────────────────────


async def test_an_account_with_no_practice_is_told_where_to_start(learner, db_session):
    """Not an empty list. Somebody who has just registered is exactly the person a
    recommendation is for, and "no data" is a sentence about the system rather than an
    answer to their question."""
    result = await build(db_session, learner.id)

    assert kinds(result) == ["practise"]
    assert result.confidence == "none"
    assert "scenario" in result.items[0].reason


# ── Where a suggestion comes from ───────────────────────────────────────────


async def test_the_most_frequent_error_category_leads(learner, db_session):
    db_session.add(
        snapshot(learner.id, categories={"VERB_TENSE": 9, "ARTICLE": 1}, words=300)
    )
    await db_session.commit()

    result = await build(db_session, learner.id)
    top = result.items[0]

    assert top.kind == "error_category"
    assert top.title == "verb tense"
    assert top.samples == 9
    assert top.measured == 3.0


async def test_a_kind_of_mistake_points_at_a_scenario_written_to_draw_it_out(
    learner, db_session
):
    """Where a scenario declares the category, the suggestion links to it; where none
    does, it links nowhere rather than to a scenario that happens to be first."""
    db_session.add(
        snapshot(learner.id, categories={"ARTICLE": 5, "PRONOUN": 5}, words=300)
    )
    await db_session.commit()

    result = await build(db_session, learner.id)
    by_title = {
        item.title: item for item in result.items if item.kind == "error_category"
    }

    assert by_title["article"].scenario_slug == "lost-property-office"
    assert by_title["pronoun"].scenario_slug is None


async def test_every_suggestion_states_the_measurement_that_chose_it(
    learner, db_session
):
    """The property that separates this from a guess. Each reason has to carry a number
    the learner could go and count for themselves."""
    db_session.add(
        snapshot(
            learner.id,
            categories={"VERB_TENSE": 6},
            forms={"present_simple": 20},
            phones={"TH": {"mean_gop": -6.0, "z": -1.9, "baseline_readings": 4}},
            phone_samples={"TH": 30},
            attempts=5,
        )
    )
    await db_session.commit()

    result = await build(db_session, learner.id)

    assert result.items
    for item in result.items:
        assert item.reason.strip()
        assert any(character.isdigit() for character in item.reason), item.reason


async def test_a_form_never_produced_is_suggested_with_a_scenario_that_asks_for_it(
    learner, db_session
):
    """Advice with nowhere to act on it is not advice. The candidate pool is what the
    catalogue actually declares, not the parser's whole vocabulary."""
    db_session.add(
        snapshot(learner.id, categories={}, forms={"present_simple": 30}, words=400)
    )
    await db_session.commit()

    result = await build(db_session, learner.id)
    forms = [item for item in result.items if item.kind == "unused_form"]

    assert forms
    assert all(item.scenario_slug for item in forms)
    assert all("Not once" in item.reason for item in forms)


async def test_a_weak_sound_is_suggested_with_a_passage_that_drills_it(
    learner, db_session
):
    db_session.add(
        snapshot(
            learner.id,
            categories={},
            forms={form: 30 for form in ("present_simple",)},
            phones={"TH": {"mean_gop": -7.0, "z": -2.2, "baseline_readings": 4}},
            phone_samples={"TH": 30},
            attempts=5,
        )
    )
    await db_session.commit()

    result = await build(db_session, learner.id)
    sounds = [item for item in result.items if item.kind == "weak_phone"]

    assert sounds
    assert sounds[0].title == "the /TH/ sound"
    assert sounds[0].passage_slug == "third-street-theatre"
    assert "standard deviations" in sounds[0].reason


async def test_a_sound_with_no_baseline_says_so_rather_than_claiming_a_direction(
    learner, db_session
):
    """Without earlier readings the raw score is all there is, and it is partly a fact
    about the microphone. The suggestion is still made and the limit is stated."""
    db_session.add(
        snapshot(
            learner.id,
            categories={},
            phones={"TH": {"mean_gop": -7.0, "z": None, "baseline_readings": 0}},
            phone_samples={"TH": 30},
            attempts=5,
        )
    )
    await db_session.commit()

    result = await build(db_session, learner.id)
    sound = next(item for item in result.items if item.kind == "weak_phone")

    assert "no baseline" in sound.reason
    assert "getting better" in sound.reason


async def test_a_sound_with_too_few_instances_is_not_ranked(learner, db_session):
    db_session.add(
        snapshot(
            learner.id,
            categories={},
            phones={"ZH": {"mean_gop": -9.0, "z": -4.0, "baseline_readings": 4}},
            phone_samples={"ZH": 2},
            attempts=5,
        )
    )
    await db_session.commit()

    result = await build(db_session, learner.id)
    assert "weak_phone" not in kinds(result)


async def test_a_sound_scoring_above_its_own_baseline_is_not_something_to_practise(
    learner, db_session
):
    """A positive z is an improvement. Recommending it would be advice against the
    evidence, and it would push a real weakness off a list of three."""
    db_session.add(
        snapshot(
            learner.id,
            categories={},
            phones={"TH": {"mean_gop": -3.0, "z": 1.4, "baseline_readings": 4}},
            phone_samples={"TH": 30},
            attempts=5,
        )
    )
    await db_session.commit()

    result = await build(db_session, learner.id)
    assert "weak_phone" not in kinds(result)


# ── The ranking itself ──────────────────────────────────────────────────────


async def test_the_same_rows_produce_the_same_ranking(learner, db_session):
    """A page refresh must not be a different opinion. Ties are broken by name rather
    than by whatever order the database returned."""
    db_session.add(
        snapshot(
            learner.id,
            categories={"VERB_TENSE": 4, "ARTICLE": 4},
            forms={"present_simple": 10},
            phones={"TH": {"mean_gop": -6.0, "z": -1.5, "baseline_readings": 4}},
            phone_samples={"TH": 30},
            attempts=5,
        )
    )
    await db_session.commit()

    first = await build(db_session, learner.id)
    second = await build(db_session, learner.id)

    assert [item.model_dump() for item in first.items] == [
        item.model_dump() for item in second.items
    ]


async def test_no_more_than_the_configured_number_are_returned(learner, db_session):
    """Long enough to offer a choice, short enough that every entry has a reason worth
    reading."""
    db_session.add(
        snapshot(
            learner.id,
            categories={"VERB_TENSE": 6, "ARTICLE": 4, "PREPOSITION": 3, "PRONOUN": 2},
            forms={},
            phones={"TH": {"mean_gop": -6.0, "z": -1.5, "baseline_readings": 4}},
            phone_samples={"TH": 30},
            attempts=5,
        )
    )
    await db_session.commit()

    result = await build(db_session, learner.id)
    assert len(result.items) == RECOMMEND_LIMIT


async def test_older_evidence_is_worth_less_than_recent_evidence(learner, db_session):
    """A weakness measured four weeks ago is still the best guess available about somebody
    who has not practised since — worth less than this week's, and never worth nothing.
    """
    old = snapshot(learner.id, week(4), categories={"VERB_TENSE": 6})
    db_session.add(old)
    await db_session.commit()
    aged = await build(db_session, learner.id, days=60)

    await db_session.delete(old)
    db_session.add(snapshot(learner.id, THIS_WEEK, categories={"VERB_TENSE": 6}))
    await db_session.commit()
    fresh = await build(db_session, learner.id, days=60)

    assert 0 < aged.items[0].score < fresh.items[0].score


# ── How much to trust it ────────────────────────────────────────────────────


async def test_thin_evidence_is_reported_as_thin(learner, db_session):
    db_session.add(snapshot(learner.id, words=40, categories={"VERB_TENSE": 2}))
    await db_session.commit()

    result = await build(db_session, learner.id)

    assert result.confidence == "low"
    assert "not enough to be sure" in result.detail


async def test_a_month_of_real_practice_is_reported_as_moderate(learner, db_session):
    for offset in (1, 0):
        db_session.add(
            snapshot(learner.id, week(offset), words=300, categories={"VERB_TENSE": 6})
        )
    await db_session.commit()

    result = await build(db_session, learner.id)

    assert result.confidence == "moderate"
    assert "300" not in result.detail or "600" in result.detail


async def test_the_confidence_never_claims_more_than_the_sample_counts_support(
    learner, db_session
):
    """`good` needs both a lot of speech and a real number of scored readings. It is the
    one label on this response that could be read as "the system is sure"."""
    db_session.add(snapshot(learner.id, words=5000, attempts=0))
    await db_session.commit()

    assert (await build(db_session, learner.id)).confidence != "good"
