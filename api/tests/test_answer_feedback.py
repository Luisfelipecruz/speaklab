"""The model's feedback on an answer: the check on its rewrite, and a call that never raises.

The check is tested against sentences written for it, with no model. The call is tested
against a scripted provider: what it asks for, what it keeps, what it withholds, and
that every way a model can fail leaves a status rather than an exception. What a real
model does with real answers is a measurement, in `tests/test_answer_measures.py`.
"""

import asyncio
import json

from config import ANSWER_REWRITE_MAX_INVENTED
from services import answer_feedback
from services.llm import LlmRejected
from tests.conftest import BrokenProvider, StubProvider

ANSWER = (
    "We rolled back because the new version expected a field the app does not send. "
    "In short, a missing field."
)
PROMPT = "Your manager asks what happened. Explain it."


def reply(**fields) -> str:
    body = {
        "lead": "Say first that a missing field broke payments.",
        "gaps": ["why the app does not send the field"],
        "rewrite": "We rolled back because the new version expected a field the app "
        "does not send.",
    }
    body.update(fields)
    return json.dumps(body)


# ── The check ───────────────────────────────────────────────────────────────


def test_a_rewrite_in_the_speakers_own_words_invents_nothing():
    rewrite = "We rolled back, because the new version expected a field the app does not send."
    assert answer_feedback.invented(ANSWER, PROMPT, rewrite) == []


def test_a_new_figure_and_a_new_name_are_invented():
    words = answer_feedback.invented(
        ANSWER, PROMPT, "We rolled back after 300 Android users could not pay."
    )
    assert "300" in words
    assert "Android" in words


def test_a_word_is_matched_by_its_lemma_and_counted_once():
    assert (
        answer_feedback.invented(ANSWER, PROMPT, "The app was not sending fields.")
        == []
    )
    words = answer_feedback.invented(
        ANSWER, PROMPT, "Customers lost orders. Customers left."
    )
    assert words.count("Customers") == 1


def test_the_words_of_a_signpost_are_structure_and_not_content():
    rewrite = (
        "The main reason is a missing field. For example, the app. To sum up, a field."
    )
    assert answer_feedback.invented(ANSWER, PROMPT, rewrite) == []


def test_the_prompt_is_something_the_speaker_was_given():
    assert (
        answer_feedback.invented(ANSWER, PROMPT, "My manager asked what happened.")
        == []
    )


# ── The call ────────────────────────────────────────────────────────────────


async def test_feedback_that_keeps_to_the_answer_is_shown_whole():
    stub = StubProvider([reply()])

    result = await answer_feedback.ask(stub, PROMPT, ANSWER)

    assert result["status"] == "ok"
    assert result["lead"] == "Say first that a missing field broke payments."
    assert result["gaps"] == ["why the app does not send the field"]
    assert result["rewrite"].startswith("We rolled back")
    assert result["rewrite_sentences"] == 1
    assert result["invented"] == []
    # Feedback is asked for at temperature zero, so the same answer reads the same way.
    assert stub.temperatures == [0.0]


async def test_a_rewrite_that_adds_facts_is_withheld_and_the_words_are_kept():
    stub = StubProvider(
        [
            reply(
                rewrite="We rolled back after 300 Android customers lost orders on Friday."
            )
        ]
    )

    result = await answer_feedback.ask(stub, PROMPT, ANSWER)

    assert result["status"] == "refused"
    assert result["rewrite"] is None
    assert result["withheld_rewrite"].startswith("We rolled back after 300")
    assert len(result["invented"]) > ANSWER_REWRITE_MAX_INVENTED
    assert result["lead"]  # the notes are still shown


async def test_a_note_about_how_it_sounded_is_dropped_and_counted():
    stub = StubProvider(
        [
            reply(
                lead="Your pronunciation of field was unclear.",
                gaps=["You sounded nervous when you explained the rollback."],
            )
        ]
    )

    result = await answer_feedback.ask(stub, PROMPT, ANSWER)

    assert result["lead"] is None
    assert result["gaps"] == []
    assert result["dropped_notes"] == 2
    assert result["status"] == "ok"


async def test_a_model_that_is_down_leaves_a_status_not_an_exception():
    result = await answer_feedback.ask(BrokenProvider(), PROMPT, ANSWER)

    assert result["status"] == "unavailable"
    assert "LlmUnavailable" in result["detail"]


async def test_a_refused_request_is_unavailable_too():
    broken = BrokenProvider(LlmRejected("model 'gemma3:4b' not found", 404))

    result = await answer_feedback.ask(broken, PROMPT, ANSWER)

    assert result["status"] == "unavailable"


async def test_prose_instead_of_json_is_unparseable_and_quoted():
    result = await answer_feedback.ask(
        StubProvider(["Great answer! Well done."]), PROMPT, ANSWER
    )

    assert result["status"] == "unparseable"
    assert result["detail"].startswith("Great answer")


async def test_a_model_that_takes_too_long_is_cut_off(monkeypatch):
    class Slow(StubProvider):
        async def complete(self, messages, max_tokens=None, temperature=None):
            await asyncio.sleep(1)
            return await super().complete(messages, max_tokens, temperature)

    monkeypatch.setattr(answer_feedback, "ANSWER_FEEDBACK_TIMEOUT_S", 0.01)

    result = await answer_feedback.ask(Slow([reply()]), PROMPT, ANSWER)

    assert result["status"] == "unavailable"
    assert "no answer within" in result["detail"]


async def test_an_answer_with_no_words_is_not_sent_to_the_model():
    stub = StubProvider([reply()])

    result = await answer_feedback.ask(stub, PROMPT, "Um.")

    assert result["status"] == "skipped"
    assert stub.calls == []


async def test_the_model_is_given_the_prompt_the_answer_and_that_it_did_not_hear_it():
    stub = StubProvider([reply()])

    await answer_feedback.ask(stub, PROMPT, ANSWER)

    (system, user) = stub.calls[0]
    assert "did not hear" in system.content
    assert PROMPT in user.content
    assert ANSWER in user.content
