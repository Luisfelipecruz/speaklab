# SpeakLab

> Practise spoken English against local models. Scenario role-play, read-aloud
> pronunciation scoring with per-phoneme GOP, and progress you can actually measure.

Every model runs on your machine. Nothing is sent anywhere.

**Status: milestone 1 of 12 — the scaffold.** `docker compose up -d` brings up a healthy
three-container stack and a page that reports what is running. The conversation loop
arrives in m6 and pronunciation scoring in m8; see [What does not exist yet](#what-does-not-exist-yet),
which is most of it.

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
| API docs | <http://localhost:8002/docs> |
| Sign up | <http://localhost:3003/register> |
| Scenarios | <http://localhost:8002/scenarios> |
| Passages | <http://localhost:8002/passages> |
| Health | `make health` |
| Tests | `make test` |
| Word error rate | `make asr-wer` |
| Synthesis latency | `make tts-latency` |
| Hear the voice | `make tts-sample` |
| Everything else | `make help` |

`make up` starts **five** containers as of m5: postgres, api, frontend, `asr` and `tts` —
the whole conversational stack. It does not start `pron`, which keeps its profile
permanently so that nobody downloads two gigabytes of torch to try a conversation.
`/health` reporting `degraded` today is the system working correctly: it means `asr` and
`tts` are up and the pronunciation service is not built yet.

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
| `pron` | wav2vec2 + torch | ~2 GB. Its own profile, so the stack is usable by someone who never downloads it |

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
| Containers up and healthy | 5 of 5 |
| Test suite | **177** — 161 pass with no model services running, all 177 with `asr` and `tts` up |
| API image | 424 MB, with no torch — asserted by a test, not by a comment |
| `asr` image | 746 MB, also no torch. CTranslate2 and ONNX Runtime, not PyTorch |
| `tts` image | 672 MB, no torch. onnxruntime and a 61 MB voice baked in |
| API operations implemented | 12 of the 30 forecast — m5 added none, deliberately |
| **Word error rate, `small.en`** | **1.72 %** on ten LibriSpeech utterances, 232 reference words |
| **ASR latency, ~6 s of audio** | **1231 ms** against a 700 ms budget — **missed, deliberately** |
| **TTS latency, ~80-token reply** | **320 ms** whole against a 400 ms budget — **78 ms** to the first sentence |
| TTS throughput | 50× real time on CPU |
| `GET /scenarios`, warm | 3.5 ms median |
| `GET /health`, warm | 32 ms median — up from 21 ms at m4, because a second model probe now answers rather than failing DNS fast |
| `POST /auth/register` | 61 ms median — one Argon2id hash at 64 MiB |
| Wrong password vs. unknown email | 75.6 vs 78.1 ms — the login endpoint does not reveal who has an account |

The ASR budget is missed and the model was not swapped to hide it. `base.en` meets it
today at 525 ms and costs 2.6× the word error rate, which is the input to every metric
downstream; the fallback is one environment variable and the whole argument is in
[docs/decisions/0001-asr-model-choice.md](docs/decisions/0001-asr-model-choice.md).
The word error rate is a **floor**: LibriSpeech is native, fluent, read-aloud English, and
learner speech will be worse by an amount that set cannot estimate.

The TTS budget *is* met, and the interesting part is what it took. onnxruntime's own
thread default is 2.3× slower than eight threads here, which alone was the difference
between 814 ms and 378 ms — so the number above is a measurement, not a library's
opinion. On a machine also running an iOS simulator the whole-reply call misses at
771 ms while first-sentence streaming holds at 135 ms, which is why both endpoints exist:
[docs/decisions/0002-tts-model-choice.md](docs/decisions/0002-tts-model-choice.md).

Latencies are medians over 12 calls on a laptop running several other stacks, and they
move by a factor of two or more with what else is busy. At m1 the same `/health` measured
13–20 ms. Treat them as orders of magnitude, not benchmarks; the ones worth reading are
the *ratios* — the register/login pair above is a claim about the code, and it holds
whatever the machine is doing.

### The pronunciation spike (m0)

Pronunciation scoring is the risky part of this product, so it was proved before anything
was built around it. On real human speech, GOP at a phone the speaker did not produce
fell by a mean of **8.14 nats** (Cohen's *d* = 8.26) against a threshold set at the 5th
percentile of correctly-produced GOP. **9 of 10** planted errors were detected and the
competing phone was named correctly in **10 of 10**. Cost: **99.5 ms** per attempt
against a 10-second budget.

The full writeup, including the failed first attempt and why it failed, is
`spike/gop-feasibility.md`. That directory is deliberately not committed; its findings
move into `docs/decisions/` at m8.

---

## What does not exist yet

Named explicitly so nothing here reads as a claim.

| Milestone | Not yet built |
|---|---|
| m3 | Password reset, email verification, login rate limiting — accounts themselves work |
| m4 | Uploading a recording. Speech recognition works and is measured; audio enters the system attached to a turn (m6) or an attempt (m8), so there is no upload endpoint yet |
| m5 | A way for the *browser* to ask for speech. The `tts` service works and is measured, but synthesis is an internal call — the persona's audio reaches the browser attached to a turn (m6), through `GET /audio/{id}` |
| m6 / m7 | The conversation loop, and a UI for it |
| m8 | Read-aloud and per-phoneme scoring — the spike passed, the service is not written |
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
