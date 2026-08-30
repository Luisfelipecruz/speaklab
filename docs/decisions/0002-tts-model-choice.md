# 0002 — Piper, and the thread count that decides whether the budget is met

**Status:** accepted
**Date:** 2026-08-30 · **Milestone:** m5 · **Supersedes:** nothing · **Revisit at:** m6

---

## Decision

**Piper 1.7 (`piper-tts` on onnxruntime), voice `en_US-lessac-medium`, at eight
intra-op threads, emitting WAV.** The voice is baked into the image at build time. The
service exposes the whole-reply endpoint the plan specified *and* a per-sentence
streaming endpoint the plan did not, because the measurement below is that the first one
alone cannot meet PRD §9.1's 400 ms budget on a full-length reply on a machine doing
anything else.

Three of those are the plan's, unchanged and now with evidence behind them. Two are new:

- **`intra_op_num_threads = 8`, set by hand.** onnxruntime's own default is **2.3×
  slower** on this machine. Leaving it to the library is the difference between missing
  the budget and meeting it, and nothing about the code would have shown that.
- **A streaming endpoint in m5, not m6.** PRD §9.1's first prescribed fallback is
  *"stream the LLM reply into TTS sentence by sentence"*. Piper already produces audio
  one sentence at a time; exposing that is fifteen lines in a file this milestone was
  writing anyway, and it drops time-to-first-audio from 320 ms to **78 ms**, flat in the
  length of the reply.

---

## What was measured

Three replies of the length the product actually produces. PRD §9.1 budgets the persona
reply at ~80 output tokens, which is the "long" row — the one that matters, and the one
a 30-word test would have missed.

Latency is the **minimum of 7 timed runs after 3 warm-ups**, end to end over HTTP
including WAV assembly. Minimum rather than median, and the machine's load average is
printed beside every table, for the reason m4 learned the hard way (handoff trap 27).

### The configuration that ships — the live compose service, load average 8.7

Minimum of **11** runs after 3 warm-ups, against `docker compose up`'s own `tts`.

| Reply | Sentences | Audio | Whole reply | **First sentence** | All sentences | RTF |
|---|---:|---:|---:|---:|---:|---:|
| short, 11 words | 2 | 2.69 s | 65 ms | **33 ms** | 79 ms | 0.024 |
| typical, 32 words | 2 | 8.38 s | 171 ms | **93 ms** | 166 ms | 0.020 |
| **long, 61 words (~80 tokens)** | 4 | 15.84 s | **320 ms** | **78 ms** | 332 ms | 0.020 |

Every row is inside the 400 ms budget, and synthesis runs at roughly **50× real time**.

An independent min-of-7 run earlier the same evening, at load average 4.9 and against a
standalone container built from the same image, gave **339 ms / 94 ms** on the long reply.
Two runs an hour apart under different loads agreeing to within 6 % is the reason these
numbers are quoted at all.

### The same service on a busy machine — load average 22–28

Sixteen cores shared with an iOS simulator, a UI-test runner, `xcodebuild` and an Android
emulator. This is not a pathological case; it is a laptop with other work on it.

| Reply | Whole reply | **First sentence** |
|---|---:|---:|
| short, 11 words | 132 ms | **52 ms** |
| typical, 32 words | 373 ms | **205 ms** |
| **long, 61 words** | **771 ms — misses** | **135 ms — meets** |

This is the row that decided the streaming endpoint. Under contention the whole-reply
call misses the budget by 1.9×, while time-to-first-audio stays comfortably inside it —
because a first sentence is a first sentence no matter how long the reply is.

### The thread sweep — why the default was not good enough

Same long reply, same method, varying `PIPER_NUM_THREADS`.

| `intra_op_num_threads` | Whole reply | First sentence |
|---|---:|---:|
| 1 | 1264 ms | 309 ms |
| 4 | 489 ms | 115 ms |
| **8 — the default here** | **378 ms** | **86 ms** |
| 12 | 645 ms | 148 ms |
| 16 | 1274 ms | 260 ms |
| onnxruntime's own default | 814 ms | 152 ms |

The curve is a U, and onnxruntime lands on the wrong side of it — its default behaves
like 12–16 threads and is **2.3× slower than 8**. More threads is not better past the
knee: each of these ONNX operators is small, and past a point the synchronisation costs
more than the parallelism returns.

**The default ships as `min(8, cpu_count)`, not a flat 8.** Eight is a measurement taken
on a 16-core machine, not a property of the model, and hard-coding it would make a
four-core machine oversubscribe. `PIPER_NUM_THREADS=0` hands the choice back to
onnxruntime for anyone who would rather have the library's answer than this one's.

This is the opposite conclusion to m4's, and the difference is worth stating: `asr`
leaves `WHISPER_CPU_THREADS=0` because CTranslate2's own default was already good. The
lesson is not "always set threads" — it is that a library default is a claim to be
measured, and two libraries in the same system gave opposite answers.

---

## Three findings the tables do not say out loud

### 1. Synthesis is not deterministic, and that changes what can be stored

The same sentence twice is not the same audio. Five syntheses of one reply measured
**8011, 8220, 8382, 8382 and 8475 ms** — a 5.5 % spread.

Piper is VITS, whose duration predictor samples from a learned distribution. That
stochasticity is not a defect; it is what stops synthetic prosody sounding metronomic,
and the voice was trained with it on. Turning it off (`noise_w_scale = 0`) would buy
reproducibility at the cost of the thing the voice is for.

The consequences are concrete and belong to m6:

- **A reply must be stored, never re-derived.** `audio_assets` is keyed by sha256 (m4),
  and two syntheses of one sentence hash differently, so text cannot be a cache key.
- **`duration_ms` describes the audio that exists**, not the audio the text implies.
- **There is no golden WAV to diff against.** A regression test for a synthesiser has to
  assert properties — format, length, sentence count — never bytes.
  `test_tts_live.py::test_synthesis_is_not_deterministic_and_that_is_a_property_not_a_bug`
  asserts the variation exists, so that switching the noise off has to be deliberate.

### 2. Streaming buys nothing for a short reply, and that is fine

For a one- or two-sentence reply the whole endpoint is already 64 ms. The streaming
endpoint's advantage is proportional to how much reply comes *after* the first sentence,
which is why `Speech.sentences` is reported: a caller can tell in advance whether
streaming this particular reply is worth the extra machinery.

### 3. The 400 ms budget was never the binding constraint

PRD §9.1's real requirement is a **conversational turn at p95 ≤ 3000 ms**, of which TTS
is 400 ms and the LLM is 1500 ms. m5 spends 320 ms of its 400, or 78 ms if the caller
streams — so it hands m6 roughly 300 ms of slack against a budget m4 already overspent
by 531 ms (decision 0001). That is the arithmetic Q8 needs and it is why this milestone
did not need to reopen it.

---

## Why Piper, concretely

The plan chose Piper and the work here was to check it holds up. It does.

| | Piper | Bark | Coqui XTTS | Chatterbox |
|---|---|---|---|---|
| Size | **61 MB voice, 672 MB image** | ~5 GB | ~2 GB | ~3 GB |
| Speed on CPU | **50× real time** | far slower than real time | ~real time | GPU-bound |
| GPU needed | **no** | effectively yes | effectively yes | yes |
| torch | **no** | yes | yes | yes |

The GPU column is the one that settles it on this machine rather than in the abstract:
Docker Desktop on macOS cannot pass the Apple GPU into a Linux container (D14), so
anything GPU-bound runs on CPU in this stack — the same model, several times slower, for
no benefit. And torch belongs in exactly one image in this system (`pron`, m8, where
forced alignment genuinely needs it).

**Naturalness has not been assessed, and this document does not claim it has.** It can
only be judged by listening, and nothing in this milestone listened — the agent that
wrote the service cannot, and no human has yet. `make tts-sample` writes a WAV to the
gitignored `spike/` for exactly that purpose, and it takes about ten seconds. Until
somebody plays it, "Piper sounds good enough" is a claim inherited from the plan and
PRD §11, not a finding of this milestone. Recorded as **Q10**, and the honest state of
it is *unmeasured*.

What *is* established is that the choice does not depend on that judgement: every
alternative in the table above is disqualified on size, speed or GPU before naturalness
is reached. Kokoro-82M is the upgrade path if voice quality turns out to be the
complaint, and it is a voice swap rather than a rewrite.

---

## Two deviations from the plan, both deliberate

**1. `POST /synthesize/stream` exists and was not in the deliverable list.** Justified by
the "busy machine" table above: without it the service cannot meet its own budget under
ordinary contention, and the fix belongs in the file this milestone wrote rather than in
m6's diff — which the plan's own rationale for m5 says should be about conversation, not
audio plumbing.

**2. `api/routers/tts.py` does not exist.** The plan lists an "internal preview
endpoint"; plan §6 forecasts exactly 30 operations, none of them a TTS route, and lists
`POST /synthesize` under *"Model-service internal APIs, never exposed to the browser"* —
two lines above the deliverable that would have exposed one. No FR asks for it: FR-6 and
FR-7 deliver reply audio as part of a session turn, and it reaches the browser through
the ownership-checked `GET /audio/{asset_id}` that already exists. This is the same
question m4 answered for `POST /audio` (D28) and it gets the same answer. Recorded as
**D31**; it is the resolution of open question **Q9**.

The plan's "voices download at build time into the shared `model_cache` volume" was also
not literally implementable — a volume is not mounted during a build. Resolved by
honouring the *reason* rather than the wording: the default voice is baked into the
image, which removes the cold first turn entirely, and the volume caches any other voice.

---

## How much to trust these numbers

- **The thread finding is solid.** The U-shaped curve reproduced across three separate
  sweeps taken minutes apart under different loads, with the minimum at 8 every time.
- **The absolute milliseconds are machine-specific.** Apple M4 Max, 16 cores, linux/arm64
  containers under Docker Desktop. Treat the *ratios* as the finding and re-measure the
  absolutes anywhere else.
- **These are single-request latencies.** The service serialises inference behind a
  semaphore, so two concurrent syntheses do not overlap. One user at a time is what this
  system is for; a second concurrent speaker would queue.
- **Voice quality is not measured and has not been assessed at all.** It is a listening
  judgement and nobody has made it yet — see Q10. Every number in this document is about
  latency, size and format; none of them is about whether the voice is pleasant.

---

## Revisit when

- **m6 measures a whole turn.** If p95 exceeds 3000 ms, the streaming path is the first
  lever, and it is already built (PRD §9.1 order: stream TTS → drop ASR to `base.en` →
  shorten the reply cap). Q8 is decided there, not here.
- **Voice quality becomes a complaint.** Kokoro-82M, as a voice swap.
- **The stack moves to a machine with a passable GPU.** The whole size/speed table above
  is reasoned from CPU-only inference, which is a property of Docker Desktop on macOS
  rather than of the models.
