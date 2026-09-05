"""The measurement suite for synthesis: a real voice, real audio, a number at the end.

**Skipped unless a real tts service is reachable**, for the same reason as
`test_asr_golden.py`: `make test` and CI point `TTS_URL` at a host that cannot resolve,
because the health tests need an absent model layer. To run these:

    docker compose up -d tts
    TTS_URL=http://localhost:8102 python -m pytest tests/test_tts_live.py -v

or `make tts-latency`, which does both.

What is asserted against what is merely reported follows the same split as the other
live suites:

- **Asserted:** the bytes are a WAV that a `wave` reader can open, its declared duration
  matches the audio actually in it, its length is plausible for the number of words sent,
  an unknown voice is refused, and the streamed chunks concatenate to the same audio the
  whole-reply endpoint returns.
- **Reported, not asserted:** latency. It is measured on whatever machine is running,
  and a laptop with a build going would fail a millisecond threshold while the code is
  perfect. Turning a measurement into a gate needs a recorded baseline on known
  hardware, which is the eval harness's job rather than this file's.

There is no golden set here and that is not an oversight. WER measures a recogniser
against a reference transcript; the equivalent for a synthesiser is a listening test,
and a committed WAV to diff against would only assert that onnxruntime is deterministic
— which it is, and which tells us nothing about whether the voice is any good. The
judgement of voice quality is a human one, made once, and recorded in decision 0002.
"""

import io
import json
import wave

import httpx
import pytest

from config import TTS_URL
from services.tts_client import TtsRejected, speak, speak_stream

# ~80 output tokens, which is what a persona reply is budgeted at. Four sentences, so
# the streaming endpoint has something to stream.
TYPICAL_REPLY = (
    "I understand your concern, and I think it is worth raising with the team. "
    "The delivery window we agreed on was always going to be tight given the "
    "holiday period. What I would suggest is that we split the order into two "
    "shipments. That way the urgent items arrive on time and the rest follows "
    "the week after."
)

SHORT_REPLY = "Sure, I can help with that. What time works for you?"

# The synthesis budget. Reported against, never asserted on — see the module docstring.
BUDGET_MS = 400


def _tts_is_reachable() -> bool:
    try:
        response = httpx.get(f"{TTS_URL}/health", timeout=3.0)
    except httpx.RequestError:
        return False
    return response.is_success and response.json().get("voice_loaded") is True


needs_tts = pytest.mark.skipif(
    not _tts_is_reachable(),
    reason=(
        f"no loaded tts service at {TTS_URL}. "
        "Run `docker compose up -d tts` and set TTS_URL=http://localhost:8102."
    ),
)


def read_wav(audio: bytes) -> tuple[int, int, int, int]:
    """frames, sample rate, channels, sample width — from the file, not from a header
    the service sent. The two are compared, which is the point."""
    with wave.open(io.BytesIO(audio), "rb") as handle:
        return (
            handle.getnframes(),
            handle.getframerate(),
            handle.getnchannels(),
            handle.getsampwidth(),
        )


# ── The audio is audio ──────────────────────────────────────────────────────


@needs_tts
async def test_a_reply_comes_back_as_a_wav_that_a_player_can_open():
    speech = await speak(SHORT_REPLY)

    frames, rate, channels, width = read_wav(speech.audio)
    assert channels == 1, "mono, as every consumer here assumes"
    assert width == 2, "16-bit PCM"
    assert rate == speech.sample_rate, "the header and the reported rate agree"
    assert frames > 0


@needs_tts
async def test_the_declared_duration_matches_the_audio_actually_in_the_file():
    """The service reports `duration_ms`; the API stores it on an audio_assets row.

    If the two could disagree, every fluency and pacing number derived from a stored
    asset would be derived from a number nothing measured.
    """
    speech = await speak(TYPICAL_REPLY)

    frames, rate, _, _ = read_wav(speech.audio)
    measured_ms = round(frames / rate * 1000)
    assert abs(measured_ms - speech.duration_ms) <= 1


@needs_tts
async def test_the_audio_is_a_plausible_length_for_the_words_sent():
    """A crude bound, and crude is what it should be.

    English read aloud sits around 2.5-3.5 words per second, so 61 words is roughly
    17-24 s. The failure this actually catches is not a slightly-off speaking rate: it
    is a voice that emitted one sentence and stopped, or a length_scale set by accident.
    """
    speech = await speak(TYPICAL_REPLY)

    words = len(TYPICAL_REPLY.split())
    seconds = speech.duration_ms / 1000
    assert 0.15 * words < seconds < 0.6 * words, f"{words} words in {seconds:.1f}s"
    assert speech.sentences == 4


@needs_tts
async def test_a_slower_length_scale_produces_longer_audio():
    """The setting that exists so a beginner band can be given slower speech.

    Asserted as a direction rather than a ratio: the scale is applied per phoneme, and
    tying a test to the exact multiple would be asserting a property of the vocoder.
    """
    normal = await speak(SHORT_REPLY)
    slow = await speak(SHORT_REPLY, length_scale=1.5)

    assert slow.duration_ms > normal.duration_ms * 1.2


# ── What it refuses ─────────────────────────────────────────────────────────


@needs_tts
async def test_an_unknown_voice_is_refused_rather_than_silently_substituted():
    """A reply that comes back in the wrong voice is worse than an error.

    The persona is the product; a synthesis that quietly fell back to whatever was
    loaded would be a persona change nobody asked for and nothing recorded.
    """
    with pytest.raises(TtsRejected) as caught:
        await speak(SHORT_REPLY, voice="xx_XX-nonexistent-medium")

    assert caught.value.status_code == 400


@needs_tts
async def test_text_that_produces_no_speech_is_refused_rather_than_returning_silence():
    """An em dash phonemises to nothing.

    A WAV of zero frames would be something the browser can play and a listener cannot
    hear, which is indistinguishable from a broken audio element.
    """
    with pytest.raises(TtsRejected) as caught:
        await speak("—")

    assert caught.value.status_code == 422


# ── Streaming, and the reason it exists ─────────────────────────────────────


@needs_tts
async def test_synthesis_is_not_deterministic_and_that_is_a_property_not_a_bug():
    """The same text twice is not the same audio, and callers have to know it.

    Piper is VITS, whose duration predictor samples from a learned distribution — that
    stochasticity is what stops synthetic prosody sounding metronomic, and it is on by
    default because the voice was trained with it. The consequences are concrete:

    - A synthesised reply must be **stored**, never re-derived. `audio_assets` is keyed
      by sha256, and two syntheses of one sentence hash differently, so text is not a
      cache key here the way it would be for a deterministic model.
    - There is no golden WAV to diff against. A regression test for a synthesiser has to
      assert properties — length, format, sentence count — never bytes.
    - `duration_ms` genuinely varies for the same reply, so a stored value describes the
      audio that exists, not the audio the text implies.

    Asserted as a spread rather than an inequality: two runs could coincide, five with
    identical sample counts would mean the noise was switched off somewhere.
    """
    durations = [(await speak(SHORT_REPLY)).duration_ms for _ in range(5)]

    assert len(set(durations)) > 1, f"identical across five runs: {durations}"
    # Loose bound in the other direction: this is prosodic variation, not a broken
    # length scale. Anything beyond a few percent would be a different failure.
    assert max(durations) / min(durations) < 1.5, durations


@needs_tts
async def test_the_stream_carries_the_same_reply_as_the_whole_endpoint():
    """The contract the turn writer depends on to store one asset however it arrived.

    Compared by structure and approximate length, NOT byte-for-byte — see the test
    above: two syntheses of one text differ by a few percent, so a sample-exact
    assertion here would be asserting that the model is something it is not. Sentence
    *splitting* is deterministic, which is why the chunk count can be asserted exactly,
    and a dropped or duplicated sentence — the failure this actually guards against —
    moves that count and moves the duration by a quarter.
    """
    whole = await speak(TYPICAL_REPLY)
    chunks = [chunk async for chunk in speak_stream(TYPICAL_REPLY)]

    streamed = b"".join(chunk.pcm for chunk in chunks)
    frames, _, _, width = read_wav(whole.audio)

    assert [chunk.index for chunk in chunks] == list(range(len(chunks)))
    assert len(chunks) == whole.sentences

    # The stream is internally exact: whatever it declared, it delivered.
    assert len(streamed) == sum(chunk.samples for chunk in chunks) * width
    assert sum(chunk.duration_ms for chunk in chunks) == pytest.approx(
        round(len(streamed) / width / chunks[0].sample_rate * 1000), abs=len(chunks)
    )

    # And it is the same reply as the other endpoint produced, to within the model's
    # own run-to-run variation.
    assert len(streamed) / width == pytest.approx(frames, rel=0.1)


@needs_tts
async def test_the_first_chunk_arrives_well_before_the_whole_reply(capsys):
    """The measurement this endpoint exists to make, reported rather than asserted.

    The assertion is only the ordering — a first sentence cannot take longer than all
    four — because the millisecond numbers belong to whichever machine is running. The
    controlled figures are in docs/decisions/0002.
    """
    latencies = {}
    for name, text in (("short", SHORT_REPLY), ("typical", TYPICAL_REPLY)):
        whole = await speak(text)
        chunks = [chunk async for chunk in speak_stream(text)]
        latencies[name] = {
            "words": len(text.split()),
            "sentences": whole.sentences,
            "audio_ms": whole.duration_ms,
            "whole_ms": whole.latency_ms,
            "first_chunk_ms": chunks[0].latency_ms,
            "last_chunk_ms": chunks[-1].latency_ms,
        }
        assert chunks[0].latency_ms <= chunks[-1].latency_ms

    with capsys.disabled():
        print(f"\n  budget: {BUDGET_MS} ms. Reported, not asserted.")
        print(f"  {json.dumps(latencies, indent=2)}")
