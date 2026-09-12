"""The history export: everything the account made, in one document, and nobody else's.

Rows are inserted directly rather than produced by practising through the API, as in the
progress suite. What is tested here is that every table reaches the document under the
right parent — a correction under the turn it was found in, a phone under its reading —
not the pipeline that fills the tables.
"""

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import select

from db_models import (
    Answer,
    AnswerPrompt,
    Attempt,
    AudioAsset,
    FluencyMetrics,
    GrammarUsage,
    LanguageError,
    Passage,
    PhonemeScore,
    PracticeSession,
    ProgressSnapshot,
    Scenario,
    Turn,
)
from tests.conftest import register_account

HISTORY = ("recordings", "sessions", "readings", "answers", "snapshots")


@pytest.fixture
async def practised(client, account, db_session, seeded):
    """The signed-in account, with one of everything the export carries."""
    user_id = account["id"]
    scenario = await db_session.scalar(
        select(Scenario).where(Scenario.slug == "daily-standup")
    )
    passage = await db_session.scalar(select(Passage).order_by(Passage.id).limit(1))
    prompt = await db_session.scalar(
        select(AnswerPrompt).order_by(AnswerPrompt.id).limit(1)
    )

    turn_audio = AudioAsset(
        user_id=user_id,
        path=f"{user_id}/turn.wav",
        duration_ms=3200,
        sample_rate=16000,
        format="wav",
        sha256="a" * 64,
    )
    reading_audio = AudioAsset(
        user_id=user_id,
        path=f"{user_id}/reading.wav",
        duration_ms=5100,
        sample_rate=16000,
        format="wav",
        sha256="b" * 64,
    )
    db_session.add_all([turn_audio, reading_audio])
    await db_session.flush()

    conversation = PracticeSession(
        user_id=user_id,
        scenario_id=scenario.id,
        mode="conversation",
        status="completed",
        report={"measured": {"words": 6}},
    )
    reading_session = PracticeSession(user_id=user_id, mode="read_aloud")
    db_session.add_all([conversation, reading_session])
    await db_session.flush()

    said = Turn(
        session_id=conversation.id,
        idx=0,
        role="user",
        transcript="yesterday I go to the office",
        words=[{"w": "yesterday", "start_ms": 0, "end_ms": 420, "logprob": -0.1}],
        asr_confidence=0.95,
        audio_asset_id=turn_audio.id,
        analysis_status="analyzed",
        analyzed_at=datetime.now(timezone.utc),
    )
    reply = Turn(
        session_id=conversation.id,
        idx=1,
        role="assistant",
        transcript="Which office was it?",
        llm_model="gemma3:4b",
    )
    db_session.add_all([said, reply])
    await db_session.flush()
    db_session.add_all(
        [
            FluencyMetrics(
                turn_id=said.id, word_count=6, speech_rate_wpm=118.0, filler_count=0
            ),
            GrammarUsage(turn_id=said.id, feature="present_simple", count=1),
            LanguageError(
                turn_id=said.id,
                category="VERB_TENSE",
                original="I go",
                correction="I went",
                detector="llm",
                confidence=0.9,
            ),
        ]
    )

    attempt = Attempt(
        session_id=reading_session.id,
        passage_id=passage.id,
        audio_asset_id=reading_audio.id,
        status="scored",
        transcript="the ship was in bad shape",
        wer=0.0,
        scored_at=datetime.now(timezone.utc),
    )
    db_session.add(attempt)
    await db_session.flush()
    db_session.add(
        PhonemeScore(
            attempt_id=attempt.id,
            word="ship",
            word_idx=1,
            phone_idx=0,
            canonical_phone="SH",
            recognized_phone="SH",
            gop=-0.4,
        )
    )

    first = Answer(
        user_id=user_id,
        prompt_id=prompt.id,
        transcript="it failed because the cache was cold",
        words=[],
        delivery={"words": 7},
        structure={"words": 7},
    )
    db_session.add(first)
    await db_session.flush()
    db_session.add(
        Answer(
            user_id=user_id,
            prompt_id=prompt.id,
            again_of=first.id,
            transcript="the cache was cold so it failed",
            words=[],
            delivery={"words": 7},
            structure={"words": 7},
            feedback={"status": "ok"},
        )
    )
    db_session.add(
        ProgressSnapshot(
            user_id=user_id,
            period="week",
            period_start=date(2026, 9, 7),
            fluency={"words_spoken": 6},
        )
    )
    await db_session.commit()

    return {
        "scenario": scenario.slug,
        "passage": passage.slug,
        "prompt": prompt.slug,
        "turn_audio": turn_audio.id,
        "reading_audio": reading_audio.id,
    }


async def test_the_export_needs_an_account(client):
    assert (await client.get("/progress/export")).status_code == 401


async def test_a_new_account_exports_an_empty_history_and_no_password(client, account):
    response = await client.get("/progress/export")

    assert response.status_code == 200
    body = response.json()
    assert body["account"]["email"] == account["email"]
    for key in HISTORY:
        assert body[key] == []
    assert "password" not in response.text
    assert "$argon2" not in response.text


async def test_it_arrives_as_a_file_to_save(client, account):
    response = await client.get("/progress/export")

    disposition = response.headers["content-disposition"]
    assert disposition.startswith("attachment;")
    assert 'filename="speaklab-history-' in disposition
    assert disposition.endswith('.json"')
    assert response.headers["content-type"].startswith("application/json")


async def test_a_conversation_carries_its_turns_and_what_was_found_in_each(
    client, practised
):
    body = (await client.get("/progress/export")).json()

    conversation, reading = body["sessions"]
    assert conversation["scenario_slug"] == practised["scenario"]
    assert conversation["report"] == {"measured": {"words": 6}}

    said, reply = conversation["turns"]
    assert said["transcript"] == "yesterday I go to the office"
    assert said["words"][0]["w"] == "yesterday"
    assert said["audio_url"] == f"/audio/{practised['turn_audio']}"
    assert said["fluency"]["speech_rate_wpm"] == 118.0
    assert said["forms"] == {"present_simple": 1}
    assert [(c["original"], c["correction"]) for c in said["corrections"]] == [
        ("I go", "I went")
    ]

    assert reply["llm_model"] == "gemma3:4b"
    assert reply["fluency"] is None
    assert reply["corrections"] == []

    assert reading["mode"] == "read_aloud"
    assert reading["turns"] == []


async def test_a_reading_carries_its_passage_and_its_scored_sounds(client, practised):
    body = (await client.get("/progress/export")).json()

    [reading] = body["readings"]
    assert reading["passage_slug"] == practised["passage"]
    assert reading["session_id"] == body["sessions"][1]["id"]
    assert reading["audio_url"] == f"/audio/{practised['reading_audio']}"
    assert [(p["word"], p["canonical_phone"]) for p in reading["phones"]] == [
        ("ship", "SH")
    ]


async def test_answers_snapshots_and_recordings_are_all_there(client, practised):
    body = (await client.get("/progress/export")).json()

    first, again = body["answers"]
    assert first["prompt_slug"] == practised["prompt"]
    assert again["again_of"] == first["id"]
    assert again["feedback"] == {"status": "ok"}

    [snapshot] = body["snapshots"]
    assert snapshot["period_start"] == "2026-09-07"

    assert {row["id"] for row in body["recordings"]} == {
        practised["turn_audio"],
        practised["reading_audio"],
    }
    for row in body["recordings"]:
        assert row["url"] == f"/audio/{row['id']}"


async def test_another_account_exports_only_its_own_empty_history(
    practised, other_client
):
    """No shape of this operation takes a user id; the stranger gets their own file."""
    stranger = await register_account(other_client)

    body = (await other_client.get("/progress/export")).json()

    assert body["account"]["id"] == stranger["id"]
    for key in HISTORY:
        assert body[key] == []
