# 0002 — Piper, and the thread count that decides whether the budget is met

Status: accepted

---

## Decision

**Piper 1.7 (`piper-tts` on onnxruntime), voice `en_US-lessac-medium`, at eight
intra-op threads, emitting WAV.** The voice is baked into the image at build time. The
service exposes a whole-reply endpoint *and* a per-sentence streaming endpoint, because
the measurement below is that the first one alone cannot meet PRD §9.1's 400 ms budget
on a full-length reply on a machine doing anything else.

Two of those choices carry the finding:

- **`intra_op_num_threads = 8`, set by hand.** onnxruntime's own default is **2.3×
  slower** on this machine. Leaving it to the library is the difference between missing
  the budget and meeting it, and nothing about the code would show that.
- **A streaming endpoint alongside the whole-reply one.** PRD §9.1's first prescribed
  fallback is *"stream the LLM reply into TTS sentence by sentence"*. Piper already
  produces audio one sentence at a time; exposing that is fifteen lines in the service,
  and it drops time-to-first-audio from 320 ms to **78 ms**, flat in the length of the
  reply.

---

## What was measured

Three replies of the length the product actually produces. PRD §9.1 budgets the persona
reply at ~80 output tokens, which is the "long" row — the one that matters, and the one
a 30-word test would miss.

Latency is the **minimum of 7 timed runs after 3 warm-ups**, end to end over HTTP
including WAV assembly. Minimum rather than median, and the machine's load average is
printed beside every table, because on a shared machine the median measures the other
work rather than the service ([0001](0001-asr-model-choice.md)).

### The configuration that ships — the live compose service, load average 8.7

Minimum of **11** runs after 3 warm-ups, against `docker compose up`'s own `tts`.

| Reply | Sentences | Audio | Whole reply | **First sentence** | All sentences | RTF |
|---|---:|---:|---:|---:|---:|---:|
| short, 11 words | 2 | 2.69 s | 65 ms | **33 ms** | 79 ms | 0.024 |
| typical, 32 words | 2 | 8.38 s | 171 ms | **93 ms** | 166 ms | 0.020 |
| **long, 61 words (~80 tokens)** | 4 | 15.84 s | **320 ms** | **78 ms** | 332 ms | 0.020 |

Every row is inside the 400 ms budget, and synthesis runs at roughly **50× real time**.

An independent min-of-7 run, at load average 4.9 and against a standalone container built
from the same image, gives **339 ms / 94 ms** on the long reply. Two runs under different
loads agreeing to within 6 % is the reason these numbers are quoted at all.

### The same service on a busy machine — load average 22–28

Sixteen cores shared with an iOS simulator, a UI-test runner, `xcodebuild` and an Android
emulator. This is not a pathological case; it is a laptop with other work on it.

| Reply | Whole reply | **First sentence** |
|---|---:|---:|
| short, 11 words | 132 ms | **52 ms** |
| typical, 32 words | 373 ms | **205 ms** |
| **long, 61 words** | **771 ms — misses** | **135 ms — meets** |

This is the row that decides the streaming endpoint. Under contention the whole-reply
call misses the budget by 1.9×, while time-to-first-audio stays comfortably inside it —
because a first sentence is a first sentence no matter how long the reply is.

### The thread sweep — why the default is not good enough

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

The recogniser reaches the opposite conclusion: `asr` leaves `WHISPER_CPU_THREADS=0`
because CTranslate2's own default is already good. The lesson is not "always set
threads" — it is that a library default is a claim to be measured, and two libraries in
the same system give opposite answers.

---

## Three findings the tables do not say out loud

### 1. Synthesis is not deterministic, and that changes what can be stored

The same sentence twice is not the same audio. Five syntheses of one reply measured
**8011, 8220, 8382, 8382 and 8475 ms** — a 5.5 % spread.

Piper is VITS, whose duration predictor samples from a learned distribution. That
stochasticity is not a defect; it is what stops synthetic prosody sounding metronomic,
and the voice was trained with it on. Turning it off (`noise_w_scale = 0`) would buy
reproducibility at the cost of the thing the voice is for.

The consequences are concrete:

- **A reply must be stored, never re-derived.** `audio_assets` is keyed by sha256, and
  two syntheses of one sentence hash differently, so text cannot be a cache key.
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

### 3. The 400 ms budget is not the binding constraint

PRD §9.1's real requirement is a **conversational turn at p95 ≤ 3000 ms**, of which TTS
is 400 ms and the LLM is 1500 ms. Synthesis spends 320 ms of its 400, or 78 ms if the
caller streams — roughly 300 ms of slack against a budget the recogniser overspends by
531 ms ([0001](0001-asr-model-choice.md)). [0003](0003-conversation-context-strategy.md)
measures the whole turn, and it meets its budget.

---

## Why Piper, concretely

| | Piper | Bark | Coqui XTTS | Chatterbox |
|---|---|---|---|---|
| Size | **61 MB voice, 672 MB image** | ~5 GB | ~2 GB | ~3 GB |
| Speed on CPU | **50× real time** | far slower than real time | ~real time | GPU-bound |
| GPU needed | **no** | effectively yes | effectively yes | yes |
| torch | **no** | yes | yes | yes |

The GPU column is the one that settles it on this machine rather than in the abstract:
Docker Desktop on macOS cannot pass the Apple GPU into a Linux container, so anything
GPU-bound runs on CPU in this stack — the same model, several times slower, for no
benefit. And torch belongs in exactly one image in this system (`pron`, where forced
alignment genuinely needs it).

**Naturalness is not assessed, and this record does not claim it is.** It can only be
judged by listening; `make tts-sample` writes a WAV to listen to, in about ten seconds.
"Piper sounds good enough" is a claim from PRD §11, not a finding of this record.

What *is* established is that the choice does not depend on that judgement: every
alternative in the table above is disqualified on size, speed or GPU before naturalness
is reached. Kokoro-82M is the upgrade path if voice quality turns out to be the
complaint, and it is a voice swap rather than a rewrite.

---

## Two deliberate choices

**1. `POST /synthesize/stream` exists.** Justified by the "busy machine" table above:
without it the service cannot meet its own budget under ordinary contention, and the fix
belongs in the voice service rather than in the conversation code.

**2. There is no TTS route in the API.** `POST /synthesize` is a model-service internal
API, never exposed to the browser. No FR asks for one: FR-6 and FR-7 deliver reply audio
as part of a session turn, and it reaches the browser through the ownership-checked
`GET /audio/{asset_id}` — the same answer, for the same reason, as there being no upload
endpoint for audio.

The default voice is baked into the image — a volume is not mounted during a build —
which removes the cold first turn entirely; the shared `model_cache` volume caches any
other voice.

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
- **Voice quality is not measured.** Every number in this record is about latency, size
  and format; none of them is about whether the voice is pleasant.

---

## Revisit when

- **A whole turn misses its budget.** The streaming path is the first lever, and it is
  built (PRD §9.1 order: stream TTS → drop ASR to `base.en` → shorten the reply cap).
- **Voice quality becomes a complaint.** Kokoro-82M, as a voice swap.
- **The stack moves to a machine with a passable GPU.** The whole size/speed table above
  is reasoned from CPU-only inference, which is a property of Docker Desktop on macOS
  rather than of the models.
