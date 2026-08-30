"""The TTS client's error taxonomy, and what it refuses to guess at.

Pure: no container, no database, no network. The cases that matter most here are the
ones a working service cannot produce on demand — a timeout, the 503 it answers while
its voice loads, a proxy returning an HTML error page with a 200 — so they are driven
through `httpx.MockTransport` rather than against a live process. The suite that does
want a real voice is `test_tts_live.py`, which skips unless one answers.

The distinction under test is the same one `test_asr_client.py` makes: *the request is
bad* against *the system is bad*. Getting it wrong in this direction has a specific
consequence — a persona reply that failed to synthesise because the container was still
loading would be retried forever if it were classified as a rejection, and dropped
forever if a rejection were classified as unavailability.
"""

import base64
import io
import json
import wave

import httpx
import pytest

from models.speech import SpeechChunk
from services.tts_client import (
    TtsProtocolError,
    TtsRejected,
    TtsUnavailable,
    speak,
    speak_stream,
)


def wav_bytes(seconds: float = 0.1, sample_rate: int = 22050) -> bytes:
    """A real, minimal WAV. Written rather than fixtured, so it cannot go stale."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(b"\x00\x00" * int(sample_rate * seconds))
    return buffer.getvalue()


# The headers infra/tts/app.py actually sets. Written out here on purpose: if the two
# drift, this file is the record of what the API was promised.
GOOD_HEADERS = {
    "x-voice": "en_US-lessac-medium",
    "x-sample-rate": "22050",
    "x-duration-ms": "2717",
    "x-sentences": "2",
    "x-length-scale": "1.0",
    "x-latency-ms": "66",
}


def client_returning(
    *, content=None, status_code=200, headers=None, json=None, raises=None
):
    def handler(request: httpx.Request) -> httpx.Response:
        if raises is not None:
            raise raises
        if json is not None:
            return httpx.Response(status_code, json=json)
        return httpx.Response(status_code, content=content, headers=headers)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def ndjson_client(lines, status_code=200, error_body=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if error_body is not None:
            return httpx.Response(status_code, json=error_body)
        body = "".join(json.dumps(line) + "\n" for line in lines).encode()
        return httpx.Response(status_code, content=body)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def chunk_line(index=0, samples=1000, latency_ms=90):
    return {
        "index": index,
        "audio_b64": base64.b64encode(b"\x01\x00" * samples).decode(),
        "samples": samples,
        "duration_ms": round(samples / 22050 * 1000),
        "sample_rate": 22050,
        "sample_width": 2,
        "channels": 1,
        "latency_ms": latency_ms,
    }


# ── The happy path ──────────────────────────────────────────────────────────


async def test_a_wav_comes_back_with_its_metadata_typed():
    async with client_returning(content=wav_bytes(), headers=GOOD_HEADERS) as http:
        speech = await speak("Sure, I can help with that.", client=http)

    assert speech.audio.startswith(b"RIFF")
    assert speech.sample_rate == 22050
    assert speech.duration_ms == 2717
    assert speech.sentences == 2
    assert speech.voice == "en_US-lessac-medium"


async def test_the_text_is_sent_as_json_under_the_field_the_service_reads():
    """`text`, and `voice` only when one was asked for.

    Always sending `voice` would mean every request asserts which voice is loaded, so
    changing PIPER_VOICE on the container would start rejecting every synthesis with a
    400 that reads like a client bug.
    """
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, content=wav_bytes(), headers=GOOD_HEADERS)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        await speak("hello", client=http)
        assert seen["body"] == {"text": "hello"}

        await speak("hello", voice="en_GB-alba-medium", length_scale=0.9, client=http)
        assert seen["body"] == {
            "text": "hello",
            "voice": "en_GB-alba-medium",
            "length_scale": 0.9,
        }


# ── The request is bad ──────────────────────────────────────────────────────


@pytest.mark.parametrize("status_code", [400, 413, 422])
async def test_a_4xx_is_a_rejection_that_carries_its_status_and_reason(status_code):
    async with client_returning(
        status_code=status_code,
        json={"detail": "this service is running 'en_US-lessac-medium', not 'x'"},
    ) as http:
        with pytest.raises(TtsRejected) as caught:
            await speak("hello", voice="x", client=http)

    assert caught.value.status_code == status_code
    assert "en_US-lessac-medium" in caught.value.detail


# ── The system is bad ───────────────────────────────────────────────────────


async def test_nobody_answering_is_unavailable_not_a_rejection():
    async with client_returning(raises=httpx.ConnectError("no route")) as http:
        with pytest.raises(TtsUnavailable) as caught:
            await speak("hello", client=http)

    assert "ConnectError" in str(caught.value)


async def test_a_timeout_is_unavailable():
    async with client_returning(raises=httpx.ReadTimeout("timed out")) as http:
        with pytest.raises(TtsUnavailable):
            await speak("hello", client=http)


@pytest.mark.parametrize("status_code", [500, 502, 503])
async def test_a_5xx_is_unavailable_because_the_text_was_never_the_problem(status_code):
    """503 is the one that matters: it is what the service answers while loading.

    Classified as a rejection it would make a reply un-synthesisable for the life of the
    session, when in fact the identical text works a second later.
    """
    async with client_returning(
        status_code=status_code, json={"detail": "en_US-lessac-medium is still loading"}
    ) as http:
        with pytest.raises(TtsUnavailable):
            await speak("hello", client=http)


# ── The two services have drifted apart ─────────────────────────────────────


async def test_a_200_that_is_not_a_wav_is_a_protocol_error():
    """A proxy answering 200 with an HTML error page is a real failure mode.

    Passed through, it becomes an audio element that silently plays nothing, which is
    indistinguishable from a muted browser.
    """
    async with client_returning(
        content=b"<html>502 Bad Gateway</html>", headers=GOOD_HEADERS
    ) as http:
        with pytest.raises(TtsProtocolError):
            await speak("hello", client=http)


@pytest.mark.parametrize("missing", ["x-duration-ms", "x-sample-rate", "x-voice"])
async def test_a_missing_metadata_header_is_a_protocol_error_not_a_default(missing):
    """Every one of these ends up on an audio_assets row.

    A defaulted zero there is a stored fact nothing downstream can tell apart from a
    real measurement, which is the whole reason the service reports them at all.
    """
    headers = {k: v for k, v in GOOD_HEADERS.items() if k != missing}
    async with client_returning(content=wav_bytes(), headers=headers) as http:
        with pytest.raises(TtsProtocolError):
            await speak("hello", client=http)


async def test_a_zero_duration_is_a_protocol_error():
    """`duration_ms` is `gt=0`: a WAV of no length is not speech.

    The service answers 422 for text that produces no audio, so a 200 claiming zero
    milliseconds means the two sides disagree about what an empty synthesis is.
    """
    async with client_returning(
        content=wav_bytes(), headers={**GOOD_HEADERS, "x-duration-ms": "0"}
    ) as http:
        with pytest.raises(TtsProtocolError):
            await speak("hello", client=http)


async def test_an_unparseable_header_is_a_protocol_error():
    async with client_returning(
        content=wav_bytes(), headers={**GOOD_HEADERS, "x-sample-rate": "22050 Hz"}
    ) as http:
        with pytest.raises(TtsProtocolError):
            await speak("hello", client=http)


# ── Streaming ───────────────────────────────────────────────────────────────


async def test_the_stream_yields_one_typed_chunk_per_line_in_order():
    lines = [chunk_line(0, latency_ms=90), chunk_line(1, latency_ms=180)]
    async with ndjson_client(lines) as http:
        chunks = [chunk async for chunk in speak_stream("two sentences.", client=http)]

    assert [chunk.index for chunk in chunks] == [0, 1]
    assert all(isinstance(chunk, SpeechChunk) for chunk in chunks)
    # Decoded, not left as base64 — the caller concatenates these into one asset.
    assert chunks[0].pcm == b"\x01\x00" * 1000
    assert chunks[0].latency_ms == 90


async def test_concatenated_chunks_reproduce_the_whole_synthesis():
    """The contract that makes the streaming endpoint usable for storage as well.

    m6 has to store one asset per assistant turn regardless of how the audio arrived,
    so `b"".join(chunk.pcm)` plus a WAV header must equal what /synthesize would have
    returned. Asserted on sample counts because that is the part a chunking bug breaks.
    """
    lines = [chunk_line(0, samples=500), chunk_line(1, samples=700)]
    async with ndjson_client(lines) as http:
        chunks = [chunk async for chunk in speak_stream("text", client=http)]

    pcm = b"".join(chunk.pcm for chunk in chunks)
    assert len(pcm) == (500 + 700) * chunks[0].sample_width
    assert sum(chunk.samples for chunk in chunks) == 1200


async def test_an_error_object_mid_stream_is_unavailable_not_a_truncated_success():
    """The status line is long gone by the time synthesis fails.

    A caller that ignored this would store a two-sentence reply as if it were the whole
    thing, and nothing later could tell that audio from a complete one.
    """
    lines = [chunk_line(0), {"error": "RuntimeError: session died"}]
    async with ndjson_client(lines) as http:
        with pytest.raises(TtsUnavailable):
            async for _ in speak_stream("text", client=http):
                pass


async def test_a_4xx_on_the_stream_is_still_a_rejection():
    async with ndjson_client(
        [], status_code=400, error_body={"detail": "no such voice"}
    ) as http:
        with pytest.raises(TtsRejected) as caught:
            async for _ in speak_stream("text", voice="x", client=http):
                pass

    assert caught.value.status_code == 400


async def test_a_line_that_is_not_json_is_a_protocol_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>nope</html>\n")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(TtsProtocolError):
            async for _ in speak_stream("text", client=http):
                pass


async def test_a_chunk_missing_a_field_is_a_protocol_error():
    bad = {k: v for k, v in chunk_line().items() if k != "sample_rate"}
    async with ndjson_client([bad]) as http:
        with pytest.raises(TtsProtocolError):
            async for _ in speak_stream("text", client=http):
                pass
