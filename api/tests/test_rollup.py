"""The arithmetic that produces a snapshot, and the rules about when it may be rewritten.

Two halves. The first works on a hand-built corpus with no database in sight, because a
snapshot is a pure function of the rows underneath it and that is the property worth being
able to test directly — every number on the progress page comes through here.

The second is about the write: a rollup that is not idempotent turns a page refresh into a
different chart, and one that never deletes leaves a removed session contributing to a
trend for ever.
"""

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from db_models import (
    FluencyMetrics,
    GrammarUsage,
    LanguageError,
    PracticeSession,
    ProgressSnapshot,
    Scenario,
    Turn,
    User,
)
from services.rollup import (
    AttemptRow,
    Corpus,
    Period,
    TurnRow,
    is_stale,
    period_start,
    periods_for,
    rebuild_user,
    snapshot_values,
)
from services.security import hash_password
from tests.conftest import unique_email

MONDAY = date(2026, 8, 31)
WEEK = Period("week", MONDAY)
DAY = Period("day", MONDAY)


def measures(words: int, rate: float = 120.0, fillers: int = 2) -> FluencyMetrics:
    return FluencyMetrics(
        turn_id=0,
        word_count=words,
        speech_rate_wpm=rate,
        articulation_rate=rate + 20,
        pause_ratio=0.2,
        mean_length_run=6.0,
        filler_count=fillers,
        response_latency_ms=500,
    )


def error(category: str = "VERB_TENSE", **overrides) -> LanguageError:
    row = LanguageError(
        turn_id=0,
        category=category,
        original="I go",
        correction="I went",
        detector="llm",
        confidence=overrides.pop("confidence", 0.9),
        asr_suspect=overrides.pop("asr_suspect", False),
    )
    for name, value in overrides.items():
        setattr(row, name, value)
    return row


def turn(
    day: date = MONDAY,
    words: int = 60,
    rate: float = 120.0,
    fillers: int = 2,
    features: dict | None = None,
    errors: tuple = (),
    session_id: int = 1,
    turn_id: int = 1,
) -> TurnRow:
    return TurnRow(
        id=turn_id,
        session_id=session_id,
        day=day,
        changed_at=None,
        measures=measures(words, rate, fillers),
        features=dict(features or {}),
        errors=list(errors),
    )


def reading(day: date = MONDAY, phones: dict | None = None, **overrides) -> AttemptRow:
    return AttemptRow(
        id=overrides.pop("attempt_id", 1),
        day=day,
        changed_at=None,
        device_hint=overrides.pop("device_hint", None),
        phones=dict(phones or {"TH": (30, -4.0)}),
    )


# ── Periods ─────────────────────────────────────────────────────────────────


def test_a_week_starts_on_monday():
    assert period_start(date(2026, 9, 3), "week") == date(2026, 8, 31)
    assert period_start(date(2026, 8, 31), "week") == date(2026, 8, 31)
    assert period_start(date(2026, 9, 6), "week") == date(2026, 8, 31)
    assert period_start(date(2026, 9, 7), "week") == date(2026, 9, 7)


def test_one_day_of_practice_produces_a_row_at_both_granularities():
    """A weekly snapshot is computed from turns, not from seven daily ones. Averaging
    averages would weight a quiet Tuesday the same as a long Sunday."""
    assert periods_for({date(2026, 9, 3)}) == {
        Period("day", date(2026, 9, 3)),
        Period("week", date(2026, 8, 31)),
    }


def test_a_period_does_not_include_the_day_after_it_ends():
    assert WEEK.covers(date(2026, 9, 6)) is True
    assert WEEK.covers(date(2026, 9, 7)) is False
    assert DAY.covers(MONDAY) is True
    assert DAY.covers(MONDAY + timedelta(days=1)) is False


# ── Fluency ─────────────────────────────────────────────────────────────────


def test_fluency_is_weighted_by_how_much_was_said_in_each_turn():
    """A plain mean would let a two-word answer count as much as a sixty-word one, which
    is how a month ends up reporting a speech rate nobody spoke at."""
    corpus = Corpus(
        turns=[
            turn(words=90, rate=100.0, turn_id=1),
            turn(words=10, rate=200.0, turn_id=2),
        ]
    )
    values = snapshot_values(corpus, WEEK)

    assert values["fluency"]["words_spoken"] == 100
    assert values["fluency"]["speech_rate_wpm"] == pytest.approx(110.0)


def test_a_period_with_no_turns_has_no_fluency_rather_than_zero():
    """Zero words per minute is a claim about a speaker. Nothing recorded is not."""
    values = snapshot_values(Corpus(), WEEK)

    assert values["fluency"] == {}
    assert values["sample_counts"]["words"] == 0


def test_turns_outside_the_period_are_not_counted():
    corpus = Corpus(
        turns=[
            turn(day=MONDAY, words=60, turn_id=1),
            turn(day=MONDAY + timedelta(days=7), words=999, turn_id=2),
        ]
    )
    assert snapshot_values(corpus, WEEK)["sample_counts"]["words"] == 60


# ── Accuracy ────────────────────────────────────────────────────────────────


def test_the_error_rate_is_per_hundred_words_not_a_count():
    corpus = Corpus(turns=[turn(words=200, errors=(error(), error("ARTICLE")))])
    accuracy = snapshot_values(corpus, WEEK)["accuracy"]

    assert accuracy["errors_per_100_words"] == 1.0
    assert accuracy["by_category"] == {"ARTICLE": 1, "VERB_TENSE": 1}


def test_a_correction_on_words_the_recogniser_doubted_never_reaches_the_rate():
    """It is shown to the learner in the session it came from, and excluded here. A
    mishearing scored as a grammar error moves a trend line for the recogniser's reasons,
    which is the failure this whole gate exists to prevent."""
    corpus = Corpus(turns=[turn(words=100, errors=(error(), error(asr_suspect=True)))])
    accuracy = snapshot_values(corpus, WEEK)["accuracy"]

    assert accuracy["errors_per_100_words"] == 1.0
    assert accuracy["excluded"]["asr_suspect"] == 1


def test_a_correction_the_model_hedged_on_never_reaches_the_rate_either():
    corpus = Corpus(turns=[turn(words=100, errors=(error(), error(confidence=0.2)))])
    accuracy = snapshot_values(corpus, WEEK)["accuracy"]

    assert accuracy["errors_per_100_words"] == 1.0
    assert accuracy["excluded"]["low_confidence"] == 1


def test_the_two_exclusions_are_reported_separately():
    """One is a fact about the recogniser and the other about the labelling model. Folded
    together they would say a month was thin without saying which part to fix."""
    corpus = Corpus(
        turns=[
            turn(
                words=100,
                errors=(error(asr_suspect=True), error(confidence=0.1)),
            )
        ]
    )
    assert snapshot_values(corpus, WEEK)["accuracy"]["excluded"] == {
        "asr_suspect": 1,
        "low_confidence": 1,
    }


def test_accuracy_per_form_is_computed_from_the_forms_and_their_corrections():
    """Two turns: five present simples and two pasts said, one present simple corrected
    to a past. Right over said plus needed, per form, across the period."""
    corpus = Corpus(
        turns=[
            turn(
                features={"present_simple": 3, "past_simple": 2, "main_clause": 4},
                errors=(error(form="present_simple", corrected_form="past_simple"),),
            ),
            turn(turn_id=2, features={"present_simple": 2}),
        ]
    )
    assert snapshot_values(corpus, WEEK)["accuracy"]["by_form"] == {
        "present_simple": {
            "used": 5,
            "right": 4,
            "wrong": 1,
            "missed": 0,
            "accuracy": 0.8,
        },
        "past_simple": {
            "used": 2,
            "right": 2,
            "wrong": 0,
            "missed": 1,
            "accuracy": 0.6667,
        },
    }


def test_a_doubted_correction_never_reaches_accuracy_per_form():
    corpus = Corpus(
        turns=[
            turn(
                features={"present_simple": 2},
                errors=(
                    error(
                        form="present_simple",
                        corrected_form="past_simple",
                        asr_suspect=True,
                    ),
                ),
            )
        ]
    )
    assert snapshot_values(corpus, WEEK)["accuracy"]["by_form"] == {
        "present_simple": {
            "used": 2,
            "right": 2,
            "wrong": 0,
            "missed": 0,
            "accuracy": 1.0,
        }
    }


def test_a_period_with_no_words_has_no_rate():
    corpus = Corpus(turns=[turn(words=0, errors=(error(),))])
    assert snapshot_values(corpus, WEEK)["accuracy"]["errors_per_100_words"] is None


# ── Complexity ──────────────────────────────────────────────────────────────


def test_breadth_counts_distinct_forms_and_their_instances_separately():
    """Twelve uses of the present simple is not a wide repertoire, and one number cannot
    say both things."""
    corpus = Corpus(
        turns=[
            turn(turn_id=1, features={"present_simple": 9, "past_simple": 2}),
            turn(turn_id=2, features={"present_simple": 3, "modal_can": 1}),
        ]
    )
    complexity = snapshot_values(corpus, WEEK)["complexity"]

    assert complexity["distinct_forms"] == 3
    assert complexity["form_instances"] == 15
    assert complexity["by_form"] == {
        "modal_can": 1,
        "past_simple": 2,
        "present_simple": 12,
    }


def test_subordination_is_embedded_clauses_per_main_clause():
    corpus = Corpus(
        turns=[
            turn(
                features={
                    "main_clause": 4,
                    "subordinate_clause": 2,
                    "relative_clause": 1,
                }
            )
        ]
    )
    assert snapshot_values(corpus, WEEK)["complexity"]["subordination_index"] == 0.75


def test_speech_with_no_main_clause_has_no_ratio_rather_than_zero():
    """Zero would read as speech with no subordination in it, which is a claim. Having
    nothing to divide by is not."""
    corpus = Corpus(turns=[turn(features={"subordinate_clause": 1})])
    assert snapshot_values(corpus, WEEK)["complexity"]["subordination_index"] is None


# ── Pronunciation ───────────────────────────────────────────────────────────


def test_phone_scores_are_weighted_by_how_many_instances_each_reading_had():
    corpus = Corpus(
        attempts=[
            reading(attempt_id=1, phones={"TH": (10, -2.0)}),
            reading(attempt_id=2, phones={"TH": (30, -6.0)}),
        ]
    )
    values = snapshot_values(corpus, WEEK)

    assert values["pronunciation"]["phones"]["TH"]["mean_gop"] == pytest.approx(-5.0)
    assert values["sample_counts"]["phone_samples"]["TH"] == 40


def test_a_sound_with_no_earlier_readings_has_no_baseline_to_be_scored_against():
    corpus = Corpus(attempts=[reading(phones={"TH": (30, -4.0)})])
    phone = snapshot_values(corpus, WEEK)["pronunciation"]["phones"]["TH"]

    assert phone["z"] is None
    assert phone["baseline_readings"] == 0
    assert phone["mean_gop"] == -4.0


def test_the_baseline_is_earlier_readings_only():
    """A baseline that included this period's reading would move towards it, and the more
    unusual the reading the more of itself it would absorb."""
    earlier = MONDAY - timedelta(days=7)
    corpus = Corpus(
        attempts=[
            reading(day=earlier, attempt_id=1, phones={"TH": (30, -3.0)}),
            reading(day=earlier, attempt_id=2, phones={"TH": (30, -5.0)}),
            reading(day=MONDAY, attempt_id=3, phones={"TH": (30, -1.0)}),
        ]
    )
    phone = snapshot_values(corpus, WEEK)["pronunciation"]["phones"]["TH"]

    assert phone["baseline_readings"] == 2
    assert phone["baseline_mean"] == pytest.approx(-4.0)
    assert phone["z"] is not None and phone["z"] > 0


def test_a_thin_reading_of_a_sound_is_not_allowed_into_the_baseline():
    """Two instances of a phone inside one reading describe the two words it appeared in.
    Letting them anchor a baseline would make every later reading of that sound look like
    a dramatic change."""
    earlier = MONDAY - timedelta(days=7)
    corpus = Corpus(
        attempts=[
            reading(day=earlier, attempt_id=1, phones={"TH": (2, -3.0)}),
            reading(day=earlier, attempt_id=2, phones={"TH": (2, -5.0)}),
            reading(day=MONDAY, attempt_id=3, phones={"TH": (30, -1.0)}),
        ]
    )
    phone = snapshot_values(corpus, WEEK)["pronunciation"]["phones"]["TH"]

    assert phone["baseline_readings"] == 0
    assert phone["z"] is None


def test_the_microphones_a_period_used_are_recorded():
    """Pronunciation scores move with the recording setup, so a period that mixes two of
    them is partly a comparison of hardware. Nothing populates the column yet, so the list
    is empty in practice — it is computed so the annotation exists the day it is not."""
    corpus = Corpus(attempts=[reading(device_hint=None)])
    assert snapshot_values(corpus, WEEK)["sample_counts"]["devices"] == []

    corpus = Corpus(attempts=[reading(device_hint="usb-headset")])
    assert snapshot_values(corpus, WEEK)["sample_counts"]["devices"] == ["usb-headset"]


# ── Sample counts ───────────────────────────────────────────────────────────


def test_every_gate_input_is_stored_beside_what_it_gates():
    """A chart must be able to decline to draw a point without going back to the source
    rows to work out whether it should."""
    corpus = Corpus(
        turns=[
            turn(turn_id=1, session_id=1, words=40, errors=(error(),)),
            turn(turn_id=2, session_id=2, words=20, errors=(error(asr_suspect=True),)),
        ],
        attempts=[reading(phones={"TH": (30, -4.0), "S": (10, -1.0)})],
    )
    counts = snapshot_values(corpus, WEEK)["sample_counts"]

    assert counts["turns"] == 2
    assert counts["sessions"] == 2
    assert counts["words"] == 60
    assert counts["attempts"] == 1
    assert counts["phones"] == 40
    assert counts["errors_counted"] == 1
    assert counts["errors_excluded"] == 1


def test_the_same_rows_always_produce_the_same_snapshot():
    """The rebuild is safe to run at any time only because of this. A snapshot that
    drifted between runs would make a refresh a different chart."""
    corpus = Corpus(
        turns=[turn(words=80, features={"present_simple": 3}, errors=(error(),))],
        attempts=[reading()],
    )
    assert snapshot_values(corpus, WEEK) == snapshot_values(corpus, WEEK)


# ── Writing ─────────────────────────────────────────────────────────────────


@pytest.fixture
async def practised(db_session, seeded):
    """An account with one analysed turn, ready to be rolled up."""
    user = User(
        email=unique_email("rollup"),
        password_hash=hash_password("practice-makes-permanent"),
        native_language="es",
    )
    db_session.add(user)
    await db_session.flush()

    scenario = await db_session.scalar(
        select(Scenario).where(Scenario.slug == "daily-standup")
    )
    session = PracticeSession(
        user_id=user.id, scenario_id=scenario.id, mode="conversation"
    )
    db_session.add(session)
    await db_session.flush()

    row = Turn(
        session_id=session.id,
        idx=0,
        role="user",
        transcript="yesterday I go to the office",
        asr_confidence=0.95,
        analysis_status="analyzed",
        analyzed_at=datetime.now(timezone.utc),
    )
    db_session.add(row)
    await db_session.flush()

    db_session.add(
        FluencyMetrics(
            turn_id=row.id,
            word_count=60,
            speech_rate_wpm=118.0,
            articulation_rate=140.0,
            pause_ratio=0.18,
            mean_length_run=7.0,
            filler_count=3,
        )
    )
    db_session.add(GrammarUsage(turn_id=row.id, feature="present_simple", count=4))
    db_session.add(
        LanguageError(
            turn_id=row.id,
            category="VERB_TENSE",
            original="I go",
            correction="I went",
            detector="llm",
            confidence=0.9,
            asr_suspect=False,
        )
    )
    await db_session.commit()
    return user, session, row


async def snapshots_of(db, user_id: int) -> list[ProgressSnapshot]:
    return list(
        (
            await db.scalars(
                select(ProgressSnapshot)
                .where(ProgressSnapshot.user_id == user_id)
                .order_by(ProgressSnapshot.period, ProgressSnapshot.period_start)
            )
        ).all()
    )


async def test_a_rollup_writes_one_row_per_granularity(practised, db_session):
    user, _, _ = practised

    written = await rebuild_user(db_session, user.id)
    await db_session.commit()

    assert {period.period for period in written} == {"day", "week"}
    rows = await snapshots_of(db_session, user.id)
    assert len(rows) == 2
    assert all(row.sample_counts["words"] == 60 for row in rows)
    assert all(row.accuracy["by_category"] == {"VERB_TENSE": 1} for row in rows)


async def test_running_it_twice_writes_nothing_the_second_time(practised, db_session):
    """The property the session-end call depends on. Without it, ending a session would
    rewrite every snapshot this account has ever had."""
    user, _, _ = practised

    await rebuild_user(db_session, user.id)
    await db_session.commit()
    again = await rebuild_user(db_session, user.id)

    assert again == []


async def test_force_rewrites_even_when_nothing_underneath_changed(
    practised, db_session
):
    """The escape hatch for a change to the arithmetic itself, after which every stored
    snapshot is a number computed by code that no longer exists."""
    user, _, _ = practised

    await rebuild_user(db_session, user.id)
    await db_session.commit()
    forced = await rebuild_user(db_session, user.id, force=True)

    assert {period.period for period in forced} == {"day", "week"}


async def test_a_new_turn_makes_its_own_period_stale_again(practised, db_session):
    user, session, _ = practised

    await rebuild_user(db_session, user.id)
    await db_session.commit()
    assert await is_stale(db_session, user.id) is False

    later = Turn(
        session_id=session.id,
        idx=1,
        role="user",
        transcript="and today I went again",
        analysis_status="analyzed",
        analyzed_at=datetime.now(timezone.utc),
    )
    db_session.add(later)
    await db_session.flush()
    db_session.add(FluencyMetrics(turn_id=later.id, word_count=20))
    await db_session.commit()

    assert await is_stale(db_session, user.id) is True
    assert len(await rebuild_user(db_session, user.id)) == 2


async def test_a_deleted_session_takes_its_contribution_off_the_chart(
    practised, db_session
):
    """A snapshot left behind by deleted turns would keep a point on a trend for ever, and
    it would be a point with nothing underneath it to check."""
    user, session, _ = practised

    await rebuild_user(db_session, user.id)
    await db_session.commit()
    assert await snapshots_of(db_session, user.id)

    await db_session.delete(session)
    await db_session.commit()
    await rebuild_user(db_session, user.id)
    await db_session.commit()

    assert await snapshots_of(db_session, user.id) == []


async def test_a_turn_that_has_not_been_analysed_yet_is_not_rolled_up(
    practised, db_session
):
    """A turn still waiting for its analysis is not a turn with no errors in it. Counting
    it would put a number on the chart that changes when the analyser catches up."""
    user, session, _ = practised

    pending = Turn(
        session_id=session.id,
        idx=1,
        role="user",
        transcript="this one has not been looked at",
        analysis_status="pending",
    )
    db_session.add(pending)
    await db_session.flush()
    db_session.add(FluencyMetrics(turn_id=pending.id, word_count=500))
    await db_session.commit()

    await rebuild_user(db_session, user.id)
    await db_session.commit()

    rows = await snapshots_of(db_session, user.id)
    assert all(row.sample_counts["words"] == 60 for row in rows)


async def test_one_account_is_never_rolled_up_into_another(practised, db_session):
    user, _, _ = practised
    stranger = User(
        email=unique_email("stranger"),
        password_hash=hash_password("practice-makes-permanent"),
        native_language="es",
    )
    db_session.add(stranger)
    await db_session.commit()

    await rebuild_user(db_session, user.id)
    await rebuild_user(db_session, stranger.id)
    await db_session.commit()

    assert await snapshots_of(db_session, stranger.id) == []
    assert len(await snapshots_of(db_session, user.id)) == 2
