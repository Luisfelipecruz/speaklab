# 0001 — Which Whisper, and the latency budget it does not meet

Status: accepted, with one gate explicitly unmet

---

## Decision

**`faster-whisper small.en` at int8, beam size 5, Silero VAD on.** This is what PRD §11
specifies; the measurement below shows it holds up on accuracy and does not on latency.

**The recogniser's latency gate is not met, and no model is swapped to make it look met.**
`small.en` transcribes ~6 s of audio in **1231 ms** against a **≤ 700 ms** budget
(PRD §9.1). `base.en` at beam 1 meets the budget at **525 ms** and is one environment
variable away — `WHISPER_MODEL=base.en` — but it triples the word error rate, and that
error rate is the input to every metric in the product. The switch waits on the thing the
budget is actually about, a whole conversational turn, and
[0003](0003-conversation-context-strategy.md) measures that turn: it meets its budget
with `small.en` in it.

---

## What was measured

Ten LibriSpeech test-clean utterances, ten speakers, 83 s, 232 reference words
(`eval/golden/asr/`). Word error rate uses `api/services/wer.py`, whose normalisation is
written out in its docstring because normalisation is what moves the number.

| Configuration | WER | sub / del / ins | 6.82 s | 10.09 s |
|---|---:|---|---:|---:|
| **`small.en` int8 beam 5 (default)** | **1.72 %** | 4 / 0 / 0 | **1231 ms** | 1416 ms |
| `small.en` int8 beam 1 | 1.72 % | 4 / 0 / 0 | 1352 ms | 1289 ms |
| `small.en` int8 beam 5, **VAD off** | 3.45 % | 7 / 1 / 0 | — | 1772 ms |
| `base.en` int8 beam 5 | 6.03 % | 9 / 0 / 5 | **4420 ms** | 984 ms |
| `base.en` int8 beam 1 | 4.31 % | 8 / 0 / 2 | **525 ms** | 599 ms |
| `tiny.en` int8 beam 1 | 4.74 % | 11 / 0 / 0 | — | 384 ms |
| `tiny.en` int8 beam 5 | — | — | 369 ms | 463 ms |

Latency is the **minimum of 7 timed runs after 3 warm-ups**, service-side
(`latency_ms`, so it excludes upload). Minimum rather than median on purpose — see
*How much to trust these numbers* below.

### Three findings the table does not say out loud

**1. Beam size buys `small.en` nothing, and costs `base.en` a great deal.** Identical
WER at beam 1 and beam 5 for `small.en`. For `base.en` the beam is actively harmful: it
*raises* WER from 4.31 % to 6.03 %, and the extra errors are **insertions** — words the
speaker did not say.

**2. That harm has a name, and it is reproducible.** On one 6.8 s utterance, `base.en`
at beam 5 takes **4564 ms** and produces:

> ref: THE INMATES BEING REMOVED AT THE APPOINTED HOUR **A FEW CANNON BALLS** WERE FIRED THROUGH THE STONE WALLS
> hyp: The inmates being removed, at the appointed hour, **if you can and** balls were fired through the stone walls. **B**

A mis-hearing, plus a hallucinated trailing `B` occupying 500 ms of the timeline that
contains no speech. `small.en` gets this utterance exactly right in 1082 ms. Ten
utterances cannot rank two configurations four errors apart, but they can catch a decoder
falling over, and they do.

**3. The VAD default is right on both axes at once, which is unusual enough to check.**
Turning Silero VAD off doubles WER (1.72 % → 3.45 %) *and* makes it slower (1416 →
1772 ms). It is on by default and stays on.

---

## Why `small.en` stays, given that it misses the budget

Four reasons, in the order they carry weight:

**The error rate is an input to everything, and the latency is not.** WER 1.72 % against
4.31 % is not a 2.6× difference in one feature; it is a 2.6× difference in the raw
material of the grammar analyser, the fluency metrics and the read-aloud scoring
reference. An ASR error scored as a grammar error is a correction the user cannot act on.
Latency has other levers. Accuracy does not.

**The measurement is not of the machine the budget describes.** PRD §9.1 says "measured
on the target machine (Apple M4 Max, 16 cores)". These numbers were taken with the host
at **load average 21** — three other project stacks, an Android emulator and a browser
running alongside, with the Docker VM alone at 680 % CPU. `small.en` may well meet
700 ms on an idle machine. Changing the product on a contaminated measurement is worse
than reporting the contamination.

**The PRD's own fallback order puts this second.** §9.1: *"stream the LLM reply into TTS
sentence by sentence; drop ASR to `base.en`; shorten the reply token cap."* Spending the
second lever before the cheapest one is the wrong order.

**The budget is a stage in a turn, and the turn is the requirement.** §9.1's binding
number is **p95 ≤ 3000 ms for a conversational turn**. A stage measured alone cannot
tell you whether the turn misses; a turn-level measurement can, and
[0003](0003-conversation-context-strategy.md) makes it.

**What makes this safe:** the fallback is implemented, measured and one variable.
`WHISPER_MODEL=base.en WHISPER_BEAM_SIZE=1` gives 525 ms at a known cost.

---

## Two choices in the image, both deliberate

**PyAV instead of the ffmpeg binary.** Audio is normalised to 16 kHz mono PCM at the
service boundary. PyAV *is* the ffmpeg libraries, loaded in-process, and faster-whisper
already depends on it — so this is the same codec support with no `apt install ffmpeg`
(~200 MB of Debian multimedia dependencies), no subprocess and no temporary file. It also
decodes and reports the source metadata from the same object, which is why
`audio_assets.format` and `.sample_rate` are what a decoder measured rather than what an
uploader claimed.

**The image is 746 MB.** The weight is CTranslate2 and ONNX Runtime (the latter is Silero
VAD's runtime), not torch — `openai-whisper` would be roughly 2.5 GB, which is the point of
the choice. The weights themselves are not in the image; they live on the shared
`model_cache` volume.

---

## How much to trust these numbers

**The WER is a floor, not a forecast.** LibriSpeech test-clean is native, fluent, adult,
read-aloud English in good recording conditions. The users of this product are none of
those things. 1.72 % is the error rate below which nothing downstream can be blamed on
the recogniser; the number for accented, disfluent, laptop-microphone speech is higher
by an amount this set cannot estimate. `eval/golden/asr/README.md` says so at length, and
[the recording protocol](../../eval/golden/pron/README.md) is the first five minutes of
fixing it.

**232 reference words means one word is 0.43 %.** The gap between `small.en` and
`base.en` (4 errors versus 10) is large enough to act on. The gap between `base.en` at
beam 1 and beam 5 (10 versus 14) is not, and is reported above as an observation rather
than a ranking.

**Latency is the minimum of seven runs** because the median on a machine at load 21 says
more about the Android emulator than about CTranslate2. Even the minimum is an upper
bound on what idle hardware would do. The *ratios* between rows are the claim; the
absolute values carry the machine's state with them.

**One thing is not measured at all:** concurrency. The service serialises inference on
purpose (`ASR_MAX_CONCURRENCY=1`), so a second simultaneous turn waits for the first.
With one user that is invisible, and it is a known gap.

---

## Revisit when

- A whole turn misses its 3000 ms p95 on a quiet machine: apply §9.1's fallbacks in
  order — stream TTS first, then `base.en`.
- A learner-speech golden set exists and the WER on it is bad enough that `medium.en` for
  offline re-scoring becomes worth its latency.
- The service needs to serve two users at once.
