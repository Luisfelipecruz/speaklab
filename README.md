# SpeakLab

> Practise spoken English against local models. Scenario role-play, read-aloud
> pronunciation scoring with per-phoneme GOP, and progress you can actually measure.

Every model runs on your machine. Nothing is sent anywhere.

**Status: milestone 8 of 12.** Both practice modes work end to end. Choose a scenario, hold
a button, talk, and a persona answers out loud; or choose a passage, read it aloud, and get
it back with every sound scored against the sound the text asked for — including which
sound came out instead. See [What does not exist yet](#what-does-not-exist-yet), which is
still a real list: progress charts, grammar analysis and the evaluation harness are m9–m11,
and the two things m8 could not finish are named there.

---

## Why this is not another chat-with-an-AI app

Three things are load-bearing, and they are the reason the architecture looks the way it
does.

**Nothing on a trend chart is produced by a language model.** Word timings, pause ratios,
phoneme posteriors and dependency parses are computed by code that returns the same
number for the same audio every time. The LLM writes the sentence that explains a number
to you. It is never the number. Prompt drift must not be able to look like progress.

**No pronunciation claim comes from something that did not hear you.** Pronunciation is
scored by an acoustic model operating on the waveform — forced alignment and Goodness of
Pronunciation, not a language model reading a transcript and guessing. From a transcript,
it would be inventing.

**Breadth and accuracy are measured separately.** You can reach a zero error rate by only
ever using the present simple. So the system tracks *which* verb forms you use alongside
*how correctly*, and treats a narrowing repertoire as a regression even when errors fall.

---

## Quick start

Prerequisites: Docker, and about 3 GB of disk for the images. The first `make up` also
downloads the Whisper weights (~480 MB for `small.en`) onto a shared volume, which takes a
few minutes once. Nothing waits for it: the API has no `depends_on` for the recogniser, so
the rest of the stack is usable immediately and `/health` reports `asr` as loading.

```bash
cp .env.example .env
make up
make migrate
make seed
```

`make seed` is idempotent — it keys on slug, and the second run reports
`0 inserted, 0 updated`. Running it after a `git pull` is how a content change reaches
your database.

The API signs sessions with a built-in development key until you set `JWT_SECRET`, and
says so in its startup log every time. That is fine on a laptop and nowhere else.

Then:

| | |
|---|---|
| App | <http://localhost:3003> |
| Sign up | <http://localhost:3003/register> |
| **Choose a scenario and talk** | <http://localhost:3003/scenarios> |
| Your conversations | <http://localhost:3003/sessions> |
| API docs | <http://localhost:8002/docs> |
| Health | `make health` |
| API tests | `make test` |
| Frontend tests | `make test-frontend` |
| Word error rate | `make asr-wer` |
| Synthesis latency | `make tts-latency` |
| Hear the voice | `make tts-sample` |
| Everything else | `make help` |

Open the app at **`localhost`**, not at a LAN address. Browsers only grant microphone
access on a secure origin, and `http://192.168.x.x:3003` is not one — the app detects this
and says so rather than rendering a record button that cannot work, but the fix is the URL.

`make up` starts **five** containers as of m5: postgres, api, frontend, `asr` and `tts` —
the whole conversational stack. It does not start `pron`, which keeps its profile
permanently so that nobody downloads 1.78 GB of torch to try a conversation. **`/health`
reporting `degraded` is the system working correctly**: it means `asr` and `tts` are up
and pronunciation scoring is switched off. Read-aloud still works in that state — a
reading comes back with its transcript and its word error rate, and says in words that
the phone scores are missing and how to get them (PRD R6).

For pronunciation scoring, `make pron-up` — 1.78 GB of image and 1.2 GB of weights,
measured at 109 s to first readiness including the download. Readings taken while it was
off can be scored afterwards without being read again (`FR-16`).

The first `make up` builds the two model images and downloads Whisper's weights, which
takes a few minutes once. The Piper voice is inside its image already, so the first
thing the system says out loud does not wait for a download.

---

## Architecture

```mermaid
graph LR
    subgraph Browser
        FE["Next.js 15<br/>:3003"]
    end
    subgraph "Docker Compose"
        API["FastAPI<br/>:8002<br/><i>no model weights</i>"]
        DB[("PostgreSQL 16<br/>:5433")]
        ASR["asr — faster-whisper<br/>:8101 · m4"]
        TTS["tts — Piper<br/>:8102 · m5"]
        PRON["pron — wav2vec2 + torch<br/>:8103 · m8"]
    end
    OLLAMA["Ollama<br/>host :11434"]

    FE -- "audio" --> API
    API --> DB
    API -- "transcribe" --> ASR
    API -- "synthesise" --> TTS
    API -. "profile: pron" .-> PRON
    API -- "persona reply" --> OLLAMA

    style FE fill:#3b82f6,color:#fff
    style API fill:#10b981,color:#fff
    style DB fill:#f59e0b,color:#fff
    style PRON fill:#ef4444,color:#fff
```

FastAPI is the only orchestrator. It normalises audio to 16 kHz mono PCM, calls `asr`
for a transcript with word timestamps and logprobs, computes the deterministic fluency
and grammar metrics in-process, calls Ollama for the persona's reply and `tts` for its
audio. Read-aloud takes a second path: the transcript plus a canonical phoneme sequence
from G2P go to `pron`, which force-aligns and returns per-phone GOP.

Three separate model services rather than one, and none of them inside the API image:

| | Runtime | Why separate |
|---|---|---|
| `asr` | faster-whisper on CTranslate2 | No torch. 746 MB image. Torch is not allowed in the request path |
| `tts` | Piper on onnxruntime | No torch either. 672 MB image around a 61 MB voice, 50× real time on CPU |
| `pron` | wav2vec2 + torch | **1.78 GB**. Its own profile, so the stack is usable by someone who never downloads it. torch comes from PyTorch's CPU index — from PyPI it was 8.51 GB, because those wheels pull the NVIDIA stack on arm64 too |

Ollama runs on the **host**, not in Compose. Docker Desktop on macOS cannot pass the
Apple GPU into a Linux container, so a containerised Ollama runs CPU-only while the
host's uses Metal — the same model, several times slower, for no benefit. The `ollama`
service is declared under `profiles: ["llm"]` for a Linux host with a GPU, and for CI.

---

## Measured

Counted against the running system on 2026-08-30, not recalled. Anything not listed here
has not been measured yet and is not claimed.

| | |
|---|---|
| Containers up and healthy | 6 of 6 with `pron` started; 5 of 5 without it |
| API test suite | **319** — 300 pass with no model services running; the other 19 need `asr`, `tts`, `pron` or Ollama |
| Frontend test suite | **93** across 13 suites, Jest and React Testing Library, no services needed |
| API image | 424 MB, with no torch — asserted by a test, not by a comment |
| `asr` image | 746 MB, also no torch. CTranslate2 and ONNX Runtime, not PyTorch |
| `tts` image | 672 MB, no torch. onnxruntime and a 61 MB voice baked in |
| API operations implemented | 22 of the 30 forecast — m8 added the four `/attempts` routes |
| **Word error rate, `small.en`** | **1.72 %** on ten LibriSpeech utterances, 232 reference words |
| **ASR latency, ~6 s of audio** | **1231 ms** against a 700 ms budget — **missed, deliberately** |
| **TTS latency, ~80-token reply** | **320 ms** whole against a 400 ms budget — **78 ms** to the first sentence |
| TTS throughput | 50× real time on CPU |
| **A whole spoken turn, p95 over 20** | **2684 ms** against a 3000 ms budget — **met**, at load 1.7–5.0 |
| Turn stages, median | ASR 1146 ms · generation 872 ms · synthesis tail 235 ms |
| The same turn on a busy machine | 7283 ms p95 at load 10–16 — 2.7× on identical code |
| `pron` image | **1.78 GB**. The only image with torch in it, and the reason it is profiled |
| **GOP separation, 10 planted errors** | **9 detected**, mean drop **8.138 nats**, competing phone named correctly **10 of 10** — reproducing m0 exactly through the live service |
| Clean-speech GOP baseline | mean −0.386, **median exactly 0.000** over 35 correctly produced phones |
| **Scoring a 79-word reading** | **8.1 s** end to end for 250 phones, against a 10 000 ms budget — **met, with 1.9 s of margin** |
| Alignment over the shipped corpus | 12 of 12 passages, **3091 phones, 0 desyncs** |
| Streaming synthesis, against its own control | 235 ms of synthesis left to wait for, against 375 ms in series |
| Token estimator error vs Ollama's own count | −6.4 % to +6.2 % across three prompt shapes |
| `GET /scenarios`, warm | 3.5 ms median |
| `GET /health`, warm | 32 ms median — up from 21 ms at m4, because a second model probe now answers rather than failing DNS fast |
| `POST /auth/register` | 61 ms median — one Argon2id hash at 64 MiB |
| Wrong password vs. unknown email | 75.6 vs 78.1 ms — the login endpoint does not reveal who has an account |

The ASR **stage** budget is missed and the model was not swapped to hide it. `base.en`
meets it today at 525 ms and costs 2.6× the word error rate, which is the input to every
metric downstream; the whole argument is in
[docs/decisions/0001-asr-model-choice.md](docs/decisions/0001-asr-model-choice.md). **m6
settled it: the stage misses and the turn passes**, so nothing is downgraded.
The word error rate is a **floor**: LibriSpeech is native, fluent, read-aloud English, and
learner speech will be worse by an amount that set cannot estimate.

The TTS budget *is* met, and the interesting part is what it took. onnxruntime's own
thread default is 2.3× slower than eight threads here, which alone was the difference
between 814 ms and 378 ms — so the number above is a measurement, not a library's
opinion. On a machine also running an iOS simulator the whole-reply call misses at
771 ms while first-sentence streaming holds at 135 ms, which is why both endpoints exist:
[docs/decisions/0002-tts-model-choice.md](docs/decisions/0002-tts-model-choice.md).

**The turn meets its budget and the margin is 316 ms, which is not much.** The one stage
that misses is ASR — 1146 ms against a 700 ms stage budget — and the turn absorbs it
because generation and synthesis both come in under. That is exactly the bet m4 made when
it declined to downgrade the recogniser to buy 620 ms at 2.6× the word error rate, and the
turn-level measurement it asked for now exists and says the bet was right.

The same twenty turns measured **7283 ms at p95** while the machine was also running a
second Docker VM, an Android emulator and two other Compose stacks — 2.7× on identical
code. Both numbers are in the table because the range is what a developer actually meets,
and because for several hours the contended one was the only measurement available and it
said the opposite thing.

PRD §9.1's first prescribed fallback — streaming the reply into the voice sentence by
sentence — is worth about **140 ms** here, measured against its own control on a quiet
machine: 235 ms of synthesis still to wait for, against 375 ms in series. That is a
twentieth of a turn, and smaller than this project assumed when it built the streaming
endpoint at m5. It stays on because it costs nothing and because it shortens the turn,
which is what the p95 budget is measured against.

**It does not pay off in the browser, and an earlier version of this paragraph said it
would.** m7 found the reason: the turn endpoint concatenates the synthesised sentences
into one WAV and returns one URL after the whole turn has completed, so the first sound a
user hears arrives at *turn* latency and m5's 78 ms describes a boundary inside the API
that nothing downstream can observe. Collecting the rest needs a streaming endpoint and
giving up the atomic turn — which is the property that makes a failed turn a retry of the
same bytes. Not scheduled:
[docs/decisions/0004-browser-recording-and-playback.md](docs/decisions/0004-browser-recording-and-playback.md) §3.

The most expensive thing m6 learned is not a latency at all. **Ollama does not refuse a
prompt that will not fit** — llama.cpp shifts the context, discards half of it, and answers
200 with nothing in the response to say so. A 4200-token prompt under `num_ctx: 4096` came
back having evaluated 2051. The half it drops is the front, which is where a system message
lives, so the persona disappears from exactly the long conversations that were the reason
to have a persona. `num_ctx` is now stated on every request and the prompt is sized before
it is sent, with a measured margin for the estimator being wrong.

Latencies are medians over 12 calls on a laptop running several other stacks, and they
move by a factor of two or more with what else is busy. At m1 the same `/health` measured
13–20 ms. Treat them as orders of magnitude, not benchmarks; the ones worth reading are
the *ratios* — the register/login pair above is a claim about the code, and it holds
whatever the machine is doing.

### Pronunciation scoring (m0 spike, m8 in production)

Pronunciation is the risky part of this product, so it was proved before anything was
built around it. On real human speech, GOP at a phone the speaker did not produce fell by
a mean of **8.14 nats** (Cohen's *d* = 8.26) against a threshold set at the 5th percentile
of correctly-produced GOP. **9 of 10** planted errors were detected and the competing phone
was named correctly in **10 of 10**.

**m8 re-ran that experiment through the production service and got the same numbers to
three decimal places** — 9 of 10, mean drop 8.138, threshold −3.119, named 10 of 10 —
through an entirely rewritten code path, in a container instead of on the host. `make
pron-golden` is the command; [decision 0005](docs/decisions/0005-gop-pipeline.md) is the
writeup, and it promotes the spike's findings along with the four things m8 changed and
why.

The one thing that did not carry over is the *cost*. m0 measured 99.5 ms per attempt on
3.4 s of audio, on the host with 8 torch threads. In its container the same work takes
819 ms, and a real 34-second reading takes **8.1 s against a 10-second budget**. The method
is not the expense; the CPU allocation is.

---

## What does not exist yet

Named explicitly so nothing here reads as a claim.

| Milestone | Not yet built |
|---|---|
| m3 | Password reset, email verification, login rate limiting — accounts themselves work |
| m4 | Uploading a recording. Speech recognition works and is measured; audio enters the system attached to a turn (m6) or an attempt (m8), so there is no upload endpoint yet |
| m5 | A way for the *browser* to ask for speech. The `tts` service works and is measured, but synthesis is an internal call — the persona's audio reaches the browser attached to a turn (m6), through `GET /audio/{id}` |
| m7 | **A recording has never been through this UI** — no headless browser has a microphone. The recorder's states and failures are covered by unit tests; the gesture itself needs a person, in Chrome and in Safari |
| m7 | Time-to-first-audio. The turn returns one concatenated WAV, so the first sound arrives at whole-turn latency — streaming it sentence by sentence to the browser needs an endpoint that does not exist, and giving up the atomic turn. See [decision 0004 §3](docs/decisions/0004-browser-recording-and-playback.md) |
| m8 | **The golden pairs.** Criterion S4 — that deliberately broken readings score measurably worse than clean ones — is not met, and cannot be met by what exists: perturbing the reference proves the arithmetic, not that a *learner* error is detected. The test is written and skips. It needs five minutes of a person's voice ([`spike/RECORD.md`](spike/RECORD.md)) |
| m8 | **A calibrated GOP threshold.** m0 settled the method — a percentile of the correct-speech distribution, per phone — and not the numbers, so `PRON_GOP_THRESHOLDS` is empty and the heatmap says its bands are relative to the reading rather than a pass mark. See [decision 0005 §7](docs/decisions/0005-gop-pipeline.md) |
| m9 | Error taxonomy and grammar analysis |
| m10 | Progress charts and recommendations |
| m11 | The evaluation harness |
| m12 | Documentation and a demo |

---

## Repository

```
api/            FastAPI. No model weights, no torch.
  db_models/    SQLAlchemy — the write path, twelve tables
  models/       Pydantic — the wire shapes
  routers/      One module per resource
  services/     Logic that is neither a route nor a row (hashing, tokens, ASR, TTS, audio, WER)
  dependencies.py  current_user, and the ownership guard
  alembic/      One revision per milestone that changes schema
  seeds/        The 8 scenarios and 12 passages, as JSON
frontend/       Next.js 15, React 19, shadcn/ui
  src/app/      Routes. (auth) is a group; scenarios/ and sessions/ are the application
  src/components/  The conversation UI, plus the shadcn primitives under ui/
  src/hooks/    useAuth (a provider), useRecorder (the microphone), useSession
  src/lib/      api.ts is the wire shapes and the browser client; server-api.ts forwards
                the cookie from a server component. Tests sit beside what they test
infra/          One directory per image — api, frontend, asr, tts
eval/golden/    Evaluation fixtures. Committed, with a manifest of their hashes
docs/           Architecture, data model, decisions, changelog
speaklab-agent/ The twelve-milestone implementation plan
spike/          m0, throwaway, gitignored
```

The schema is documented in [docs/data-model.md](docs/data-model.md) — what each table
holds, why five columns are JSONB and two adjacent ones are not, and what the seed
contract is.

`PRD.md` holds the product requirements and the measurement model.
`speaklab-agent/IMPLEMENTATION-PLAN.md` holds the twelve milestones, the schema and the
API surface — including the ones not built yet, with what each is expected to prove.

## Licence

MIT. See [LICENSE](LICENSE).
