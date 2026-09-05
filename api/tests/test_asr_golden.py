"""The measurement suite: real audio, a real model, a number at the end.

**This suite is skipped unless a real asr service is reachable**, and that is the
correct default rather than a compromise. `make test` and CI both point `ASR_URL` at a
host that does not resolve, on purpose — the health tests need an unreachable model
service — and a suite that silently downloaded 500 MB of weights to run three
assertions would not be a suite anybody runs. To run these:

    docker compose up -d asr
    ASR_URL=http://localhost:8101 python -m pytest tests/test_asr_golden.py -v

What is asserted here versus what is merely reported matters:

- **Asserted:** the transcript is close enough to the reference that the pipeline is
  demonstrably working, timestamps satisfy the contract the wire format promises, and
  the service reports having repaired nothing.
- **Reported, not asserted:** latency. It is measured on whatever machine happens to be
  running, and a laptop with a compile going will fail a millisecond threshold while
  the code is perfect. Turning a measurement into a gate needs a recorded baseline on
  known hardware, which is the eval harness's job rather than this file's.

Ten utterances is 232 reference words, so **one word is 0.43% of WER**. That is enough
to tell a working pipeline from a broken one and enough to separate `small.en` from
`tiny.en`; it is nowhere near enough to rank two configurations four errors apart. The
ceilings below are set accordingly — they catch "the model got swapped" and "the audio
is arriving corrupted", not "the WER moved by half a point".
"""

import json
import os
from pathlib import Path

import httpx
import pytest

from config import ASR_URL
from services.asr_client import transcribe
from services.wer import wer
from tests.conftest import API_ROOT
from tests.eval_out import record

# In the container `eval/` is mounted read-only at /app/eval; on a host it is beside
# api/. Read-only is a property worth having: the corpus a system is evaluated on must
# not be writable by the system being evaluated.
GOLDEN = next(
    (
        candidate
        for candidate in (
            Path("/app/eval/golden/asr"),
            Path(API_ROOT).resolve().parent / "eval/golden/asr",
        )
        if (candidate / "manifest.json").exists()
    ),
    None,
)

# Per model, the WER ceiling this suite will accept. Derived from the measurements in
# docs/decisions/0001 with roughly a doubling of headroom, because the point is to catch
# a pipeline fault rather than to re-litigate the model choice on ten utterances.
WER_CEILINGS = {"small.en": 0.05, "base.en": 0.10, "tiny.en": 0.15}
DEFAULT_CEILING = 0.20


def _asr_is_reachable() -> bool:
    try:
        response = httpx.get(f"{ASR_URL}/health", timeout=3.0)
    except httpx.RequestError:
        return False
    return response.is_success and response.json().get("model_loaded") is True


needs_asr = pytest.mark.skipif(
    GOLDEN is None or not _asr_is_reachable(),
    reason=(
        f"no golden set, or no loaded asr service at {ASR_URL}. "
        "Run `docker compose up -d asr` and set ASR_URL=http://localhost:8101."
    ),
)


def golden_items() -> list[dict]:
    return json.loads((GOLDEN / "manifest.json").read_text())["items"]


@pytest.fixture(scope="module")
def manifest() -> list[dict]:
    return golden_items()


# ── The fixtures themselves ─────────────────────────────────────────────────
#
# These run everywhere, including in CI, because a corrupted golden set would make every
# assertion below meaningless in a way that looks like a model regression.


@pytest.mark.skipif(GOLDEN is None, reason="golden set not mounted")
def test_the_golden_audio_is_the_audio_the_manifest_describes():
    """sha256 of every file, against the manifest that was committed with it.

    An evaluation fixture that can change without anybody noticing is not a fixture.
    """
    import hashlib

    for item in golden_items():
        digest = hashlib.sha256((GOLDEN / item["file"]).read_bytes()).hexdigest()
        assert (
            digest == item["sha256"]
        ), f"{item['file']} is not the file it claims to be"


@pytest.mark.skipif(GOLDEN is None, reason="golden set not mounted")
def test_the_golden_set_spans_more_than_one_speaker():
    """Ten utterances from one voice would measure one voice."""
    items = golden_items()
    assert len({item["speaker_id"] for item in items}) >= 8
    assert len(items) >= 10


# ── The model ───────────────────────────────────────────────────────────────


@needs_asr
async def test_word_error_rate_on_the_golden_set(manifest, capsys):
    """The number this milestone exists to be able to state."""
    errors = reference_words = 0
    substitutions = deletions = insertions = 0
    model = None

    for item in manifest:
        result = await transcribe((GOLDEN / item["file"]).read_bytes(), item["file"])
        model = result.model
        score = wer(item["text"], result.text)
        errors += score.errors
        reference_words += score.reference_words
        substitutions += score.substitutions
        deletions += score.deletions
        insertions += score.insertions

    rate = errors / reference_words
    ceiling = WER_CEILINGS.get(model, DEFAULT_CEILING)

    with capsys.disabled():
        print(
            f"\n  {model}: WER {errors}/{reference_words} = {rate * 100:.2f}% "
            f"(sub {substitutions}, del {deletions}, ins {insertions}), "
            f"ceiling {ceiling * 100:.0f}%"
        )

    record(
        "asr",
        {
            "status": "measured",
            "model": model,
            "wer": rate,
            "errors": errors,
            "reference_words": reference_words,
            "utterances": len(manifest),
            "substitutions": substitutions,
            "deletions": deletions,
            "insertions": insertions,
            "ceiling": ceiling,
        },
    )

    assert rate <= ceiling, f"{model} scored {rate:.1%} against a {ceiling:.0%} ceiling"


@needs_asr
async def test_word_timestamps_satisfy_the_contract_the_wire_format_promises(manifest):
    """Monotonic, non-negative, ordered, and inside the audio.

    Every fluency metric is arithmetic on these numbers. A word ending
    before it starts produces a negative duration, and a negative duration in a
    speech-rate calculation produces a number that is not wrong so much as meaningless.
    """
    for item in manifest:
        result = await transcribe((GOLDEN / item["file"]).read_bytes(), item["file"])
        duration_ms = result.source.duration_ms
        words = result.words
        assert words, f"{item['id']} produced no words at all"

        for word in words:
            assert (
                0 <= word.start_ms <= word.end_ms <= duration_ms
            ), f"{item['id']}: {word}"

        starts = [word.start_ms for word in words]
        assert starts == sorted(starts), f"{item['id']} has words out of order"


@needs_asr
async def test_the_service_reports_repairing_nothing_on_clean_speech(manifest):
    """`timestamp_fixups` is a counter, not a suppression.

    The service clamps out-of-contract timings and says how many it clamped. On the
    golden set that count should be zero; a non-zero one is a fact about the model
    worth seeing rather than a failure — which is why it is counted at all.
    """
    total = 0
    for item in manifest:
        result = await transcribe((GOLDEN / item["file"]).read_bytes(), item["file"])
        total += result.timestamp_fixups
    assert total == 0


@needs_asr
async def test_the_decoder_reports_the_source_it_was_given(manifest):
    """FLAC in, and the service says so.

    The golden set is FLAC precisely so that this path is exercised: the browser sends
    WebM and MP4, and a fixture already in the target format would never prove the
    service normalises anything.
    """
    item = manifest[0]
    result = await transcribe((GOLDEN / item["file"]).read_bytes(), item["file"])

    assert result.source.format == "flac"
    assert result.source.channels == 1
    # Within a frame of the duration the manifest recorded from the file header.
    assert abs(result.source.duration_ms - item["duration_s"] * 1000) < 100


@needs_asr
async def test_bytes_that_are_not_audio_are_rejected_rather_than_transcribed():
    """A 422 from the service, an `AsrRejected` here — never a 500 and never a transcript."""
    from services.asr_client import AsrRejected

    with pytest.raises(AsrRejected) as caught:
        await transcribe(b"this is a text file, not a recording", "notes.txt")

    assert caught.value.status_code == 422


@needs_asr
async def test_a_truncated_recording_does_not_claim_the_duration_it_intended(manifest):
    """Half a FLAC file is still decodable, and its header still says how long it was.

    `duration_ms` comes from the decoded sample count for this reason. A row that
    records the intended duration of a recording that arrived incomplete would put a
    wrong denominator under every rate computed from it.
    """
    item = manifest[0]
    whole = (GOLDEN / item["file"]).read_bytes()

    try:
        result = await transcribe(whole[: len(whole) // 2], item["file"])
    except Exception as exc:  # noqa: BLE001 - a rejection is an equally correct outcome
        from services.asr_client import AsrRejected

        assert isinstance(exc, AsrRejected)
        return

    assert result.source.duration_ms < item["duration_s"] * 1000


@needs_asr
async def test_the_environment_is_wired_the_way_the_measurement_assumed(manifest):
    """The decoder settings travel with the transcript, so a stale number is detectable.

    A WER measured at `beam_size=1` and a WER measured at `beam_size=5` are different
    claims, and the only thing that makes them distinguishable six months later is that
    the service says which one it was.
    """
    result = await transcribe((GOLDEN / manifest[0]["file"]).read_bytes())

    assert result.decoder.compute_type
    assert result.decoder.beam_size >= 1
    assert result.model == os.environ.get("WHISPER_MODEL", result.model)
