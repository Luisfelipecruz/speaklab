"""The pronunciation client's error taxonomy, driven without a 2 GB container.

Pure: no container, no database, no network. The same arrangement `test_tts_client.py`
uses, and for the same reason — the cases worth testing are the ones a working service
cannot produce on demand: a connection nobody accepts, the 503 it answers while its
dictionary loads, a 200 whose body is not the agreed shape.

The distinction these tests hold in place is *the text is bad* against *the service is
bad*. It decides what a learner is told. A section whose words cannot be turned into
phones is the writer's to fix, and the page names the words; a service that is not
running is nobody's fault, and the section is saved as scorable rather than marked
permanently wrong for a container that was switched off.
"""

import httpx
import pytest

from services.pron_client import (
    Phonemized,
    PronMisconfigured,
    PronProtocolError,
    PronRejected,
    PronUnavailable,
    phonemize,
    score,
)


def client_returning(*, json=None, status_code=200, content=None, raises=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if raises is not None:
            raise raises
        if json is not None:
            return httpx.Response(status_code, json=json)
        return httpx.Response(status_code, content=content or b"")

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


# ── What comes back when it works ───────────────────────────────────────────


async def test_the_words_that_cannot_be_scored_come_back_named():
    async with client_returning(json={"words": 5, "unscorable": ["2026"]}) as http:
        answer = await phonemize("We shipped it in 2026.", client=http)

    assert answer == Phonemized(words=5, unscorable=["2026"])


async def test_a_text_every_word_of_which_converts_names_none():
    async with client_returning(json={"words": 4, "unscorable": []}) as http:
        answer = await phonemize("The cat sat down.", client=http)

    assert answer.unscorable == []
    assert answer.words == 4


async def test_the_text_goes_out_as_the_form_field_the_service_reads():
    """`text`, form-encoded — the same field `/score` sends it under."""
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.content.decode()
        seen["path"] = request.url.path
        return httpx.Response(200, json={"words": 1, "unscorable": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        await phonemize("hello", client=http)

    assert seen["body"] == "text=hello"
    assert seen["path"] == "/phonemize"


# ── The text is bad ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("status_code", [400, 413, 422])
async def test_a_refusal_carries_its_reason_and_its_code(status_code):
    """A 4xx is the writer's to act on, so the reason is kept, not logged and lost."""
    async with client_returning(
        json={"detail": "no reference text"}, status_code=status_code
    ) as http:
        with pytest.raises(PronRejected) as raised:
            await phonemize("   ", client=http)

    assert raised.value.detail == "no reference text"
    assert raised.value.status_code == status_code


# ── The service is bad ──────────────────────────────────────────────────────


async def test_nobody_answering_is_unavailable_not_a_refusal():
    """The normal state on a laptop that never started the profile."""
    async with client_returning(
        raises=httpx.ConnectError("connection refused")
    ) as http:
        with pytest.raises(PronUnavailable) as raised:
            await phonemize("The cat sat down.", client=http)

    assert "ConnectError" in str(raised.value)


async def test_still_loading_is_unavailable():
    """503 while the dictionary loads. Asked again later, the same text converts."""
    async with client_returning(
        json={"detail": "the dictionary is still loading; retry shortly"},
        status_code=503,
    ) as http:
        with pytest.raises(PronUnavailable):
            await phonemize("The cat sat down.", client=http)


async def test_a_body_this_code_cannot_read_is_a_protocol_error():
    """A 200 in the wrong shape is a version skew between two images.

    Classified apart from a refusal because no rewording of the text fixes it, and apart
    from unavailability because the service is answering: it is a deployment fault, and
    the log should say so.
    """
    async with client_returning(json={"count": 5}) as http:
        with pytest.raises(PronProtocolError):
            await phonemize("The cat sat down.", client=http)


async def test_a_negative_word_count_is_not_accepted_as_a_word_count():
    async with client_returning(json={"words": -1, "unscorable": []}) as http:
        with pytest.raises(PronProtocolError):
            await phonemize("The cat sat down.", client=http)


# ── The mapping is one mapping ──────────────────────────────────────────────


async def test_a_phone_map_gap_is_this_project_s_bug_on_either_call():
    """Both calls classify statuses through the same code, so neither can drift.

    A phone-map gap is not transient and not the caller's fault: the image needs a new
    map. Retrying it forever, which is what unavailability would earn it, would hide the
    one failure here that is ours.
    """
    async with client_returning(
        json={"detail": "phone map gap: NX"}, status_code=500
    ) as http:
        with pytest.raises(PronMisconfigured):
            await score(b"RIFF", "the cat", client=http)
        with pytest.raises(PronMisconfigured):
            await phonemize("the cat", client=http)


async def test_a_plain_500_is_unavailable_on_either_call():
    async with client_returning(
        json={"detail": "something fell over"}, status_code=500
    ) as http:
        with pytest.raises(PronUnavailable):
            await score(b"RIFF", "the cat", client=http)
        with pytest.raises(PronUnavailable):
            await phonemize("the cat", client=http)
