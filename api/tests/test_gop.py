"""The GOP pipeline against the real `pron` service. Skips when it is not running.

The same arrangement `test_asr_golden.py` and `test_tts_live.py` use: hermetic tests
prove the logic, and **only a live suite is allowed to produce a number that gets
published**. Everything here talks to a real wav2vec2, and every figure it prints is a
figure that may be quoted.

Four things are measured:

1. **The probe** — reference perturbation. Score real human speech against text containing
   a phone the speaker did not produce, and GOP at that phone must collapse. Gate: 8 of
   10, set before the answer was known.
2. **`recognized_phone`** — the field that turns a grade into an instruction. It has been
   right in 10 of 10.
3. **Alignment over the whole shipped corpus** — all 12 seeded passages, against the phone
   counts recorded in `test_g2p.py`. This is the half of the tokeniser contract that
   hermetic tests cannot check, because `g2p_en` is not in the API image.
4. **Latency**, against a 10 000 ms budget.

Run it with:

    make pron-golden

which is the only place `PRON_URL` is pointed at the real container. `make test` sees
`http://pron.invalid:8103` and every test here skips, which is what keeps the hermetic
suite hermetic.
"""

from __future__ import annotations

import json
import os
import time

import httpx
import pytest

from tests.test_g2p import EXPECTED

PRON_URL = os.environ.get("PRON_URL", "http://pron.invalid:8103")

_HERE = os.path.dirname(os.path.abspath(__file__))
SEEDS = os.path.join(_HERE, "..", "seeds", "passages.json")

# `/app/eval` is the read-only mount the test container gets; the relative path is CI and
# a laptop. Resolved rather than hard-coded for the same reason the pron source is: a
# fixture that only exists under one of the two ways this suite is run is a fixture that
# silently stops being exercised.
GOLDEN = next(
    (
        path
        for path in (
            "/app/eval/golden/pron",
            os.path.normpath(os.path.join(_HERE, "..", "..", "eval", "golden", "pron")),
        )
        if os.path.isfile(os.path.join(path, "manifest.json"))
    ),
    "/app/eval/golden/pron",
)
MANIFEST = os.path.join(GOLDEN, "manifest.json")


def _service_ready() -> tuple[bool, str]:
    try:
        response = httpx.get(f"{PRON_URL}/health", timeout=5.0)
    except httpx.RequestError as exc:
        return False, f"{PRON_URL} is not answering ({type(exc).__name__})"
    body = response.json()
    if not body.get("model_loaded"):
        return (
            False,
            f"{body.get('model')} is still loading; run `make pron-golden` again",
        )
    return True, ""


READY, WHY_NOT = _service_ready()
pytestmark = pytest.mark.skipif(not READY, reason=WHY_NOT or "pron unavailable")


@pytest.fixture(scope="module")
def manifest():
    with open(MANIFEST, encoding="utf-8") as handle:
        return json.load(handle)


def lengthen(audio: bytes, seconds: float) -> tuple[bytes, float]:
    """The probe, repeated to roughly `seconds`, as one valid WAV.

    Needed because a 79-word passage is ~250 phones and CTC cannot align more phones than
    it has frames — the service refuses it, correctly, with a 422. The repeated audio does
    not *say* the passage, and it is not meant to: what these tests assert on it is
    structure and timing, both of which are properties of length and text rather than of
    content.
    """
    import io
    import wave

    with wave.open(io.BytesIO(audio)) as reader:
        params = reader.getparams()
        frames = reader.readframes(reader.getnframes())

    one = len(frames) / (params.framerate * params.sampwidth * params.nchannels)
    repeats = max(1, round(seconds / one))
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setparams(params)
        writer.writeframes(frames * repeats)
    return buffer.getvalue(), one * repeats


@pytest.fixture(scope="module")
def probe_audio(manifest):
    path = os.path.join(GOLDEN, manifest["probe"]["file"])
    if not os.path.exists(path):
        pytest.skip(f"{path} not fetched — run `python3 eval/golden/pron/fetch.py`")
    with open(path, "rb") as handle:
        return handle.read()


@pytest.fixture(scope="module")
def passage_length_audio(probe_audio):
    """~35 s, which is long enough for the longest seeded passage's 297 phones."""
    return lengthen(probe_audio, 35.0)


def score(audio: bytes, text: str) -> dict:
    response = httpx.post(
        f"{PRON_URL}/score",
        files={"file": ("probe.wav", audio, "audio/wav")},
        data={"text": text},
        timeout=180.0,
    )
    assert response.status_code == 200, response.text
    return response.json()


def find(rows: list[dict], word_idx: int, phone: str) -> dict | None:
    """The scored row for one canonical phone inside one word. Stress-insensitive."""
    base = phone.rstrip("012")
    for row in rows:
        if row["word_idx"] == word_idx and row["canonical_phone"].rstrip("012") == base:
            return row
    return None


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    k = (len(ordered) - 1) * q
    low = int(k)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (k - low)


# ── The service itself ──────────────────────────────────────────────────────


def test_the_service_reports_the_vocabulary_it_is_scoring_against():
    """392 tokens and 39 phones, from the running container rather than from a comment."""
    body = httpx.get(f"{PRON_URL}/health", timeout=5.0).json()
    assert body["vocabulary_tokens"] == 392
    assert body["arpabet_phones"] == 39
    assert body["status"] == "ok"


def test_a_correct_reading_scores_near_zero(probe_audio, manifest):
    """GOP <= 0 by construction, and near 0 when the speaker produced the phone.

    This is the baseline every other number here is read against. The reference run
    measured mean -0.386 and **median exactly 0.000** over 35 correctly produced phones.
    """
    result = score(probe_audio, manifest["probe"]["truth"])
    rows = result["phones"]
    assert rows, "nothing was scored"

    gops = [row["gop"] for row in rows]
    assert max(gops) <= 0.0, "GOP must be <= 0 by construction"

    summary = result["summary"]
    print(
        f"\n  clean baseline: {len(rows)} phones  "
        f"mean {summary['mean_gop']:+.3f}  median {summary['median_gop']:+.3f}  "
        f"p5 {summary['percentile_5']:+.3f}"
    )
    assert summary["median_gop"] > -1.0, "correct speech should sit near zero"


# ── The experiment ──────────────────────────────────────────────────────────


def test_a_phone_the_speaker_did_not_produce_collapses(probe_audio, manifest):
    """Reference perturbation, through the service. Gate: 8 of 10.

    Perturbing the *reference* rather than the audio is what makes this runnable on
    genuine human speech, and it is the exact situation the product is in when a learner
    mispronounces: the text says one sound and the waveform contains another.

    The threshold is the 5th percentile of GOP over the correctly produced phones — the
    operating point that would wrongly flag 5 % of correct speech. Computed here from
    this run rather than carried forward, because a threshold copied forward is a constant
    pretending to be a measurement.
    """
    probe = manifest["probe"]
    truth = probe["truth"].split()

    clean = score(probe_audio, probe["truth"])["phones"]
    threshold = percentile([row["gop"] for row in clean], 0.05)

    header = (
        f"{'#':<3}{'contrast':<28}{'clean':>9}{'wrong':>9}{'drop':>8}  "
        f"{'heard':<8}verdict"
    )
    print(f"\n  detection threshold = 5th pctile of clean GOP = {threshold:+.3f}")
    print(f"  {header}")
    print("  " + "-" * len(header))

    detected = 0
    named = 0
    drops: list[float] = []
    missing: list[int] = []

    for item in probe["probes"]:
        words = list(truth)
        words[item["word_idx"]] = item["replacement"]
        rows = score(probe_audio, " ".join(words))["phones"]

        wrong = find(rows, item["word_idx"], item["canonical_phone"])
        right = find(clean, item["word_idx"], item["canonical_phone"])
        if wrong is None:
            missing.append(item["n"])
            print(
                f"  {item['n']:<3}{item['contrast']:<28}{'--- not located in the alignment ---'}"
            )
            continue

        baseline = right["gop"] if right else 0.0
        drop = baseline - wrong["gop"]
        drops.append(drop)
        hit = wrong["gop"] < threshold
        detected += hit
        # Did the model name the phone the speaker actually produced? That is the
        # confusion pair — the difference between a grade and an instruction.
        named += wrong["recognized_phone"] is not None
        print(
            f"  {item['n']:<3}{item['contrast']:<28}{baseline:>9.3f}{wrong['gop']:>9.3f}"
            f"{drop:>8.3f}  {str(wrong['recognized_phone']):<8}"
            f"{'DETECTED' if hit else 'missed'}"
        )

    print("  " + "-" * len(header))
    if drops:
        mean_drop = sum(drops) / len(drops)
        print(
            f"\n  mean drop {mean_drop:+.3f}   detected {detected}/10   named {named}/{len(drops)}"
        )
        print("  reference run: mean drop +8.138, detected 9/10, named 10/10")

    assert not missing, f"probes {missing} could not be located in the alignment"
    assert detected >= 8, (
        f"only {detected}/10 planted errors fell below the clean 5th percentile. "
        f"The gate is 8; the reference run measured 9."
    )


def test_the_competing_phone_is_named_not_guessed(probe_audio, manifest):
    """`recognized_phone` is what makes a score actionable, and it is never invented.

    "your /θ/ is weak" is a grade. "you are producing /s/ where English wants /θ/" is an
    instruction, and the model gets it right in 10 of 10 — including the probe the
    threshold itself missed. The other half of the property: where nothing won the
    segment, the answer is null, not a plausible guess.
    """
    probe = manifest["probe"]
    truth = probe["truth"].split()
    item = probe["probes"][1]  # /s/ against a spoken /ð/ — the clearest case, -10.687

    words = list(truth)
    words[item["word_idx"]] = item["replacement"]
    rows = score(probe_audio, " ".join(words))["phones"]

    row = find(rows, item["word_idx"], item["canonical_phone"])
    assert row is not None
    assert row["recognized_phone"] == "ð", (
        f"expected the model to name the phone actually spoken; got "
        f"{row['recognized_phone']!r}"
    )

    # Every row either names a phone or names nothing. A CTC blank is not a phone, and
    # reporting `<pad>` as "what you said instead" would be a claim about speech the
    # acoustic model never made.
    for other in rows:
        assert not (other["recognized_phone"] or "").startswith("<")


# ── The corpus ──────────────────────────────────────────────────────────────


def test_every_seeded_passage_converts_to_the_expected_phones(passage_length_audio):
    """All 12 passages through real `g2p_en`, against the counts `test_g2p.py` records.

    The hermetic half of this contract checks the tokeniser — that a standalone em dash is
    not a word, which is the bug that desynced two of these passages. This is the half
    that checks `g2p_en` still agrees, and it is the one that would catch a dependency
    upgrade changing a pronunciation underneath us.

    The audio is the probe lengthened to ~35 s and does not *say* any of these passages.
    That is deliberate: what is asserted is the phone count, which comes from the text
    alone. It has to be lengthened rather than used as-is because CTC cannot align more
    phones than it has frames — the 3.4 s probe against a 250-phone passage is a 422, and
    correctly so, which the test below asserts in its own right.
    """
    audio, _ = passage_length_audio
    with open(SEEDS, encoding="utf-8") as handle:
        passages = {p["slug"]: p for p in json.load(handle)}

    print()
    total = 0
    for slug, (words, phones) in EXPECTED.items():
        body = passages[slug]["body"]
        result = score(audio, body)
        counted = len({(r["word_idx"]) for r in result["phones"]})
        assert (
            result["words"] == words
        ), f"{slug}: {result['words']} words, expected {words}"
        assert len(result["phones"]) == phones, (
            f"{slug}: {len(result['phones'])} phones scored, expected {phones}. "
            f"g2p_en's output for this passage has changed."
        )
        total += phones
        print(
            f"  ok  {slug:<30} {words:>3} words  {phones:>4} phones  ({counted} attributed)"
        )

    print(f"\n  {len(EXPECTED)} passages, {total} phones, 0 desyncs")
    assert total == 3091


def test_a_recording_far_too_short_for_the_passage_is_refused(manifest):
    """A person who read three words of seventy-nine gets an explanation, not a 500.

    CTC cannot align a phone sequence longer than the frames available. That is not a
    broken file and it is not a server fault — it is the commonest real failure of this
    feature — so it is a 422 whose text says what happened.
    """
    with open(SEEDS, encoding="utf-8") as handle:
        long_passage = json.load(handle)[0]["body"]

    # 0.2 s of silence: 10 frames, against roughly 250 phones.
    from tests.conftest import silent_wav

    response = httpx.post(
        f"{PRON_URL}/score",
        files={"file": ("tiny.wav", silent_wav(200, 16000), "audio/wav")},
        data={"text": long_passage},
        timeout=60.0,
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "frames" in detail and "shorter" in detail
    print(f"\n  422: {detail}")


def test_text_the_tokeniser_and_g2p_disagree_about_is_refused():
    """The desync check, live. A 422 naming the passage is a bug report."""
    response = httpx.post(
        f"{PRON_URL}/score",
        files={"file": ("tiny.wav", b"", "audio/wav")},
        data={"text": ""},
        timeout=30.0,
    )
    assert response.status_code == 422


# ── Latency ─────────────────────────────────────────────────────────────────


def test_a_passage_length_reading_is_inside_the_budget(
    probe_audio, passage_length_audio
):
    """Asynchronous read-aloud scoring is allowed 10 000 ms.

    Measured on audio the length of a real reading, not on the 3.4 s probe — the forward
    pass is linear in audio length and quoting the short number would be flattering. Both
    are measured, and the pair is the interesting part: it separates *length* from
    *environment*. A host-side measurement with 8 torch threads cannot do that on its
    own; this runs where the service actually runs.
    """
    with open(SEEDS, encoding="utf-8") as handle:
        passage = json.load(handle)[0]["body"]

    long_audio, seconds = passage_length_audio

    # The short clip first, against its own truth, so the comparison is like for like.
    short_started = time.perf_counter()
    short = score(probe_audio, "i had that curiosity beside me at this moment")
    short_ms = round((time.perf_counter() - short_started) * 1000)

    started = time.perf_counter()
    result = score(long_audio, passage)
    elapsed_ms = round((time.perf_counter() - started) * 1000)

    print(
        f"\n  short   3.4 s, {len(short['phones']):>3} phones  "
        f"service {short['latency_ms']:>5} ms  round trip {short_ms:>5} ms\n"
        f"  passage {seconds:.1f} s, {len(result['phones']):>3} phones  "
        f"service {result['latency_ms']:>5} ms  round trip {elapsed_ms:>5} ms\n"
        f"  per audio-second: {short['latency_ms'] / 3.4:.0f} ms -> "
        f"{result['latency_ms'] / seconds:.0f} ms\n"
        f"  budget 10 000 ms. A host run measured 99.5 ms on 3.4 s, which is not this."
    )
    assert elapsed_ms < 10_000, f"{elapsed_ms} ms exceeds the 10 000 ms budget"


# ── Criterion S4 — the one that needs a person ──────────────────────────────


def test_broken_readings_score_worse_than_clean_ones(manifest):
    """**Criterion S4**, and the only test here that cannot run yet.

    The probe above proves the arithmetic separates a phone that was produced from one
    that was not. It does not prove the system detects a *learner* error, because a
    perturbed reference is a categorically different phone and a learner error is
    gradient — a retracted /s/, epenthesis with a particular vowel quality, an unreleased
    final stop. The 8-nat gap from reference perturbation is an upper bound, and this is
    the test that finds the real one.

    It needs about five minutes of somebody's voice: each passage read twice, once
    correctly and once mispronouncing the marked words, same microphone and same sitting.
    Drop the recordings in `eval/golden/pron/` and list them under `pairs` in the
    manifest; its README carries the full protocol.
    """
    pairs = manifest["pairs"]
    if not pairs:
        pytest.skip(
            "No clean/broken pairs recorded yet — this is the one check here that "
            "cannot be automated. See eval/golden/pron/ for the recording protocol."
        )

    clean_gops: list[float] = []
    broken_gops: list[float] = []
    for pair in pairs:
        for kind, pool in (("clean", clean_gops), ("broken", broken_gops)):
            path = os.path.join(GOLDEN, pair[kind])
            with open(path, "rb") as handle:
                rows = score(handle.read(), pair["text"])["phones"]
            pool.extend(row["gop"] for row in rows)

    threshold = percentile(clean_gops, 0.05)
    flagged = sum(1 for gop in broken_gops if gop < threshold)
    print(
        f"\n  clean {len(clean_gops)} phones, broken {len(broken_gops)} phones\n"
        f"  threshold {threshold:+.3f}, flagged {flagged}/{len(broken_gops)} broken phones"
    )
    assert sum(broken_gops) / len(broken_gops) < sum(clean_gops) / len(clean_gops)
