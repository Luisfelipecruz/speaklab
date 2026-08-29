"""The ASR client's error taxonomy, and the WER scorer's normalisation.

Both halves are pure: no container, no database, no network. They are here rather than
in the golden-set suite because the cases that matter most are the ones a working
service cannot produce on demand — a timeout, a 503, a 200 whose body has drifted out of
shape.

The distinction under test throughout is between *the recording is bad* and *the system
is bad*. Collapsing those is how a retry loop gets written against audio that will never
decode, and it is a one-line mistake — a single `except Exception` — so it gets its own
tests rather than a comment.
"""

import httpx
import pytest

from services.asr_client import (
    AsrProtocolError,
    AsrRejected,
    AsrUnavailable,
    transcribe,
)
from services.wer import normalise, wer

# A minimal but complete response, in the shape infra/asr/app.py actually returns. It
# is written out here rather than captured from the service on purpose: if the two
# drift, this file is the record of what the API was promised.
GOOD_RESPONSE = {
    "text": "hello there",
    "words": [
        {"w": "hello", "start_ms": 0, "end_ms": 400, "logprob": -0.01},
        {"w": "there", "start_ms": 400, "end_ms": 700, "logprob": -0.2},
    ],
    "confidence": 0.9,
    "timestamp_fixups": 0,
    "language": "en",
    "model": "small.en",
    "decoder": {"beam_size": 5, "vad_filter": True, "compute_type": "int8"},
    "source": {
        "format": "wav",
        "codec": "pcm_s16le",
        "sample_rate": 16000,
        "channels": 1,
        "duration_ms": 700,
    },
    "latency_ms": 120,
}


def client_returning(*, json=None, status_code=200, text=None, raises=None):
    """An httpx client whose transport answers however the test needs it to."""

    def handler(request: httpx.Request) -> httpx.Response:
        if raises is not None:
            raise raises
        if text is not None:
            return httpx.Response(status_code, text=text)
        return httpx.Response(status_code, json=json)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


# ── The happy path ──────────────────────────────────────────────────────────


async def test_a_transcript_comes_back_as_typed_words():
    async with client_returning(json=GOOD_RESPONSE) as http:
        result = await transcribe(b"fake audio", client=http)

    assert result.text == "hello there"
    assert [word.w for word in result.words] == ["hello", "there"]
    # Not a dict. The parse is the point: m6 dumps these straight into `turns.words`,
    # and a field the service renamed should fail here rather than there.
    assert result.words[0].start_ms == 0
    assert result.source.duration_ms == 700
    assert result.decoder.beam_size == 5


async def test_the_upload_is_sent_as_multipart_under_the_field_the_service_reads():
    """`file`, not `audio` or the raw body.

    A field-name mismatch produces a 422 from FastAPI that reads like malformed audio,
    which would send somebody looking at the recording rather than at the request.
    """
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["content_type"] = request.headers["content-type"]
        seen["body"] = request.content
        return httpx.Response(200, json=GOOD_RESPONSE)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        await transcribe(b"RIFFfake", filename="turn.webm", client=http)

    assert seen["content_type"].startswith("multipart/form-data")
    assert b'name="file"' in seen["body"]
    assert b"turn.webm" in seen["body"]
    assert b"RIFFfake" in seen["body"]


# ── The recording is bad ────────────────────────────────────────────────────


@pytest.mark.parametrize("status_code", [400, 413, 415, 422])
async def test_a_4xx_is_a_rejection_that_carries_its_status_and_reason(status_code):
    async with client_returning(
        status_code=status_code,
        json={"detail": "cannot decode audio: InvalidDataError"},
    ) as http:
        with pytest.raises(AsrRejected) as caught:
            await transcribe(b"not audio", client=http)

    assert caught.value.status_code == status_code
    # The reason travels: this becomes the body of the 422 the browser sees, and
    # "cannot decode audio" is something a user can act on. "ASR failed" is not.
    assert "cannot decode" in caught.value.detail


# ── The system is bad ───────────────────────────────────────────────────────


async def test_nobody_answering_is_unavailable_not_a_rejection():
    async with client_returning(
        raises=httpx.ConnectError("[Errno -2] Name or service not known")
    ) as http:
        with pytest.raises(AsrUnavailable) as caught:
            await transcribe(b"audio", client=http)

    # The exception type is preserved because that is the part an operator needs: a
    # ConnectError and a ReadTimeout are the same outcome and different problems.
    assert "ConnectError" in str(caught.value)


async def test_a_timeout_is_unavailable():
    async with client_returning(raises=httpx.ReadTimeout("timed out")) as http:
        with pytest.raises(AsrUnavailable):
            await transcribe(b"audio", client=http)


@pytest.mark.parametrize("status_code", [500, 502, 503])
async def test_a_5xx_is_unavailable_because_the_recording_was_never_the_problem(
    status_code,
):
    """Including 503, which is what the service answers while its weights load.

    That case is the one that must not be an `AsrRejected`: the same bytes will
    transcribe perfectly two minutes later.
    """
    async with client_returning(
        status_code=status_code, json={"detail": "small.en is still loading"}
    ) as http:
        with pytest.raises(AsrUnavailable):
            await transcribe(b"audio", client=http)


# ── The two services have drifted apart ─────────────────────────────────────


async def test_a_200_that_is_not_json_is_a_protocol_error():
    async with client_returning(text="<html>502 Bad Gateway</html>") as http:
        with pytest.raises(AsrProtocolError):
            await transcribe(b"audio", client=http)


async def test_a_200_missing_a_field_is_a_protocol_error_not_a_silent_default():
    body = {key: value for key, value in GOOD_RESPONSE.items() if key != "words"}
    async with client_returning(json=body) as http:
        with pytest.raises(AsrProtocolError):
            await transcribe(b"audio", client=http)


async def test_a_positive_logprob_is_rejected():
    """A logprob above zero is a probability above one.

    It cannot happen and therefore means the field has changed meaning — most likely
    to a raw probability, which would pass straight through an untyped parse and make
    every confidence gate downstream compare the wrong scale.
    """
    body = {
        **GOOD_RESPONSE,
        "words": [{"w": "x", "start_ms": 0, "end_ms": 1, "logprob": 0.5}],
    }
    async with client_returning(json=body) as http:
        with pytest.raises(AsrProtocolError):
            await transcribe(b"audio", client=http)


# ── WER, and what its normalisation decides ─────────────────────────────────


def test_normalisation_folds_case_and_drops_punctuation():
    assert normalise("Hello, there!") == ["hello", "there"]


def test_normalisation_keeps_apostrophes_inside_words():
    """`don't` is one word. `dont` and `do not` are different words from it."""
    assert normalise("I don't know") == ["i", "don't", "know"]


def test_normalisation_drops_quoting_apostrophes_at_a_word_edge():
    assert normalise("she said 'hello' twice") == ["she", "said", "hello", "twice"]


def test_an_exact_match_scores_zero():
    assert wer("THE SHIP WAS IN BAD SHAPE", "The ship was in bad shape.").rate == 0.0


def test_the_three_edit_types_are_counted_separately():
    """The rate alone cannot tell a model that drops words from one that invents them."""
    result = wer("a b c d", "a x c d e")
    assert (result.substitutions, result.deletions, result.insertions) == (1, 0, 1)
    assert result.errors == 2
    assert result.rate == 0.5


def test_a_dropped_word_is_a_deletion():
    result = wer("the ship was in bad shape", "the ship was in shape")
    assert (result.substitutions, result.deletions, result.insertions) == (0, 1, 0)


def test_numbers_are_not_normalised_to_words():
    """A deliberate choice, tested so that changing it has to be deliberate too.

    `20` against `TWENTY` is a substitution. Mapping them together would hide a real
    difference between recognisers from a metric whose whole job is to expose it.
    """
    assert wer("TWENTY OARS", "20 oars").substitutions == 1


def test_an_empty_hypothesis_is_all_deletions_and_a_rate_of_one():
    result = wer("a b c", "")
    assert result.deletions == 3
    assert result.rate == 1.0


def test_an_empty_reference_with_output_is_capped_at_one_rather_than_dividing_by_zero():
    result = wer("", "hello")
    assert result.reference_words == 0
    assert result.rate == 1.0
