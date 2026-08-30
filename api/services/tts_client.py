"""Talking to the tts service.

The same three-outcome taxonomy as `asr_client`, for the same reason: *the request is
bad*, *the system is bad*, and *the two services have drifted apart* need different
handling, and a single `except Exception` collapses all three into a retry loop that can
never succeed.

- `TtsUnavailable` — nobody answered, or the service answered 5xx. This includes the
  503 it returns while its voice is loading, which is the case that must not be a
  rejection: the same text synthesises perfectly a second later.
- `TtsRejected` — 4xx. The text is empty, too long, phonemises to nothing, or names a
  voice this service is not running. Retrying will fail identically.
- `TtsProtocolError` — a 200 whose body is not a WAV, or whose headers do not carry the
  metadata the API records on the `audio_assets` row.

**Two functions, because the milestone that built the service measured why.** `speak`
returns the finished WAV and is what m6 stores. `speak_stream` yields one sentence at a
time, and its first chunk arrives in about 90 ms against roughly 380 ms for the whole
reply — PRD §9.1's first prescribed fallback, and the reason the 400 ms budget is
reachable for a long reply at all. The measurements are in
`docs/decisions/0002-tts-model-choice.md`.
"""

from __future__ import annotations

import base64
import json
from typing import Any, AsyncIterator

import httpx
from pydantic import ValidationError

from config import TTS_TIMEOUT_S, TTS_URL
from models.speech import Speech, SpeechChunk

# Every RIFF/WAVE file starts with these four bytes, then a size, then `WAVE`. Checked
# because a reverse proxy returning an HTML error page with a 200 is a real thing, and
# handing that to the browser as audio/wav produces a player that silently does nothing.
_RIFF = b"RIFF"


class TtsError(Exception):
    """Base for every failure of the synthesis call."""


class TtsUnavailable(TtsError):
    """The service could not be reached, or failed on its own account."""


class TtsRejected(TtsError):
    """The service refused the text. Retrying with the same text will not help."""

    def __init__(self, detail: str, status_code: int) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


class TtsProtocolError(TtsError):
    """A 200 that is not the agreed shape. A version skew, not a bad request."""


def _detail_of(response: httpx.Response) -> str:
    """FastAPI's `{"detail": ...}`, or the raw text when it is not that."""
    try:
        body = response.json()
    except ValueError:
        return response.text[:200]
    if isinstance(body, dict) and "detail" in body:
        return str(body["detail"])
    return response.text[:200]


def _raise_for_status(response: httpx.Response) -> None:
    if response.status_code >= 500:
        raise TtsUnavailable(f"HTTP {response.status_code}: {_detail_of(response)}")
    if response.status_code >= 400:
        raise TtsRejected(_detail_of(response), response.status_code)


def _payload(
    text: str, voice: str | None, length_scale: float | None
) -> dict[str, Any]:
    body: dict[str, Any] = {"text": text}
    if voice is not None:
        body["voice"] = voice
    if length_scale is not None:
        body["length_scale"] = length_scale
    return body


async def speak(
    text: str,
    voice: str | None = None,
    length_scale: float | None = None,
    client: httpx.AsyncClient | None = None,
) -> Speech:
    """Text in, one complete WAV out.

    `client` is injectable so the tests can drive this against `httpx.MockTransport`.
    That is not only convenience: the cases worth testing here are a timeout, a 503 and
    a 200 carrying an HTML error page, and none of those can be produced on demand by a
    service that works.
    """
    owned = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=TTS_TIMEOUT_S)

    try:
        try:
            response = await client.post(
                f"{TTS_URL}/synthesize", json=_payload(text, voice, length_scale)
            )
        except httpx.RequestError as exc:
            raise TtsUnavailable(f"{type(exc).__name__}: {exc}") from exc

        _raise_for_status(response)

        audio = response.content
        if not audio.startswith(_RIFF):
            raise TtsProtocolError(
                f"200 whose body is not a WAV: starts {audio[:16]!r}"
            )

        try:
            return Speech(
                audio=audio,
                voice=response.headers["x-voice"],
                sample_rate=int(response.headers["x-sample-rate"]),
                duration_ms=int(response.headers["x-duration-ms"]),
                sentences=int(response.headers["x-sentences"]),
                length_scale=float(response.headers["x-length-scale"]),
                latency_ms=int(response.headers["x-latency-ms"]),
            )
        except (KeyError, ValueError, ValidationError) as exc:
            # A missing header is a protocol error, never a default. `duration_ms` ends
            # up on an audio_assets row, and a zero there would be a stored fact that
            # nothing downstream can tell from a real measurement.
            raise TtsProtocolError(f"unexpected response headers: {exc!r}") from exc
    finally:
        if owned:
            await client.aclose()


async def speak_stream(
    text: str,
    voice: str | None = None,
    length_scale: float | None = None,
    client: httpx.AsyncClient | None = None,
) -> AsyncIterator[SpeechChunk]:
    """One `SpeechChunk` per sentence, in order, as the service produces them.

    A failure after the first line cannot change the status code, so the service reports
    it as an `{"error": ...}` object in the stream. That is raised here as
    `TtsUnavailable` — the transport was fine and the text was fine, the synthesis died
    part way — so that a caller which stops at the first exception cannot mistake a
    truncated reply for a complete one.
    """
    owned = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=TTS_TIMEOUT_S)

    try:
        try:
            async with client.stream(
                "POST",
                f"{TTS_URL}/synthesize/stream",
                json=_payload(text, voice, length_scale),
            ) as response:
                if response.status_code >= 400:
                    # The body has not been read yet on a streaming response, and
                    # `_detail_of` needs it.
                    await response.aread()
                    _raise_for_status(response)

                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                    except ValueError as exc:
                        raise TtsProtocolError(
                            f"line is not JSON: {line[:120]!r}"
                        ) from exc

                    if "error" in record:
                        raise TtsUnavailable(
                            f"synthesis failed mid-stream: {record['error']}"
                        )

                    try:
                        yield SpeechChunk(
                            index=record["index"],
                            pcm=base64.b64decode(record["audio_b64"]),
                            samples=record["samples"],
                            duration_ms=record["duration_ms"],
                            sample_rate=record["sample_rate"],
                            sample_width=record["sample_width"],
                            channels=record["channels"],
                            latency_ms=record["latency_ms"],
                        )
                    except (KeyError, ValueError, ValidationError) as exc:
                        raise TtsProtocolError(
                            f"unexpected chunk shape: {exc!r}"
                        ) from exc
        except httpx.RequestError as exc:
            raise TtsUnavailable(f"{type(exc).__name__}: {exc}") from exc
    finally:
        if owned:
            await client.aclose()
