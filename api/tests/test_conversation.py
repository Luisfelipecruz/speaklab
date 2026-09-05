"""The conversation loop, with no model running.

What is under test here is everything the conversation loop decides: what goes into a
prompt, how much of the history fits, what happens to the rest, how a reply becomes
sentences and then one WAV, and what a report is allowed to claim. None of that needs Ollama, and a
suite that required it would be a suite that only runs on one machine.

The measurements live in `test_conversation_live.py`, which skips unless the real
containers answer. The split is the same one every other service suite makes: logic here,
numbers there, and no number in this file.
"""

import asyncio

import pytest

from db_models import PracticeSession, Scenario, Turn
from services.conversation import (
    GUARDRAILS,
    SentenceAccumulator,
    build_messages,
    build_report,
    generate_reply,
    narrate_report,
    select_history,
    summarise,
    system_message,
)
from services.llm import estimate_messages
from tests.conftest import BrokenProvider, StubProvider

PERSONA = (
    "You are Dana, a hiring manager at a logistics company, interviewing the user for a "
    "backend engineer position. Ask one follow-up question after every answer."
)


@pytest.fixture
def scenario() -> Scenario:
    """An unsaved row. Nothing here touches the database — these are pure functions."""
    return Scenario(
        id=1,
        slug="job-interview-backend",
        title="Job interview",
        description="A screening call.",
        category="professional",
        cefr_band="B2",
        persona_prompt=PERSONA,
        goal="The candidate has described one project in technical detail.",
        target_grammar=["present_perfect"],
        target_functions=["describe_experience"],
        rubric={
            "criteria": [{"name": "task_completion", "descriptor": "..."}],
            "min_turns": 8,
        },
        is_active=True,
    )


def conversation(count: int, words: int = 12) -> list[Turn]:
    """`count` turns alternating user and assistant, each `words` long."""
    return [
        Turn(
            idx=index,
            role="user" if index % 2 == 0 else "assistant",
            transcript=f"Turn {index}. " + " ".join(["word"] * words),
        )
        for index in range(count)
    ]


# ── Persona anchoring ───────────────────────────────────────────────────────


def test_the_persona_is_in_every_request_however_long_the_conversation(scenario):
    """A persona that survives only in the history does not survive."""
    for length in (0, 2, 10, 40):
        messages = build_messages(scenario, None, conversation(length), "And then?")
        assert any(PERSONA in message.content for message in messages), length


def test_the_persona_is_anchored_again_at_the_end_not_only_at_the_front(scenario):
    """The measured reason, from `curl /api/show`: **Gemma 3 has no system role.**
    Ollama's template renders a system message as an ordinary `<start_of_turn>user`
    block wherever it sits, so "put it in the system message" means "put it in the first
    user turn" — forty turns away from where the reply gets written.

    So there are two anchors, and this asserts the second one is genuinely near the end
    rather than being the first one counted twice.
    """
    messages = build_messages(scenario, None, conversation(20), "So, about that.")

    anchored = [i for i, message in enumerate(messages) if "Dana" in message.content]
    assert len(anchored) >= 2, "only one anchor: the tail re-anchor is missing"
    assert anchored[-1] >= len(messages) - 2, (
        "the last mention of the persona is not near the end of the prompt, which is "
        "the only position that does anything on a model with no system channel"
    )


def test_the_last_message_is_what_the_speaker_just_said(scenario):
    """The tail anchor goes *before* the utterance, not after it. After it, the model is
    answering the reminder rather than the person."""
    messages = build_messages(scenario, None, conversation(4), "I led the migration.")

    assert messages[-1].role == "user"
    assert messages[-1].content == "I led the migration."


def test_the_opening_turn_has_no_user_message_to_reply_to(scenario):
    """There is nothing to answer yet, so the instruction to begin has to be the last
    thing the model reads."""
    messages = build_messages(scenario, None, [], None)

    assert all(message.role != "user" for message in messages)
    assert "Open the conversation" in messages[-1].content


def test_the_guardrails_travel_with_the_persona(scenario):
    """The length cap is a latency control and the ASR line guards against the
    recogniser's errors. Neither is something a scenario author should remember."""
    content = system_message(scenario, None).content

    assert GUARDRAILS in content
    assert scenario.goal in content


def test_the_persona_is_told_it_does_not_know_the_speakers_name(scenario):
    """The fix for a bug found in a real standup, and the reason it is a guardrail.

    `daily-standup` produced "Good morning, [User Name]." in **4 of 7** stored replies,
    where every other scenario produced none. The persona says "Greet the user", and a
    greeting in a standup is a template slot in most of the text this model was trained
    on — so the model supplied one. **Nothing in any prompt ever contained a placeholder.**

    Measured against the live model on the opening turn, n = 12 per arm: **12/12 without
    this instruction, 0/12 with it.** `test_conversation_live.py` re-runs that.

    It is a guardrail rather than a fix to one seed because the cause is not that
    scenario's wording — it is that the system has no name to give, and any persona asked
    to greet somebody can reach for a placeholder. `users` has an email and a native
    language and nothing a character could say out loud.
    """
    content = system_message(scenario, None).content

    assert "do not know the speaker's name" in content
    assert "[Name]" in content, "the placeholder shape is named explicitly, not implied"
    assert "never invent a name" in content


def test_a_turn_with_no_transcript_is_not_sent_as_an_empty_message(scenario):
    """A recording the recogniser returned nothing for is a real row. Sent as an empty
    user message it reads to the model as the speaker having said nothing, which is a
    different thing from them not having been understood."""
    turns = [
        Turn(idx=0, role="user", transcript="Hello."),
        Turn(idx=1, role="assistant", transcript=None),
        Turn(idx=2, role="user", transcript="   "),
    ]
    messages = build_messages(scenario, None, turns, "Anyway.")

    assert all(message.content.strip() for message in messages)


def test_the_digest_is_not_presented_as_something_somebody_said(scenario):
    """It goes in the system message, not into history as a fake assistant turn. A
    summary quoted back as though the persona had said it is a persona that repeats
    itself."""
    messages = build_messages(
        scenario, "They discussed Berlin and a 2019 migration.", [], "Go on."
    )

    assert "Berlin" in messages[0].content
    assert not any(
        "Berlin" in message.content
        for message in messages[1:]
        if message.role == "assistant"
    )


# ── The token budget ────────────────────────────────────────────────────────


def test_a_long_conversation_is_trimmed_to_fit(scenario, monkeypatch):
    """The cliff this protects against is measured in config.LLM_NUM_CTX: one token over
    and llama.cpp discards half the prompt and answers anyway, with no error."""
    monkeypatch.setattr("services.conversation.LLM_MAX_INPUT_TOKENS", 600)

    turns = conversation(200)
    window = select_history(scenario, None, turns, "And then what happened?")

    assert window.kept, "everything was dropped"
    assert len(window.kept) < len(turns)
    assert window.estimated_tokens <= 600

    messages = build_messages(scenario, None, window.kept, "And then what happened?")
    assert estimate_messages(messages) <= 600


def test_the_newest_turns_are_the_ones_kept(scenario, monkeypatch):
    """Recency is what a reply is about. The old turns are the ones a digest can carry;
    the reverse would summarise what was just said and quote what was forgotten."""
    monkeypatch.setattr("services.conversation.LLM_MAX_INPUT_TOKENS", 600)

    turns = conversation(200)
    window = select_history(scenario, None, turns, "Go on.")

    assert window.kept[-1] is turns[-1]
    assert window.overflow[0] is turns[0]
    assert len(window.kept) + len(window.overflow) == len(turns)


def test_nothing_is_both_kept_and_overflowed(scenario, monkeypatch):
    """The two lists partition the conversation. An overlap would put the same exchange
    in the prompt and in the digest, and the persona would appear to remember it twice.
    """
    monkeypatch.setattr("services.conversation.LLM_MAX_INPUT_TOKENS", 600)

    window = select_history(scenario, None, conversation(200), "Go on.")

    kept = {id(turn) for turn in window.kept}
    overflowed = {id(turn) for turn in window.overflow}
    assert not (kept & overflowed)


def test_a_short_conversation_needs_no_summary(scenario):
    window = select_history(scenario, None, conversation(4), "Go on.")

    assert window.overflow == []
    assert window.should_summarise is False


def test_summarising_is_triggered_before_the_budget_is_actually_reached(
    scenario, monkeypatch
):
    """The high-water mark is the whole design. At the mark every turn still fits, so
    the fold that follows is preparation for the *next* turn — which is what makes it
    correct to run it after the reply has been sent rather than while somebody waits."""
    monkeypatch.setattr("services.conversation.LLM_MAX_INPUT_TOKENS", 900)

    marked = None
    for length in range(2, 120, 2):
        window = select_history(scenario, None, conversation(length), "Go on.")
        if window.should_summarise and marked is None:
            marked = window
        if window.overflow:
            assert marked is not None, (
                "turns fell out of the window before summarisation was ever asked for, "
                "so a turn's worth of conversation was dropped rather than summarised"
            )
            break

    assert marked is not None and marked.overflow == [], (
        "summarisation was first requested on a conversation that had already lost "
        "turns; the mark is not below the budget"
    )


# ── Summarisation ───────────────────────────────────────────────────────────


async def test_the_summary_prompt_carries_the_turns_it_is_summarising(scenario):
    provider = StubProvider(["They talked about Berlin."])
    overflow = [
        Turn(
            idx=0,
            role="user",
            transcript="My name is Ana and I moved to Berlin in 2019.",
        ),
        Turn(idx=1, role="assistant", transcript="What brought you there?"),
    ]

    await summarise(provider, None, overflow)

    sent = "\n".join(message.content for message in provider.calls[0])
    assert "Ana" in sent and "Berlin" in sent and "2019" in sent


async def test_the_summary_instruction_demands_the_entities_be_kept(scenario):
    """The way a summary silently becomes a drop is by keeping the gist and losing the
    name, the number and the date that later turns refer back to. The instruction is
    what stands between summarising and dropping, so it is asserted not assumed."""
    provider = StubProvider(["..."])
    await summarise(
        provider, None, [Turn(idx=0, role="user", transcript="Hello there.")]
    )

    instruction = provider.calls[0][0].content
    for word in ("name", "number", "date"):
        assert word in instruction.lower()


async def test_an_existing_digest_is_rewritten_rather_than_appended_to(scenario):
    """A digest that grows by concatenation is the context problem it was written to
    solve, arriving a hundred turns later."""
    provider = StubProvider(["Ana, from Berlin, then described a migration."])
    result = await summarise(
        provider,
        "Ana introduced herself and said she is from Berlin.",
        [Turn(idx=4, role="user", transcript="I led a migration off Oracle in 2021.")],
    )

    sent = "\n".join(message.content for message in provider.calls[0])
    assert "Existing summary:" in sent
    assert "Ana introduced herself" in sent
    assert result == "Ana, from Berlin, then described a migration."


async def test_summarising_nothing_returns_the_digest_unchanged(scenario):
    """No model call for turns with no text in them."""
    provider = StubProvider()
    result = await summarise(
        provider,
        "The existing summary.",
        [Turn(idx=0, role="assistant", transcript=None)],
    )

    assert result == "The existing summary."
    assert provider.calls == []


def test_a_digest_reaches_the_next_prompt(scenario):
    """The end of the loop: what was summarised has to come back. Without this the
    digest is written and never read, which is the same as dropping the turns."""
    messages = build_messages(
        scenario,
        "Ana is from Berlin and led an Oracle migration in 2021.",
        conversation(4),
        "Go on.",
    )

    assembled = "\n".join(message.content for message in messages)
    assert "Ana" in assembled and "Berlin" in assembled and "2021" in assembled


# ── Splitting a reply into sentences ────────────────────────────────────────


def test_sentences_are_emitted_as_soon_as_they_are_complete():
    """The point of the whole streaming path: sentence one goes to the voice while
    sentence two is still being written."""
    accumulator = SentenceAccumulator()

    assert accumulator.feed("That sounds like a difficult project. ") == [
        "That sounds like a difficult project."
    ]
    assert accumulator.feed("What was the hardest part") == []
    assert accumulator.feed("? ") == ["What was the hardest part?"]


def test_a_decimal_point_is_not_a_sentence_boundary():
    """Streaming makes this a real hazard rather than a pedantic one: "It cost 3." is a
    complete-looking buffer for the few milliseconds before "5 million" arrives."""
    accumulator = SentenceAccumulator()

    assert accumulator.feed("The migration moved about 3.") == []
    assert accumulator.feed("5 million rows overnight. ") == [
        "The migration moved about 3.5 million rows overnight."
    ]


def test_an_abbreviation_does_not_split_the_sentence():
    accumulator = SentenceAccumulator()
    assert accumulator.feed("Dr. ") == []
    assert accumulator.feed("Ferreira ran that team for six years. ") == [
        "Dr. Ferreira ran that team for six years."
    ]


def test_an_initial_does_not_split_the_sentence():
    accumulator = SentenceAccumulator()
    accumulator.feed("The report was by J. ")
    accumulator.feed("R. ")
    assert accumulator.feed("Hoffman last spring. ") == [
        "The report was by J. R. Hoffman last spring."
    ]


def test_a_genuinely_short_sentence_is_still_a_sentence():
    """The first version of this guard was a minimum sentence *length*, and it was wrong
    in a way this test exists to keep out. The guardrails ask the persona for two or
    three sentences and it obliges with short ones; a 24-character floor swallowed "That
    is a good point." into the sentence after it — defeating the streaming it was meant
    to protect, on exactly the replies where the first sentence arriving early matters
    most."""
    accumulator = SentenceAccumulator()

    assert accumulator.feed("That is a good point. ") == ["That is a good point."]
    assert accumulator.feed("I see. ") == ["I see."]


def test_the_tail_of_a_truncated_reply_is_not_lost():
    """`num_predict` truncation produces a reply with no final full stop. Dropping the
    remainder would silently shorten every reply that hit the cap."""
    accumulator = SentenceAccumulator()
    complete = accumulator.feed("I see. And then what happened after the")

    assert complete == ["I see."]
    assert accumulator.flush() == ["And then what happened after the"]
    assert accumulator.flush() == []


def test_the_sentences_reassemble_into_the_reply():
    """No word may be lost between the model and the voice. Punctuation and spacing can
    move; content cannot."""
    reply = "That is interesting. How long did it take? I would have expected longer."
    accumulator = SentenceAccumulator()

    found = []
    for character in reply:
        found.extend(accumulator.feed(character))
    found.extend(accumulator.flush())

    assert " ".join(found).split() == reply.split()


# ── Generating and speaking ─────────────────────────────────────────────────


async def test_a_reply_is_generated_spoken_and_joined_into_one_file(scenario, voice):
    provider = StubProvider(
        ["That is a good point. What happened after the migration?"]
    )
    messages = build_messages(scenario, None, [], None)

    reply = await generate_reply(provider, messages, stream_to_tts=True)

    assert reply.text.startswith("That is a good point.")
    assert reply.sentences == 2
    assert len(voice) == 2, "the reply was not split before synthesis"
    assert reply.audio and reply.audio.startswith(b"RIFF")
    assert reply.speech_status == "ok"
    assert reply.duration_ms and reply.duration_ms > 0


async def test_streaming_and_not_streaming_produce_the_same_reply(scenario, voice):
    """Overlapping synthesis with generation is a latency optimisation and must not be a
    behaviour change. If the two paths could differ in what they say, the measurement
    comparing them would be comparing two products."""
    messages = build_messages(scenario, None, [], None)
    text = "One thing at a time. Which system did you migrate first? I am curious."

    streamed = await generate_reply(StubProvider([text]), messages, stream_to_tts=True)
    whole = await generate_reply(StubProvider([text]), messages, stream_to_tts=False)

    assert streamed.text == whole.text
    assert streamed.sentences == whole.sentences
    assert streamed.duration_ms == whole.duration_ms


async def test_synthesis_runs_while_generation_is_still_going(scenario, monkeypatch):
    """The claim the fallback rests on, asserted rather than described.

    The provider blocks between sentences; the voice records the wall clock at which
    each call arrived. If synthesis of the first sentence starts before the last delta
    has been produced, the paths genuinely overlap.
    """
    from models.speech import Speech
    from services import conversation
    from tests.conftest import silent_wav

    started_at: list[float] = []
    generation_finished_at: list[float] = []

    async def slow_speak(text, voice=None, length_scale=None, client=None):
        started_at.append(asyncio.get_running_loop().time())
        await asyncio.sleep(0.02)
        return Speech(
            audio=silent_wav(100),
            voice="stub",
            sample_rate=22050,
            duration_ms=100,
            sentences=1,
            length_scale=1.0,
            latency_ms=1,
        )

    monkeypatch.setattr(conversation, "speak", slow_speak)

    class SlowProvider(StubProvider):
        async def stream(self, messages, max_tokens=None):
            self.calls.append(messages)
            from services.llm import Completion

            text = "First sentence here, long enough. "
            yield text
            await asyncio.sleep(0.05)
            yield "Second sentence follows it. "
            generation_finished_at.append(asyncio.get_running_loop().time())
            yield Completion(
                text=text + "Second sentence follows it.",
                model="stub",
                latency_ms=50,
            )

    await generate_reply(SlowProvider(), [], stream_to_tts=True)

    assert started_at, "nothing was synthesised"
    assert started_at[0] < generation_finished_at[0], (
        "the first sentence was not sent to the voice until generation had finished, "
        "so the two never overlapped and the optimisation is not in effect"
    )


async def test_a_silent_voice_does_not_cost_the_speaker_their_reply(
    scenario, monkeypatch
):
    """The degradation decision. A reply that can be read is worth more than a 502, and
    the endpoint says which happened rather than pretending the turn had no audio."""
    from services import conversation
    from services.tts_client import TtsUnavailable

    async def broken_speak(text, voice=None, length_scale=None, client=None):
        raise TtsUnavailable("ConnectError: refused")

    monkeypatch.setattr(conversation, "speak", broken_speak)

    reply = await generate_reply(StubProvider(["I understand. Tell me more."]), [])

    assert reply.text == "I understand. Tell me more."
    assert reply.audio is None
    assert reply.speech_status == "unavailable"
    assert "refused" in (reply.speech_detail or "")


async def test_text_the_voice_refuses_is_reported_as_a_rejection_not_an_outage(
    monkeypatch,
):
    """The voice returns 422 for text that phonemises to nothing. Retrying it forever
    would be a loop against a reply that can never be spoken."""
    from services import conversation
    from services.tts_client import TtsRejected

    async def refusing_speak(text, voice=None, length_scale=None, client=None):
        raise TtsRejected("text produced no speech", 422)

    monkeypatch.setattr(conversation, "speak", refusing_speak)

    reply = await generate_reply(StubProvider(["— — —"]), [])

    assert reply.speech_status == "rejected"
    assert reply.audio is None


async def test_a_provider_that_is_down_raises_rather_than_inventing_a_reply(voice):
    """Never a fabricated reply. The exception has to reach the endpoint."""
    from services.llm import LlmUnavailable

    with pytest.raises(LlmUnavailable):
        await generate_reply(BrokenProvider(), [])


# ── The session report ──────────────────────────────────────────────────────


def build_finished_session(scenario) -> tuple[PracticeSession, list[Turn]]:
    from datetime import datetime, timedelta, timezone

    started = datetime(2026, 8, 30, 10, 0, tzinfo=timezone.utc)
    session = PracticeSession(
        id=1,
        user_id=1,
        scenario_id=scenario.id,
        mode="conversation",
        status="active",
        started_at=started,
        ended_at=started + timedelta(minutes=6),
    )
    turns = [
        Turn(
            idx=0,
            role="assistant",
            transcript="Tell me about yourself.",
            latency_ms=900,
        ),
        Turn(
            idx=1,
            role="user",
            transcript="I have worked on backend systems for six years.",
            words=[
                {"w": w, "start_ms": 0, "end_ms": 1, "logprob": -0.2} for w in range(9)
            ],
            asr_confidence=0.9,
        ),
        Turn(
            idx=2,
            role="assistant",
            transcript="Which project stands out?",
            latency_ms=1100,
        ),
    ]
    return session, turns


def test_the_report_separates_what_was_counted_from_what_was_written(scenario):
    """Invariant I1, made structural. A flat report with a `goal_met` boolean next to a
    turn count is one refactor away from something plotting a language model's opinion
    over time; nested, the provenance travels with the value."""
    session, turns = build_finished_session(scenario)
    report = build_report(session, scenario, turns, {"status": "ok", "goal_met": True})

    assert report["measured"]["turns"]["user"] == 1
    assert report["measured"]["words_spoken"] == 9
    assert report["measured"]["duration_ms"] == 360_000
    assert report["narrative"]["goal_met"] is True
    assert "goal_met" not in report["measured"]


def test_the_report_names_what_it_cannot_yet_compute(scenario):
    """The report is meant to carry errors with corrections and declared forms never
    elicited, and there is no analyser for either yet. Omitting the keys would read as a
    session that simply had no errors in it."""
    session, turns = build_finished_session(scenario)
    report = build_report(session, scenario, turns)

    assert set(report["pending"]) == {
        "fluency",
        "errors",
        "grammar_usage",
        "pronunciation",
    }
    # Each entry says what is missing, rather than being a bare label.
    assert all(len(value.split()) >= 4 for value in report["pending"].values())


def test_the_report_uses_a_median_latency_not_a_mean(scenario):
    """One cold model load adds ~2.6 s to whichever turn it lands on. A mean over eight
    turns would report that as the conversation having been slow."""
    session, turns = build_finished_session(scenario)
    turns.append(Turn(idx=3, role="assistant", transcript="I see.", latency_ms=9000))

    report = build_report(session, scenario, turns)

    assert report["measured"]["median_turn_latency_ms"] == 1100


def test_the_report_says_whether_the_rubric_minimum_was_reached(scenario):
    session, turns = build_finished_session(scenario)
    report = build_report(session, scenario, turns)

    assert report["measured"]["min_turns"] == 8
    assert report["measured"]["reached_min_turns"] is False


async def test_the_narrative_asserts_it_did_not_hear_anything(scenario):
    """Invariant I2 in the one place it could plausibly be broken. The model is reading
    a transcript; a remark about how somebody sounded would be invented."""
    session, turns = build_finished_session(scenario)
    provider = StubProvider(
        ['{"summary": "They talked.", "goal_met": false, "note": "Clear."}']
    )

    result = await narrate_report(provider, scenario, turns)

    instruction = provider.calls[0][0].content
    assert "did not hear" in instruction
    assert "pronunciation" in instruction
    assert result["goal_met"] is False


async def test_a_narrative_wrapped_in_a_code_fence_is_still_read(scenario):
    """Small models fence their JSON more often than not, and a report that said
    'unparseable' because of three backticks would be reporting on the fence."""
    session, turns = build_finished_session(scenario)
    provider = StubProvider(['```json\n{"summary": "Fine.", "goal_met": true}\n```'])

    result = await narrate_report(provider, scenario, turns)

    assert result["status"] == "ok"
    assert result["goal_met"] is True


async def test_a_narrative_that_is_not_json_is_recorded_as_exactly_that(scenario):
    """Salvaging prose into `summary` would make the report unable to distinguish a
    model that answered from a model that apologised."""
    session, turns = build_finished_session(scenario)
    provider = StubProvider(["I am sorry, I cannot help with that."])

    result = await narrate_report(provider, scenario, turns)

    assert result["status"] == "unparseable"
    assert "sorry" in result["detail"]


async def test_ending_a_session_survives_the_model_being_down(scenario):
    """A session stuck in `active` because a container was restarting is a worse failure
    than a report with a missing paragraph."""
    session, turns = build_finished_session(scenario)

    result = await narrate_report(BrokenProvider(), scenario, turns)

    assert result["status"] == "unavailable"
    assert "LlmUnavailable" in result["detail"]
