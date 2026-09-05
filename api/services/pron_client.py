"""Talking to the pron service.

The same shape as `asr_client`, for the same reason: the API holds no weights and no
media library (invariant I5), it holds an address and a client, and the error taxonomy is
the part worth writing by hand.

Four outcomes reach the caller and they are genuinely different facts:

- `PronUnavailable` — nobody answered, or the service answered 5xx. **This is the normal
  state**, not an exception: `pron` is profiled, so on a laptop that never ran
  `make pron-up` it is simply absent. PRD R6 says an attempt must still return its
  transcript and WER in that case, with phoneme scores reported as `unavailable`. This is
  the only client in the system whose most common failure is expected.
- `PronRejected` — a 4xx. The audio could not be decoded, or the recording is far shorter
  than the passage, or the passage text desyncs from G2P. Retrying the same bytes against
  the same text will fail identically, so this is stored on the attempt as a *reason*
  rather than retried.
- `PronProtocolError` — a 200 whose body this code cannot parse. A version skew between
  two containers, and the failure a broad `except Exception` would hide for months.
- `PronMisconfigured` — a 500 naming a phone-map gap. It is separated from
  `PronUnavailable` because it is not transient and no amount of retrying fixes it: the
  image needs a new phone map. It is the one failure here that is *this project's* bug,
  and it should read like one in the log.
"""

import httpx
from pydantic import ValidationError

from config import PRON_TIMEOUT_S, PRON_URL
from models.attempt import PronScoring


class PronError(Exception):
    """Base for every failure of the scoring call."""


class PronUnavailable(PronError):
    """Not reachable, or failed on its own account. Expected when the profile is down."""


class PronRejected(PronError):
    """The service refused this audio or this text. The same request will fail again."""

    def __init__(self, detail: str, status_code: int) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


class PronProtocolError(PronError):
    """A 200 whose body is not the agreed shape. A version skew, not a bad recording."""


class PronMisconfigured(PronError):
    """The service reported a phone-map gap. Not transient; the image is wrong."""


def _detail_of(response: httpx.Response) -> str:
    """FastAPI's `{"detail": ...}`, or the raw text when it is not that."""
    try:
        body = response.json()
    except ValueError:
        return response.text[:200]
    if isinstance(body, dict) and "detail" in body:
        return str(body["detail"])
    return response.text[:200]


async def score(
    data: bytes,
    text: str,
    filename: str = "recording",
    content_type: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> PronScoring:
    """Send a recording and the text it was meant to be; get per-phone GOP back.

    `client` is injectable so the tests can drive this against `httpx.MockTransport`
    rather than a 2 GB container. That is not only convenience: the cases that matter
    here are a timeout, a 503, a 422 and a malformed 200, and three of those are hard to
    produce on demand from a service that works.
    """
    owned = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=PRON_TIMEOUT_S)

    try:
        try:
            response = await client.post(
                f"{PRON_URL}/score",
                files={
                    "file": (filename, data, content_type or "application/octet-stream")
                },
                data={"text": text},
            )
        except httpx.RequestError as exc:
            raise PronUnavailable(f"{type(exc).__name__}: {exc}") from exc

        if response.status_code == 500:
            detail = _detail_of(response)
            if "phone map" in detail.lower():
                raise PronMisconfigured(detail)
            raise PronUnavailable(f"HTTP 500: {detail}")
        if response.status_code >= 500:
            raise PronUnavailable(
                f"HTTP {response.status_code}: {_detail_of(response)}"
            )
        if response.status_code >= 400:
            raise PronRejected(_detail_of(response), response.status_code)

        try:
            return PronScoring.model_validate(response.json())
        except (ValueError, ValidationError) as exc:
            raise PronProtocolError(f"unexpected response shape: {exc}") from exc
    finally:
        if owned:
            await client.aclose()
