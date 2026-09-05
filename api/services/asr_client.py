"""Talking to the asr service.

The API holds no weights and no media library; it holds an address and this client. Everything about transcription that is not a model lives here: the timeout,
the error taxonomy, and the parse of the response into the same `Word` shape the
database column stores.

**The error taxonomy is the point of the module.** Three outcomes reach the caller and
they need different handling:

- `AsrUnavailable` — nobody answered, or the service answered 5xx. The recording is
  fine; the system is not. The caller should keep the audio and let the user retry.
- `AsrRejected` — the service answered 4xx: the bytes are not decodable audio, or they
  are too large. Retrying will fail identically. This becomes a 422 to the browser.
- `AsrProtocolError` — something answered 200 with a body this code cannot parse. That
  is a version skew between the two services, and it must not be mistaken for either of
  the above: it is the failure that a broad `except Exception` would hide for months.

Collapsing the first two is the tempting simplification and the wrong one. It produces a
retry loop that can never succeed against audio that will never decode.
"""

import httpx
from pydantic import ValidationError

from config import ASR_TIMEOUT_S, ASR_URL
from models.audio import Transcription


class AsrError(Exception):
    """Base for every failure of the transcription call."""


class AsrUnavailable(AsrError):
    """The service could not be reached, or failed on its own account."""


class AsrRejected(AsrError):
    """The service refused the audio. Retrying with the same bytes will not help."""

    def __init__(self, detail: str, status_code: int) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


class AsrProtocolError(AsrError):
    """A 200 whose body is not the agreed shape. A version skew, not a bad recording."""


def _detail_of(response: httpx.Response) -> str:
    """FastAPI's `{"detail": ...}`, or the raw text when it is not that."""
    try:
        body = response.json()
    except ValueError:
        return response.text[:200]
    if isinstance(body, dict) and "detail" in body:
        return str(body["detail"])
    return response.text[:200]


async def transcribe(
    data: bytes,
    filename: str = "recording",
    content_type: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> Transcription:
    """Send bytes, get a transcript with word timings back.

    `client` is injectable so the tests can drive this against `httpx.MockTransport`
    rather than a running container. That is not only convenience: the interesting cases
    here are a timeout, a 503 and a malformed 200, and two of those are difficult to
    produce on demand from a service that works.
    """
    owned = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=ASR_TIMEOUT_S)

    try:
        try:
            response = await client.post(
                f"{ASR_URL}/transcribe",
                files={
                    "file": (filename, data, content_type or "application/octet-stream")
                },
            )
        except httpx.RequestError as exc:
            # Connection refused, DNS failure, timeout — from here they are the same
            # observation: the container is not answering. The type is preserved in the
            # message because that is the part an operator needs.
            raise AsrUnavailable(f"{type(exc).__name__}: {exc}") from exc

        if response.status_code >= 500:
            raise AsrUnavailable(f"HTTP {response.status_code}: {_detail_of(response)}")
        if response.status_code >= 400:
            raise AsrRejected(_detail_of(response), response.status_code)

        try:
            return Transcription.model_validate(response.json())
        except (ValueError, ValidationError) as exc:
            raise AsrProtocolError(f"unexpected response shape: {exc}") from exc
    finally:
        if owned:
            await client.aclose()
