"""The grammar page: a learner's corrections grouped, the verb forms they changed, and the
one form named for practice.

The rows are inserted directly — a session, a turn, its counts and its corrections — rather
than produced by analysing speech, because what is under test is the grouping and the
floors, and the analysis has its own suite. Every correction is placed by quoting the
transcript, so the offsets hold the words they claim to, as the analysis stores them.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from config import (
    ERROR_CONFIDENCE_FLOOR,
    GRAMMAR_CONTEXT_CHARS,
    GRAMMAR_EXAMPLES_PER_CATEGORY,
    GRAMMAR_MIN_FORM_CORRECTIONS,
    PROGRESS_MIN_FORM_CONTEXTS,
)
from db_models import (
    FluencyMetrics,
    GrammarUsage,
    LanguageError,
    PracticeSession,
    Scenario,
    Turn,
)
from services.corrections import excerpt

pytestmark = pytest.mark.usefixtures("seeded")


def fix(
    quote: str,
    correction: str,
    category: str = "VERB_TENSE",
    *,
    form: str | None = None,
    corrected_form: str | None = None,
    detector: str = "llm",
    confidence: float = 0.9,
    asr_suspect: bool = False,
    explanation: str | None = "An explanation.",
) -> dict:
    return {
        "quote": quote,
        "correction": correction,
        "category": category,
        "form": form,
        "corrected_form": corrected_form,
        "detector": detector,
        "confidence": confidence,
        "asr_suspect": asr_suspect,
        "explanation": explanation,
    }


async def practise(
    db,
    user_id: int,
    transcript: str,
    fixes: list[dict] = (),
    *,
    used: dict[str, int] | None = None,
    words: int | None = None,
    days_ago: int = 0,
    scenario: str = "daily-standup",
    status: str = "analyzed",
) -> Turn:
    """One analysed turn in a session of its own, with its counts and corrections."""
    scenario_id = await db.scalar(select(Scenario.id).where(Scenario.slug == scenario))
    session = PracticeSession(
        user_id=user_id, scenario_id=scenario_id, mode="conversation"
    )
    db.add(session)
    await db.flush()
    turn = Turn(
        session_id=session.id,
        idx=1,
        role="user",
        transcript=transcript,
        analysis_status=status,
        created_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
    )
    db.add(turn)
    await db.flush()
    db.add(
        FluencyMetrics(
            turn_id=turn.id,
            word_count=words if words is not None else len(transcript.split()),
        )
    )
    for feature, count in (used or {}).items():
        db.add(GrammarUsage(turn_id=turn.id, feature=feature, count=count))
    for found in fixes:
        start = transcript.index(found["quote"])
        db.add(
            LanguageError(
                turn_id=turn.id,
                category=found["category"],
                span_start=start,
                span_end=start + len(found["quote"]),
                original=found["quote"],
                correction=found["correction"],
                explanation=found["explanation"],
                form=found["form"],
                corrected_form=found["corrected_form"],
                detector=found["detector"],
                confidence=found["confidence"],
                asr_suspect=found["asr_suspect"],
            )
        )
    await db.commit()
    return turn


TENSE = fix(
    "I go to the office",
    "I went to the office",
    form="present_simple",
    corrected_form="past_simple",
)
AGREEMENT = fix(
    "my sister work",
    "my sister works",
    "SUBJECT_VERB_AGREEMENT",
    form="present_simple",
    corrected_form="present_simple",
    detector="rule",
    confidence=1.0,
)
PREPOSITION = fix("depends of", "depends on", "PREPOSITION")

SPOKEN = (
    "Good morning. Yesterday I go to the office and my sister work in a bank. "
    "It depends of the weather, I think."
)


async def test_the_page_needs_an_account(client):
    assert (await client.get("/grammar")).status_code == 401


async def test_a_new_account_is_told_what_it_is_waiting_for(client, account):
    body = (await client.get("/grammar")).json()

    assert body["totals"] == {
        "sessions": 0,
        "turns": 0,
        "words": 0,
        "corrections": 0,
        "counted": 0,
    }
    assert body["categories"] == [] and body["forms"] == []
    assert body["weakest"] is None
    assert body["weakest_gate"]["shown"] is False
    assert body["weakest_gate"]["reason"].startswith(
        "No correction so far has changed a verb form."
    )
    assert body["caveat"] is None


async def test_corrections_are_grouped_by_kind_most_counted_first(
    client, account, db_session
):
    await practise(
        db_session,
        account["id"],
        SPOKEN,
        [TENSE, AGREEMENT, PREPOSITION],
        used={"present_simple": 3, "main_clause": 3},
    )
    await practise(
        db_session,
        account["id"],
        "Last week I finish the report and I send it.",
        [
            fix(
                "I finish the report",
                "I finished the report",
                form="present_simple",
                corrected_form="past_simple",
            )
        ],
        used={"present_simple": 2},
    )

    body = (await client.get("/grammar")).json()

    assert [c["category"] for c in body["categories"]] == [
        "VERB_TENSE",
        "PREPOSITION",
        "SUBJECT_VERB_AGREEMENT",
    ]
    tense = body["categories"][0]
    assert tense["label"] == "verb tense"
    assert "went/gone" in tense["description"]
    assert tense["counted"] == 2 and tense["not_counted"] == 0
    assert tense["by_detector"] == {"llm": 2}
    # Newest first: the second turn was stored last.
    assert [e["original"] for e in tense["examples"]] == [
        "I finish the report",
        "I go to the office",
    ]
    assert body["totals"]["corrections"] == 4
    assert body["totals"]["sessions"] == 2
    assert body["categories"][2]["by_detector"] == {"rule": 1}
    assert body["caveat"] and "none was checked by a person" in body["caveat"]


async def test_each_correction_comes_in_the_sentence_it_was_made_in(
    client, account, db_session
):
    turn = await practise(db_session, account["id"], SPOKEN, [TENSE])

    (example,) = (await client.get("/grammar")).json()["categories"][0]["examples"]

    assert example["before"] == "Yesterday "
    assert example["quote"] == "I go to the office"
    assert example["after"] == " and my sister work in a bank."
    assert example["correction"] == "I went to the office"
    assert example["session_id"] == turn.session_id
    assert example["scenario_title"] == "Daily standup"
    assert (example["form"], example["corrected_form"]) == (
        "present_simple",
        "past_simple",
    )


async def test_a_doubtful_correction_is_shown_and_not_counted(
    client, account, db_session
):
    """On words the recogniser was unsure of, or hedged by the model: on the page, so the
    learner can see it, and out of every count, as it is everywhere else."""
    await practise(
        db_session,
        account["id"],
        SPOKEN,
        [
            dict(TENSE, asr_suspect=True),
            dict(PREPOSITION, confidence=ERROR_CONFIDENCE_FLOOR / 2),
        ],
        used={"present_simple": 3},
    )

    body = (await client.get("/grammar")).json()

    assert body["totals"]["counted"] == 0
    assert {c["category"]: c["not_counted"] for c in body["categories"]} == {
        "VERB_TENSE": 1,
        "PREPOSITION": 1,
    }
    assert all(not e["counted"] for c in body["categories"] for e in c["examples"])
    (present,) = body["forms"]
    assert (present["wrong"], present["missed"], present["corrections"]) == (0, 0, [])


async def test_only_the_newest_few_are_quoted_and_all_are_counted(
    client, account, db_session
):
    for day in range(GRAMMAR_EXAMPLES_PER_CATEGORY + 2):
        await practise(db_session, account["id"], SPOKEN, [TENSE], days_ago=day)

    (tense,) = (await client.get("/grammar")).json()["categories"]

    assert tense["counted"] == GRAMMAR_EXAMPLES_PER_CATEGORY + 2
    assert len(tense["examples"]) == GRAMMAR_EXAMPLES_PER_CATEGORY


async def test_the_window_leaves_older_practice_out(client, account, db_session):
    await practise(db_session, account["id"], SPOKEN, [TENSE], days_ago=40)

    assert (await client.get("/grammar?days=30")).json()["totals"]["turns"] == 0
    assert (await client.get("/grammar?days=60")).json()["totals"]["turns"] == 1


async def test_a_turn_not_yet_analysed_is_not_on_the_page(client, account, db_session):
    await practise(db_session, account["id"], SPOKEN, [TENSE], status="analyzing")

    assert (await client.get("/grammar")).json()["totals"]["corrections"] == 0


async def test_one_account_never_sees_another_ones_corrections(
    client, account, other_client, db_session
):
    await practise(db_session, account["id"], SPOKEN, [TENSE])
    from tests.conftest import register_account

    await register_account(other_client)

    body = (await other_client.get("/grammar")).json()
    assert body["totals"]["corrections"] == 0
    assert body["categories"] == []


async def test_the_verb_forms_carry_counts_and_the_corrections_behind_them(
    client, account, db_session
):
    """Right is used less wrong, and the past simple was needed once and never said. No
    percentage: the counts are what can be checked against the sentences below them."""
    await practise(
        db_session,
        account["id"],
        SPOKEN,
        [TENSE, AGREEMENT],
        used={"present_simple": 3, "main_clause": 3},
    )

    forms = {f["form"]: f for f in (await client.get("/grammar")).json()["forms"]}

    assert set(forms) == {"present_simple", "past_simple"}
    present = forms["present_simple"]
    assert (present["used"], present["right"], present["wrong"], present["missed"]) == (
        3,
        1,
        2,
        0,
    )
    assert "accuracy" not in present
    assert [c["original"] for c in present["corrections"]] == [
        "I go to the office",
        "my sister work",
    ]
    past = forms["past_simple"]
    assert (past["used"], past["missed"]) == (0, 1)
    assert [c["correction"] for c in past["corrections"]] == ["I went to the office"]


def corrected_present_perfects(count: int) -> list[dict]:
    return [
        fix(
            f"I go number {n}",
            f"I have been number {n}",
            form="past_simple",
            corrected_form="present_perfect",
        )
        for n in range(count)
    ]


def perfect_transcript(count: int) -> str:
    return " ".join(f"I go number {n}." for n in range(count))


async def test_below_the_floor_no_form_is_named_and_the_page_says_how_far(
    client, account, db_session
):
    """Four corrections could all be the detector's mistakes. The gate says which form is
    nearest, and what the floor is."""
    short = GRAMMAR_MIN_FORM_CORRECTIONS - 1
    await practise(
        db_session,
        account["id"],
        perfect_transcript(short),
        corrected_present_perfects(short),
        used={"past_simple": PROGRESS_MIN_FORM_CONTEXTS},
    )

    body = (await client.get("/grammar")).json()

    assert body["weakest"] is None
    gate = body["weakest_gate"]
    assert (gate["shown"], gate["have"], gate["need"]) == (
        False,
        short,
        GRAMMAR_MIN_FORM_CORRECTIONS,
    )
    # Both have four; the past simple came up more often, so it is the nearer.
    assert gate["reason"].startswith(
        f"The form with the most corrections so far is the past simple: {short} "
        f"corrections, from the {PROGRESS_MIN_FORM_CONTEXTS} times it was said or needed."
    )
    assert f"come up {PROGRESS_MIN_FORM_CONTEXTS} times" in gate["reason"]


async def test_enough_corrections_on_too_few_uses_names_nothing(
    client, account, db_session
):
    """Corrected five times in five is still a sample of five."""
    enough = GRAMMAR_MIN_FORM_CORRECTIONS
    await practise(
        db_session,
        account["id"],
        perfect_transcript(enough),
        corrected_present_perfects(enough),
        used={"past_simple": enough},
    )

    assert (await client.get("/grammar")).json()["weakest"] is None


async def test_the_form_right_least_often_is_named_with_a_scenario_at_your_band(
    client, account, db_session
):
    """The present perfect, needed five times and never said, is right none of five; the
    past simple is right in all but its five corrections. A B1 learner is sent to the
    B1 scenario that asks for it, not the first one alphabetically."""
    from db_models import User

    user = await db_session.get(User, account["id"])
    user.cefr_self_assessed = "B1"
    enough = max(GRAMMAR_MIN_FORM_CORRECTIONS, PROGRESS_MIN_FORM_CONTEXTS)
    await practise(
        db_session,
        account["id"],
        perfect_transcript(enough),
        corrected_present_perfects(enough),
        used={"past_simple": enough * 3},
    )

    body = (await client.get("/grammar")).json()
    weakest = body["weakest"]

    assert weakest["form"] == "present_perfect"
    assert (weakest["used"], weakest["right"], weakest["missed"]) == (0, 0, enough)
    assert weakest["scenario_slug"] == "doctors-appointment"
    assert weakest["reason"].startswith(f"Right 0 of {enough} — needed {enough} times")
    assert f"{weakest['scenario_title']} is written to draw it out" in weakest["reason"]
    assert body["weakest_gate"]["shown"] is True


async def test_a_form_no_scenario_asks_for_is_named_and_says_so(
    client, account, db_session
):
    enough = max(GRAMMAR_MIN_FORM_CORRECTIONS, PROGRESS_MIN_FORM_CONTEXTS)
    await practise(
        db_session,
        account["id"],
        perfect_transcript(enough),
        [
            dict(found, corrected_form="past_perfect_continuous")
            for found in corrected_present_perfects(enough)
        ],
        used={"past_simple": enough * 3},
    )

    weakest = (await client.get("/grammar")).json()["weakest"]

    assert weakest["form"] == "past_perfect_continuous"
    assert weakest["scenario_slug"] is None
    assert weakest["reason"].endswith("No scenario is written to draw it out yet.")


# ── The sentence around a correction ────────────────────────────────────────


def test_the_sentence_is_cut_at_its_own_boundaries():
    text = "First sentence. Then I go there and stay. Last one?"
    start = text.index("I go")
    assert excerpt(text, start, start + 4, "I go") == (
        "Then ",
        "I go",
        " there and stay.",
    )


def test_the_transcripts_spelling_is_kept_when_only_capitals_and_spaces_differ():
    text = "yesterday i  go to work"
    start = text.index("i  go")
    assert excerpt(text, start, start + 5, "I go")[1] == "i  go"


def test_offsets_that_do_not_hold_the_words_place_nothing():
    """A sentence cut around the wrong words would put the correction on something the
    speaker got right."""
    text = "Yesterday I went to the office."
    assert excerpt(text, 10, 16, "I go") == ("", None, "")
    assert excerpt(text, None, None, "I go") == ("", None, "")
    assert excerpt(text, 10, 999, "I go") == ("", None, "")


def test_an_unpunctuated_turn_is_not_quoted_whole():
    """The recogniser often writes a whole turn as one sentence."""
    words = " ".join(f"word{n}" for n in range(60))
    text = f"{words} I go {words}"
    start = text.index("I go")
    before, quote, after = excerpt(text, start, start + 4, "I go")

    assert quote == "I go"
    assert before.startswith("…") and after.endswith("…")
    assert len(before) <= GRAMMAR_CONTEXT_CHARS + 1
    assert len(after) <= GRAMMAR_CONTEXT_CHARS + 1
    assert not before[1:].startswith(" ") and "word" in before
