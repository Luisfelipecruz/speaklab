"""The progress endpoints: what is drawn, what is withheld, and what it says instead.

Almost every test here is about a refusal. Plotting a number is one line of arithmetic;
the thing that decides whether this page is honest is what it does with three weeks of
almost no practice, which is the state every real account starts in and the one this
project's own corpus is still in.

Snapshots are inserted directly rather than produced by practising through the API. That
is deliberate: the rollup has its own suite, and building a month of varied practice
through four endpoints would test the fixtures rather than the gates.
"""

from datetime import date, timedelta

import pytest
from sqlalchemy import select

from config import (
    PROGRESS_MIN_ATTEMPTS,
    PROGRESS_MIN_POINTS,
    PROGRESS_MIN_WORDS,
)
from db_models import ProgressSnapshot, User
from services.rollup import period_start

TODAY = date.today()
THIS_WEEK = period_start(TODAY, "week")


def week(offset: int) -> date:
    """`offset` weeks before the current one."""
    return THIS_WEEK - timedelta(days=7 * offset)


def snapshot(
    user_id: int,
    start: date,
    *,
    words: int = 200,
    errors_per_100: float | None = 4.0,
    forms: dict | None = None,
    by_form: dict | None = None,
    speech_rate: float = 120.0,
    attempts: int = 0,
    phones: dict | None = None,
    phone_samples: dict | None = None,
    period: str = "week",
) -> ProgressSnapshot:
    forms = forms if forms is not None else {"present_simple": 6, "past_simple": 2}
    return ProgressSnapshot(
        user_id=user_id,
        period=period,
        period_start=start,
        fluency={
            "words_spoken": words,
            "speech_rate_wpm": speech_rate,
            "articulation_rate_wpm": speech_rate + 20,
            "pause_ratio": 0.2,
            "mean_length_run": 6.0,
            "filler_count": 4,
            "fillers_per_100_words": 2.0,
            "mean_pause_before_speaking_ms": 400,
        },
        accuracy={
            "errors_per_100_words": errors_per_100,
            "by_category": {"VERB_TENSE": 3, "ARTICLE": 1},
            "by_category_per_100_words": {"VERB_TENSE": 1.5, "ARTICLE": 0.5},
            "excluded": {"asr_suspect": 1, "low_confidence": 0},
            "by_form": by_form or {},
        },
        complexity={
            "distinct_forms": len(forms),
            "form_instances": sum(forms.values()),
            "by_form": forms,
            "subordination_index": 0.4,
        },
        pronunciation={"phones": phones or {}, "mean_gop": -2.0 if phones else None},
        sample_counts={
            "turns": 4,
            "words": words,
            "sessions": 1,
            "attempts": attempts,
            "phones": sum((phone_samples or {}).values()),
            "phone_samples": phone_samples or {},
            "errors_counted": 4,
            "errors_excluded": 1,
            "devices": [],
        },
    )


@pytest.fixture
async def practised(client, account, db_session):
    """A signed-in account with three weeks of measurable practice behind it."""
    for offset in (2, 1, 0):
        db_session.add(snapshot(account["id"], week(offset)))
    await db_session.commit()
    return account


def series_of(body: dict, family: str, metric: str) -> dict:
    group = next(entry for entry in body["families"] if entry["name"] == family)
    return next(entry for entry in group["series"] if entry["metric"] == metric)


# ── Access ──────────────────────────────────────────────────────────────────


async def test_progress_needs_an_account(client):
    for path in ("/progress", "/progress/recommendations"):
        assert (await client.get(path)).status_code == 401
    assert (await client.post("/progress/refresh")).status_code == 401


async def test_one_account_never_sees_another_ones_numbers(
    client, other_client, account, db_session
):
    """There is no shape of this API that takes a user id, and this is the test that says
    so: the stranger's request is answered with their own empty page, not with a 403 that
    would confirm somebody else's exists."""
    db_session.add(snapshot(account["id"], THIS_WEEK, words=500))
    await db_session.commit()

    from tests.conftest import register_account

    await register_account(other_client)
    body = (await other_client.get("/progress")).json()

    assert body["totals"]["words"] == 0


# ── Gates ───────────────────────────────────────────────────────────────────


async def test_a_new_account_is_told_what_each_chart_is_waiting_for(client, account):
    """The most common state this page will ever be in. Empty axes with no explanation
    read as a broken feature; every suppressed series has to say what it needs."""
    body = (await client.get("/progress")).json()

    assert body["totals"]["words"] == 0
    for family in body["families"]:
        for entry in family["series"]:
            assert entry["gate"]["shown"] is False
            assert entry["gate"]["reason"], entry["metric"]


async def test_a_period_below_the_word_floor_is_a_hole_with_a_reason(
    client, account, db_session
):
    """Not an omitted point. A chart drawn only from the periods that cleared the floor
    compresses a thin fortnight into the space between two points, which reads as
    continuous practice."""
    db_session.add(snapshot(account["id"], THIS_WEEK, words=PROGRESS_MIN_WORDS - 1))
    await db_session.commit()

    entry = series_of(
        (await client.get("/progress")).json(), "fluency", "speech_rate_wpm"
    )
    withheld = [point for point in entry["points"] if point["start"] == str(THIS_WEEK)]

    assert entry["gate"]["shown"] is False
    assert withheld[0]["value"] is None
    assert str(PROGRESS_MIN_WORDS) in withheld[0]["withheld"]


async def test_enough_speech_draws_the_point(client, account, db_session):
    db_session.add(snapshot(account["id"], THIS_WEEK, words=PROGRESS_MIN_WORDS))
    await db_session.commit()

    entry = series_of(
        (await client.get("/progress")).json(), "fluency", "speech_rate_wpm"
    )
    drawn = [point for point in entry["points"] if point["value"] is not None]

    assert entry["gate"]["shown"] is True
    assert drawn[0]["value"] == 120.0
    assert drawn[0]["samples"] == PROGRESS_MIN_WORDS


async def test_a_week_with_nothing_in_it_is_still_a_point_on_the_axis(
    practised, client
):
    """Gaps are periods too. Silence has to look like silence rather than being closed up."""
    body = (await client.get("/progress?days=60")).json()
    entry = series_of(body, "fluency", "speech_rate_wpm")

    empty = [
        point for point in entry["points"] if point["withheld"] == "nothing recorded"
    ]
    assert empty, "a window longer than the practice showed no gaps at all"


# ── Claims ──────────────────────────────────────────────────────────────────


async def test_speech_rate_is_drawn_and_never_judged(practised, client):
    """The easiest sentence on this page to write and the least defensible one on it.
    Faster is nerves as often as it is fluency, so the series carries numbers and no
    verdict."""
    entry = series_of(
        (await client.get("/progress")).json(), "fluency", "speech_rate_wpm"
    )

    assert entry["gate"]["shown"] is True
    assert entry["better"] is None
    assert entry["direction"] is None


async def test_a_falling_error_rate_over_enough_weeks_is_called_an_improvement(
    client, account, db_session
):
    for offset, rate in zip((2, 1, 0), (8.0, 6.0, 3.0), strict=True):
        db_session.add(snapshot(account["id"], week(offset), errors_per_100=rate))
    await db_session.commit()

    entry = series_of(
        (await client.get("/progress")).json(), "accuracy", "errors_per_100_words"
    )

    assert entry["better"] == "lower"
    assert entry["change"] == -5.0
    assert entry["direction"] == "improving"


async def test_two_points_are_not_enough_to_claim_a_direction(
    client, account, db_session
):
    """A line through two points is a line through noise, and it is the sentence a learner
    would act on."""
    assert PROGRESS_MIN_POINTS > 2
    for offset, rate in zip((1, 0), (8.0, 3.0), strict=True):
        db_session.add(snapshot(account["id"], week(offset), errors_per_100=rate))
    await db_session.commit()

    entry = series_of(
        (await client.get("/progress")).json(), "accuracy", "errors_per_100_words"
    )

    assert entry["gate"]["shown"] is True, "the points themselves are still drawn"
    assert entry["direction"] is None


async def test_the_accuracy_family_carries_the_measured_quality_of_its_labels(
    practised, client
):
    """The rate is a count of rows and is exact. The rows under it come from two detectors
    of different quality, and which is which belongs on the screen rather than only in a
    decision document."""
    body = (await client.get("/progress")).json()
    accuracy = next(entry for entry in body["families"] if entry["name"] == "accuracy")

    assert accuracy["caveat"] and "0.50" in accuracy["caveat"]
    assert "grammar rules" in accuracy["caveat"]
    for family in body["families"]:
        if family["name"] != "accuracy":
            assert family["caveat"] is None


# ── Pronunciation ───────────────────────────────────────────────────────────


async def test_per_sound_trends_wait_for_enough_readings(client, account, db_session):
    """The first few readings describe the microphone as much as the mouth, and the gate
    says so in those words rather than showing an empty panel."""
    db_session.add(
        snapshot(
            account["id"],
            THIS_WEEK,
            attempts=1,
            phones={"TH": {"mean_gop": -6.0, "z": None, "baseline_readings": 0}},
            phone_samples={"TH": 30},
        )
    )
    await db_session.commit()

    body = (await client.get("/progress")).json()

    assert body["phone_gate"]["shown"] is False
    assert body["phone_gate"]["need"] == PROGRESS_MIN_ATTEMPTS
    assert body["phones"] == []
    assert "microphone" in body["phone_gate"]["reason"]


async def test_enough_readings_show_the_sounds_worst_first(client, account, db_session):
    db_session.add(
        snapshot(
            account["id"],
            THIS_WEEK,
            attempts=PROGRESS_MIN_ATTEMPTS,
            phones={
                "TH": {"mean_gop": -6.0, "z": -1.8, "baseline_readings": 3},
                "S": {"mean_gop": -1.0, "z": 0.4, "baseline_readings": 3},
            },
            phone_samples={"TH": 30, "S": 40},
        )
    )
    await db_session.commit()

    body = (await client.get("/progress")).json()

    assert body["phone_gate"]["shown"] is True
    assert [phone["phone"] for phone in body["phones"]] == ["TH", "S"]
    assert body["phones"][0]["z"] == -1.8


async def test_a_sound_with_too_few_instances_is_left_out_of_the_panel(
    client, account, db_session
):
    """A passage engineered around one sound yields it thirty times. A sound that turned
    up twice is a sample of two, whatever the reading around it was worth."""
    db_session.add(
        snapshot(
            account["id"],
            THIS_WEEK,
            attempts=PROGRESS_MIN_ATTEMPTS,
            phones={
                "TH": {"mean_gop": -6.0, "z": -1.8, "baseline_readings": 3},
                "ZH": {"mean_gop": -9.0, "z": -4.0, "baseline_readings": 3},
            },
            phone_samples={"TH": 30, "ZH": 2},
        )
    )
    await db_session.commit()

    body = (await client.get("/progress")).json()
    assert [phone["phone"] for phone in body["phones"]] == ["TH"]


# ── Repertoire ──────────────────────────────────────────────────────────────


async def test_a_narrowing_repertoire_with_fewer_errors_is_a_warning_not_a_win(
    client, account, db_session
):
    """The one combination a chart would otherwise render as unambiguous progress. A
    learner who retreats to the present simple makes fewer mistakes."""
    db_session.add(
        snapshot(
            account["id"],
            week(1),
            errors_per_100=8.0,
            forms={"present_simple": 5, "past_simple": 3, "present_perfect": 2},
        )
    )
    db_session.add(
        snapshot(
            account["id"], week(0), errors_per_100=2.0, forms={"present_simple": 9}
        )
    )
    await db_session.commit()

    repertoire = (await client.get("/progress")).json()["repertoire"]

    assert repertoire["distinct_forms"] == 1
    assert repertoire["previous_distinct_forms"] == 3
    assert repertoire["warning"] is not None
    assert "not the same as improving" in repertoire["warning"]


async def test_a_narrowing_repertoire_with_more_errors_is_not_warned_about(
    client, account, db_session
):
    """It is a bad week, and the chart already says so. The warning exists for the case
    the numbers would otherwise be read as good news."""
    db_session.add(
        snapshot(
            account["id"], week(1), errors_per_100=2.0, forms={"a": 1, "b": 1, "c": 1}
        )
    )
    db_session.add(snapshot(account["id"], week(0), errors_per_100=9.0, forms={"a": 3}))
    await db_session.commit()

    assert (await client.get("/progress")).json()["repertoire"]["warning"] is None


async def test_reaching_further_while_making_fewer_mistakes_is_not_warned_about(
    client, account, db_session
):
    """The case the warning must stay out of the way of: a wider range of forms *and* a
    lower error rate is the thing this product is for."""
    db_session.add(
        snapshot(account["id"], week(1), errors_per_100=8.0, forms={"a": 3, "b": 1})
    )
    db_session.add(
        snapshot(
            account["id"],
            week(0),
            errors_per_100=3.0,
            forms={"a": 3, "b": 2, "c": 1, "d": 1},
        )
    )
    await db_session.commit()

    repertoire = (await client.get("/progress")).json()["repertoire"]

    assert repertoire["distinct_forms"] == 4
    assert repertoire["previous_distinct_forms"] == 2
    assert repertoire["warning"] is None


def tallied(used: int, right: int, missed: int = 0) -> dict:
    return {
        "used": used,
        "right": right,
        "wrong": used - right,
        "missed": missed,
        "accuracy": round(right / (used + missed), 4),
    }


async def test_accuracy_per_form_is_shown_as_a_proportion_above_the_floor(
    client, account, db_session
):
    """Twelve present simples, nine right, one needed and missed: a proportion is worth
    giving. Two past simples, one right: the counts are, the proportion is not."""
    db_session.add(
        snapshot(
            account["id"],
            week(0),
            forms={"present_simple": 12, "past_simple": 2},
            by_form={
                "present_simple": tallied(12, 9, missed=1),
                "past_simple": tallied(2, 1),
            },
        )
    )
    await db_session.commit()

    repertoire = (await client.get("/progress")).json()["repertoire"]

    assert repertoire["accuracy_floor"] == 10
    assert repertoire["accuracy"]["present_simple"] == {
        "used": 12,
        "right": 9,
        "wrong": 3,
        "missed": 1,
        "accuracy": 0.6923,
    }
    assert repertoire["accuracy"]["past_simple"] == {
        "used": 2,
        "right": 1,
        "wrong": 1,
        "missed": 0,
        "accuracy": None,
    }


async def test_accuracy_per_form_carries_its_caveat_and_nothing_else_does(
    client, account, db_session
):
    """The corrections are the model's, and a wrong one counts against a form the learner
    used correctly. The panel is read away from the error-rate chart, so it says so."""
    db_session.add(
        snapshot(
            account["id"],
            week(1),
            by_form={"present_simple": tallied(4, 3)},
        )
    )
    db_session.add(snapshot(account["id"], week(0)))
    await db_session.commit()

    repertoire = (await client.get("/progress")).json()["repertoire"]
    assert repertoire["accuracy"] == {}
    assert repertoire["caveat"] is None

    latest = await db_session.scalar(
        select(ProgressSnapshot).where(
            ProgressSnapshot.user_id == account["id"],
            ProgressSnapshot.period_start == week(0),
        )
    )
    latest.accuracy = dict(latest.accuracy, by_form={"past_simple": tallied(2, 1)})
    await db_session.commit()

    repertoire = (await client.get("/progress")).json()["repertoire"]
    assert "0.50 precision" in repertoire["caveat"]
    assert "a form you used correctly" in repertoire["caveat"]
    assert "a missed one counts as right" in repertoire["caveat"]


async def test_an_empty_repertoire_still_says_what_the_floor_is(client, account):
    """The panel explains the floor before anything is in it."""
    repertoire = (await client.get("/progress")).json()["repertoire"]
    assert repertoire["accuracy"] == {}
    assert repertoire["accuracy_floor"] == 10


async def test_a_snapshot_from_before_the_join_has_no_accuracy_per_form(
    client, account, db_session
):
    """A period rolled up before corrections were joined to forms carries none, and the
    page says nothing rather than a hundred per cent."""
    row = snapshot(account["id"], week(0))
    row.accuracy = {
        key: value for key, value in row.accuracy.items() if key != "by_form"
    }
    db_session.add(row)
    await db_session.commit()

    assert (await client.get("/progress")).json()["repertoire"]["accuracy"] == {}


# ── Freshness ───────────────────────────────────────────────────────────────


async def test_the_page_says_when_it_is_behind_rather_than_rebuilding_itself(
    client, account, db_session, seeded
):
    """Recomputing inside a page load is what a snapshot table exists to avoid. Saying so
    lets the page offer a refresh instead."""
    from datetime import datetime, timezone

    from db_models import PracticeSession, Turn

    session = PracticeSession(user_id=account["id"], mode="conversation")
    db_session.add(session)
    await db_session.flush()
    db_session.add(
        Turn(
            session_id=session.id,
            idx=0,
            role="user",
            transcript="something analysed after the last rollup",
            analysis_status="analyzed",
            analyzed_at=datetime.now(timezone.utc),
        )
    )
    await db_session.commit()

    assert (await client.get("/progress")).json()["stale"] is True


async def test_refresh_rebuilds_the_snapshots_and_returns_the_page(
    client, account, db_session, seeded
):
    from datetime import datetime, timezone

    from db_models import FluencyMetrics, PracticeSession, Turn

    session = PracticeSession(user_id=account["id"], mode="conversation")
    db_session.add(session)
    await db_session.flush()
    turn = Turn(
        session_id=session.id,
        idx=0,
        role="user",
        transcript="a turn nothing has rolled up yet",
        analysis_status="analyzed",
        analyzed_at=datetime.now(timezone.utc),
    )
    db_session.add(turn)
    await db_session.flush()
    db_session.add(
        FluencyMetrics(turn_id=turn.id, word_count=120, speech_rate_wpm=115.0)
    )
    await db_session.commit()

    response = await client.post("/progress/refresh")
    body = response.json()

    assert response.status_code == 200
    assert body["stale"] is False
    assert body["totals"]["words"] == 120

    rows = (
        await db_session.scalars(
            select(ProgressSnapshot).where(ProgressSnapshot.user_id == account["id"])
        )
    ).all()
    assert {row.period for row in rows} == {"day", "week"}


async def test_refreshing_twice_is_the_same_page(client, account, db_session, seeded):
    first = (await client.post("/progress/refresh")).json()
    second = (await client.post("/progress/refresh")).json()
    assert first == second


# ── Parameters ──────────────────────────────────────────────────────────────


async def test_daily_granularity_is_available(client, account, db_session):
    db_session.add(snapshot(account["id"], TODAY, period="day", words=120))
    await db_session.commit()

    body = (await client.get("/progress?period=day")).json()

    assert body["period"] == "day"
    assert series_of(body, "fluency", "speech_rate_wpm")["gate"]["shown"] is True


async def test_an_unknown_granularity_is_refused_rather_than_answered_emptily(
    client, account
):
    """422, not an empty chart. An empty chart reads as "you have not practised", which is
    a wrong answer rather than a rejected question."""
    assert (await client.get("/progress?period=fortnight")).status_code == 422


async def test_the_window_is_bounded_on_the_server(client, account):
    assert (await client.get("/progress?days=100000")).status_code == 422
    assert (await client.get("/progress?days=1")).status_code == 422


async def test_the_totals_count_what_the_gates_are_about(practised, client):
    body = (await client.get("/progress")).json()

    assert body["totals"]["periods"] == 3
    assert body["totals"]["words"] == 600
    assert body["totals"]["sessions"] == 3


async def test_a_deleted_account_takes_its_snapshots_with_it(
    client, account, db_session
):
    """The cascade is declared on the column; this is the test that says somebody checked
    it, because a progress row outliving its user is a row nothing can ever reach."""
    db_session.add(snapshot(account["id"], THIS_WEEK))
    await db_session.commit()

    user = await db_session.get(User, account["id"])
    await db_session.delete(user)
    await db_session.commit()

    rows = (
        await db_session.scalars(
            select(ProgressSnapshot).where(ProgressSnapshot.user_id == account["id"])
        )
    ).all()
    assert rows == []
