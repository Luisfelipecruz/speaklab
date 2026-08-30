"""`POST /sessions/{id}/turns` — the endpoint the product is about. FR-7.

Audio in, transcript, persona reply, speech out, persisted. The recogniser, the voice and
the model are all stubbed: what is being tested is the orchestration, which is the part
this codebase decided. `test_conversation_live.py` runs the same path against the real
containers and is where every published number comes from.

Three properties here are worth more than the rest, and each has a test that fails loudly
if it is undone:

* **a turn is atomic** — both halves are written or neither is;
* **no database connection is held while the models work** — the endpoint takes seconds
  and the pool has ten connections;
* **the voice failing does not cost the speaker their reply.**
"""

import pytest
from sqlalchemy import func, select

from db_models import AudioAsset, PracticeSession, Turn, User
from services.llm import get_provider
from tests.conftest import BrokenProvider, StubProvider, register_account, unique_email

SLUG = "job-interview-backend"
RECORDING = b"RIFF$\x00\x00\x00WAVEfmt " + bytes(range(64))


async def start(client):
    response = await client.post("/sessions", json={"scenario_slug": SLUG})
    assert response.status_code == 201, response.text
    return response.json()


async def speak_turn(client, session_id: int, data: bytes = RECORDING):
    return await client.post(
        f"/sessions/{session_id}/turns",
        files={"file": ("turn.wav", data, "audio/wav")},
    )


@pytest.fixture
def conversing(seeded, client, account, provider, voice, recogniser, audio_root):
    """Everything a turn needs, stubbed. Returned as one object so the tests read."""
    return {
        "client": client,
        "account": account,
        "provider": provider,
        "voice": voice,
        "heard": recogniser,
        "audio_root": audio_root,
    }


# ── The happy path ──────────────────────────────────────────────────────────


async def test_a_turn_returns_the_transcript_the_reply_and_the_audio(
    conversing, client
):
    """FR-7, in one assertion block.

    Both turns come back, not only the reply. The client sent audio and has no
    transcript of its own — the recogniser is the only thing that knows what was said —
    so returning just the persona's answer would force an immediate second request to
    find out what the speaker was heard to have said.
    """
    session = await start(client)
    conversing["heard"].append("I have worked on payment systems for four years.")

    response = await speak_turn(client, session["id"])

    assert response.status_code == 201, response.text
    body = response.json()

    assert body["user_turn"]["role"] == "user"
    assert (
        body["user_turn"]["transcript"]
        == "I have worked on payment systems for four years."
    )
    assert body["user_turn"]["idx"] == 1
    assert body["user_turn"]["asr_model"] == "stub-whisper"

    assert body["reply_turn"]["role"] == "assistant"
    assert body["reply_turn"]["idx"] == 2
    assert body["reply_turn"]["transcript"]
    assert body["reply_turn"]["audio_url"]

    assert body["speech"]["status"] == "ok"
    assert body["speech"]["duration_ms"] > 0
    assert body["low_confidence"] is False


async def test_the_turn_reports_where_its_time_went(conversing, client):
    """R3: a latency regression is felt long before it is noticed, so the breakdown is
    on every turn rather than behind a debug flag. `make turn-latency` reads these same
    fields, so the measurement and the product cannot disagree."""
    session = await start(client)

    timing = (await speak_turn(client, session["id"])).json()["timing"]

    assert timing["total_ms"] >= 0
    assert timing["asr_ms"] == 12
    assert timing["prompt_tokens"] and timing["prompt_tokens"] > 0
    assert timing["reply_ms"] >= 0


async def test_the_word_timings_are_stored_on_the_turn(conversing, client, db_session):
    """`turns.words` is the raw material for every §7.1 fluency metric, and m9 is a long
    way from here. A stub that stored an empty array would leave the column untested
    until the milestone that reads it discovers it was never filled."""
    session = await start(client)
    conversing["heard"].append("One two three four five.")

    body = (await speak_turn(client, session["id"])).json()
    turn = await db_session.get(Turn, body["user_turn"]["id"])

    assert turn is not None and turn.words is not None
    assert len(turn.words) == 5
    assert set(turn.words[0]) == {"w", "start_ms", "end_ms", "logprob"}
    assert turn.asr_confidence == pytest.approx(0.93)


async def test_ten_turns_stay_in_order_and_in_character(conversing, client, db_session):
    """The scripted conversation the plan asks for.

    Two claims. The indices form one unbroken sequence, so nothing is lost or written
    twice; and the persona is in **every** request rather than only the first, which is
    R7 asserted against the real endpoint rather than against `build_messages` alone.
    """
    session = await start(client)

    for number in range(10):
        conversing["heard"].append(f"This is turn number {number}, and it went well.")
        response = await speak_turn(client, session["id"], RECORDING + bytes([number]))
        assert response.status_code == 201, response.text

    turns = list(
        (
            await db_session.scalars(
                select(Turn).where(Turn.session_id == session["id"]).order_by(Turn.idx)
            )
        ).all()
    )
    assert [turn.idx for turn in turns] == list(range(21))
    assert [turn.role for turn in turns[1:3]] == ["user", "assistant"]

    for messages in conversing["provider"].calls:
        assembled = "\n".join(message.content for message in messages)
        assert "Dana" in assembled or "hiring manager" in assembled


async def test_the_conversation_reaches_the_model(conversing, client):
    """What was said earlier has to come back. Without this the persona is answering
    each turn as though it were the first."""
    session = await start(client)
    conversing["heard"].append("My name is Ana and I work in Lisbon.")
    await speak_turn(client, session["id"])
    conversing["heard"].append("So, about that project.")
    await speak_turn(client, session["id"], RECORDING + b"x")

    last = "\n".join(m.content for m in conversing["provider"].calls[-1])
    assert "My name is Ana" in last
    assert "So, about that project." in last


# ── Transactions and the connection pool ────────────────────────────────────


async def test_no_database_connection_is_held_while_the_models_work(
    seeded, client, account, voice, recogniser, audio_root, db_engine
):
    """The property `database.get_db` warned about a milestone before there was anything
    to warn about.

    This endpoint calls three services and takes seconds. Holding a pooled connection
    across that is how a pool of ten is exhausted by four simultaneous users, and the
    symptom is not this endpoint being slow — it is every *other* endpoint blocking on
    checkout. The reads therefore end with a commit and the writes open a fresh
    transaction afterwards.

    Asserted by having the model itself look at the pool. If somebody moves one innocent
    query into the middle phase, this fails.
    """
    from main import app

    observed = []

    class WatchingProvider(StubProvider):
        async def stream(self, messages, max_tokens=None):
            observed.append(db_engine.pool.checkedout())
            async for event in super().stream(messages, max_tokens):
                yield event

    app.dependency_overrides[get_provider] = lambda: WatchingProvider()
    try:
        session = await start(client)
        assert (await speak_turn(client, session["id"])).status_code == 201
    finally:
        app.dependency_overrides.pop(get_provider, None)

    assert observed, "the provider was never called"
    assert observed == [0] * len(observed), (
        f"a database connection was held while the models were working: {observed}. "
        "Phase A must commit before the model calls — see the module docstring."
    )


async def test_a_turn_is_atomic_when_generation_fails(
    seeded, client, account, voice, recogniser, audio_root, db_session
):
    """Both halves or neither.

    Keeping the user's half would leave a conversation whose last turn is a question
    nobody answered, and a retry would then have to decide whether it is continuing that
    turn or starting a new one. The recording is not lost in any sense that matters: the
    browser still holds the blob, and the same bytes produce the same content-addressed
    asset when the turn is retried.
    """
    from main import app

    session = await start(client)
    app.dependency_overrides[get_provider] = lambda: BrokenProvider()

    response = await speak_turn(client, session["id"])

    assert response.status_code == 503
    assert "not responding" in response.json()["detail"]

    turns = await db_session.scalar(
        select(func.count(Turn.id)).where(Turn.session_id == session["id"])
    )
    assert turns == 1, "the user's turn was written even though the reply never was"

    assets = await db_session.scalar(
        select(func.count(AudioAsset.id)).where(AudioAsset.user_id == account["id"])
    )
    assert assets == 1, "the recording was stored for a turn that does not exist"


# ── Degradation ─────────────────────────────────────────────────────────────


async def test_a_silent_voice_still_answers_the_speaker(
    seeded, client, account, provider, recogniser, audio_root, monkeypatch
):
    """The reply is text the speaker can read. 502-ing it because a container is
    restarting would be the API deciding no answer is better than a silent one."""
    from services import conversation
    from services.tts_client import TtsUnavailable

    async def broken_speak(text, voice=None, length_scale=None, client=None):
        raise TtsUnavailable("ConnectError: refused")

    # The opening turn needs a working voice; only the second turn is silenced.
    session = await start_with_voice(client, monkeypatch, conversation)
    monkeypatch.setattr(conversation, "speak", broken_speak)

    body = (await speak_turn(client, session["id"])).json()

    assert body["reply_turn"]["transcript"]
    assert body["reply_turn"]["audio_url"] is None
    assert body["speech"]["status"] == "unavailable"
    assert "refused" in body["speech"]["detail"]


async def start_with_voice(client, monkeypatch, conversation_module):
    """Start a session with a working voice, so a test can break it afterwards."""
    from models.speech import Speech
    from tests.conftest import silent_wav

    async def ok_speak(text, voice=None, length_scale=None, client=None):
        return Speech(
            audio=silent_wav(120),
            voice="stub-voice",
            sample_rate=22050,
            duration_ms=120,
            sentences=1,
            length_scale=1.0,
            latency_ms=1,
        )

    monkeypatch.setattr(conversation_module, "speak", ok_speak)
    return await start(client)


async def test_a_recording_the_recogniser_cannot_read_is_a_422(
    conversing, client, monkeypatch
):
    """The one place in this turn where a 4xx is the honest answer: the rejected thing
    is the user's audio and re-recording genuinely helps. Contrast the model being
    unpulled, which is a 503 because there is nothing the speaker can do about it."""
    from routers import turns as turns_router
    from services.asr_client import AsrRejected

    session = await start(client)

    async def refuse(data, filename="recording", content_type=None):
        raise AsrRejected("not decodable as audio", 422)

    monkeypatch.setattr(turns_router, "transcribe", refuse)

    response = await speak_turn(client, session["id"])

    assert response.status_code == 422
    assert "not decodable" in response.json()["detail"]


async def test_a_recogniser_that_is_down_is_a_503(conversing, client, monkeypatch):
    from routers import turns as turns_router
    from services.asr_client import AsrUnavailable

    session = await start(client)

    async def down(data, filename="recording", content_type=None):
        raise AsrUnavailable("ConnectError: refused")

    monkeypatch.setattr(turns_router, "transcribe", down)

    response = await speak_turn(client, session["id"])

    assert response.status_code == 503
    assert "was not lost" in response.json()["detail"]


async def test_a_recogniser_answering_nonsense_is_a_502(
    conversing, client, monkeypatch
):
    """Version skew between two containers, which must not be reported as either of the
    other two. It is the failure a broad `except Exception` hides for months."""
    from routers import turns as turns_router
    from services.asr_client import AsrProtocolError

    session = await start(client)

    async def skewed(data, filename="recording", content_type=None):
        raise AsrProtocolError("unexpected response shape")

    monkeypatch.setattr(turns_router, "transcribe", skewed)

    assert (await speak_turn(client, session["id"])).status_code == 502


async def test_a_turn_the_recogniser_was_unsure_of_is_flagged_not_hidden(
    seeded, client, account, provider, voice, audio_root, monkeypatch
):
    """PRD §7.5 and R2. The turn is still stored and still answered — the speaker said
    something and deserves a reply — but it is marked so m9 keeps it out of accuracy
    trends. An ASR error scored as a grammar error is a correction nobody can act on."""
    from models.audio import DecoderSettings, SourceMedia, Transcription, Word
    from routers import turns as turns_router

    session = await start(client)

    async def mumbled(data, filename="recording", content_type=None):
        return Transcription(
            text="something something",
            words=[Word(w="something", start_ms=0, end_ms=300, logprob=-2.5)],
            confidence=0.21,
            timestamp_fixups=0,
            language="en",
            model="stub-whisper",
            decoder=DecoderSettings(beam_size=5, vad_filter=True, compute_type="int8"),
            source=SourceMedia(
                format="wav",
                codec="pcm_s16le",
                sample_rate=16000,
                channels=1,
                duration_ms=800,
            ),
            latency_ms=10,
        )

    monkeypatch.setattr(turns_router, "transcribe", mumbled)

    body = (await speak_turn(client, session["id"])).json()

    assert body["low_confidence"] is True
    assert body["reply_turn"]["transcript"], "a low-confidence turn still gets a reply"


# ── Retention (FR-26) ───────────────────────────────────────────────────────


async def test_retention_off_keeps_the_transcript_and_drops_the_waveform(
    conversing, client, db_session, audio_root
):
    """FR-26, and m6 is the first milestone where the setting means anything: it has
    been changeable since m3 and nothing stored a waveform until now.

    The setting drops the audio and keeps everything derived from it — transcript, word
    timings, confidence — which is exactly what the requirement asks for.
    """
    assert (
        await client.patch("/auth/me", json={"retain_audio": False})
    ).status_code == 200
    session = await start(client)
    before = {path for path in audio_root.rglob("*") if path.is_file()}

    body = (await speak_turn(client, session["id"])).json()

    assert body["user_turn"]["audio_asset_id"] is None
    assert body["user_turn"]["audio_url"] is None
    assert body["user_turn"]["transcript"]

    turn = await db_session.get(Turn, body["user_turn"]["id"])
    assert turn is not None and turn.words and turn.asr_confidence is not None

    # The persona's own audio is still stored: it is synthesised speech, not the user's
    # voice, and it is what replaying a conversation needs.
    assert body["reply_turn"]["audio_asset_id"] is not None

    # Named rather than counted. The reply's own audio deduplicates against the opening
    # turn's when a stub voice returns identical bytes, so "one new file" is not the
    # property — "not *this* file" is.
    from services.audio import sha256_of

    written = {path.name for path in audio_root.rglob("*") if path.is_file()}
    assert sha256_of(RECORDING) not in written, "the speaker's recording was stored"
    assert before is not None


# ── Sequencing and state ────────────────────────────────────────────────────


async def test_a_completed_session_takes_no_more_turns(conversing, client):
    session = await start(client)
    await client.post(f"/sessions/{session['id']}/end")

    response = await speak_turn(client, session["id"])

    assert response.status_code == 409
    assert "completed" in response.json()["detail"]


async def test_another_accounts_session_cannot_be_spoken_into(
    conversing, client, other_client
):
    session = await start(client)
    await register_account(other_client, email=unique_email("intruder"))

    response = await speak_turn(other_client, session["id"])

    assert response.status_code == 404


async def test_a_read_aloud_session_is_not_a_conversation(
    conversing, client, db_session, account
):
    """A session with no scenario has no persona to reply as. m8's `POST /attempts` is
    where those go, and saying so is a better error than a generic 404."""
    user = await db_session.scalar(select(User).where(User.email == account["email"]))
    session = PracticeSession(user_id=user.id, mode="read_aloud", status="active")
    db_session.add(session)
    await db_session.commit()

    response = await speak_turn(client, session.id)

    assert response.status_code == 409
    assert "no scenario" in response.json()["detail"]


# ── Summarisation, end to end (FR-8) ────────────────────────────────────────


async def test_a_long_conversation_grows_a_digest_and_uses_it(
    seeded,
    client,
    account,
    provider,
    voice,
    recogniser,
    audio_root,
    db_session,
    monkeypatch,
):
    """The FR-8 loop closed against the real endpoint: turns fall out of the window, a
    digest is written, and the digest comes back in the next prompt.

    The budget is squeezed rather than the conversation being made enormous — a hundred
    real turns would be a slow test that proved the same thing.
    """
    monkeypatch.setattr("services.conversation.LLM_MAX_INPUT_TOKENS", 700)

    session = await start(client)
    for number in range(8):
        recogniser.append(
            f"In {2015 + number} I worked at company number {number} on their billing "
            "platform, which was a large and slow system."
        )
        assert (
            await speak_turn(client, session["id"], RECORDING + bytes([number]))
        ).status_code == 201

    stored = await db_session.get(PracticeSession, session["id"])
    await db_session.refresh(stored)

    assert (
        stored.context_digest
    ), "the conversation outgrew the window and nothing was summarised"
    assert stored.digest_through_idx is not None

    recogniser.append("Anyway, that is the background.")
    await speak_turn(client, session["id"], RECORDING + b"final")

    last = "\n".join(m.content for m in provider.calls[-1])
    assert stored.context_digest[:40] in last, "the digest was written and never read"
