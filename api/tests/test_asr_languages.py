"""The recognisers' languages and tasks, against the live services.

`asr` runs the English-only `small.en`, which every English figure is measured on. It
refuses another language and a translation with a 422 that says so, and a request naming
nothing is transcribed in English exactly as a request naming English is. `asr-multi` runs
the multilingual `small` and chooses between the languages it is given.

**Skipped unless the services answer**, like the golden ASR suite: `make test` points both
addresses at hosts that do not resolve. `make asr-languages` runs it against the
containers. The Spanish cases read the Say it in English golden set, which stays on the
machine that recorded it, and skip without it.
"""

import json
from pathlib import Path

import httpx
import pytest

from config import ASR_MULTI_URL, ASR_URL
from services.asr_client import AsrRejected, transcribe
from tests.conftest import API_ROOT


def _golden(name: str) -> Path | None:
    for root in (
        Path("/app/eval/golden"),
        Path(API_ROOT).resolve().parent / "eval/golden",
    ):
        if (root / name).exists():
            return root / name
    return None


ENGLISH = _golden("asr")
SAY = _golden("say")


def _loaded(url: str) -> bool:
    try:
        response = httpx.get(f"{url}/health", timeout=3.0)
    except httpx.RequestError:
        return False
    return response.is_success and response.json().get("model_loaded") is True


def _english_clip() -> bytes:
    manifest = json.loads((ENGLISH / "manifest.json").read_text())
    return (ENGLISH / manifest["items"][0]["file"]).read_bytes()


def _spanish_clip() -> bytes | None:
    for name in ("manifest.json", "manifest.local.json"):
        path = SAY / name if SAY else None
        if path and path.exists():
            for item in json.loads(path.read_text(encoding="utf-8"))["items"]:
                if item["language"] == "es" and (SAY / item["audio"]).exists():
                    return (SAY / item["audio"]).read_bytes()
    return None


needs_asr = pytest.mark.skipif(
    ENGLISH is None or not _loaded(ASR_URL),
    reason=f"no loaded asr at {ASR_URL}: `make up`, then `make asr-languages`",
)
needs_multi = pytest.mark.skipif(
    ENGLISH is None or not _loaded(ASR_MULTI_URL),
    reason=f"no loaded asr-multi at {ASR_MULTI_URL}: `make say-up`, then `make asr-languages`",
)


@needs_asr
@pytest.mark.parametrize(
    ("fields", "says"),
    [
        ({"language": "es"}, "English-only"),
        ({"language": "es,en"}, "English-only"),
        ({"language": "auto"}, "English-only"),
        ({"language": "en", "task": "translate"}, "nothing to translate"),
    ],
)
async def test_the_english_recogniser_refuses_what_it_cannot_do_and_says_why(
    fields, says
):
    with pytest.raises(AsrRejected) as refused:
        await transcribe(_english_clip(), filename="clip.flac", **fields)

    assert refused.value.status_code == 422
    assert says in refused.value.detail


@needs_asr
async def test_a_request_naming_nothing_is_transcribed_as_one_naming_english():
    clip = _english_clip()
    plain = await transcribe(clip, filename="clip.flac")
    named = await transcribe(clip, filename="clip.flac", language="en")

    assert plain.text == named.text
    assert (plain.language, plain.task, plain.language_scores) == (
        "en",
        "transcribe",
        None,
    )
    assert plain.model.endswith(".en")


@needs_multi
async def test_the_multilingual_recogniser_chooses_english_for_english():
    result = await transcribe(
        _english_clip(), filename="clip.flac", language="es,en", url=ASR_MULTI_URL
    )

    assert result.language == "en"
    assert set(result.language_scores) == {"es", "en"}
    assert result.language_scores["en"] > result.language_scores["es"]


@needs_multi
async def test_the_multilingual_recogniser_chooses_spanish_for_spanish():
    clip = _spanish_clip()
    if clip is None:
        pytest.skip("no Spanish recording in eval/golden/say on this machine")

    result = await transcribe(
        clip, filename="clip.webm", language="es,en", url=ASR_MULTI_URL
    )

    assert result.language == "es"
    assert result.task == "transcribe"


@needs_multi
async def test_the_multilingual_recogniser_translates_when_asked():
    clip = _spanish_clip() or _english_clip()
    result = await transcribe(
        clip, filename="clip", language="es", task="translate", url=ASR_MULTI_URL
    )

    assert result.task == "translate"
    assert result.text.strip()


@needs_multi
async def test_the_multilingual_recogniser_refuses_a_language_whisper_does_not_know():
    with pytest.raises(AsrRejected) as refused:
        await transcribe(
            _english_clip(), filename="clip.flac", language="xx", url=ASR_MULTI_URL
        )

    assert refused.value.status_code == 422
    assert "'xx'" in refused.value.detail
