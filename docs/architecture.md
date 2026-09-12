# Architecture

What SpeakLab is made of, and why each piece is where it is. What each part counts and
refuses to say is in [how-it-works.md](how-it-works.md); every figure quoted here, with its
source, is in [measurements.md](measurements.md).

---

## 1. The shape

One orchestrator, one database, three model services, and one language model on the host.

```
browser ──▶ Next.js :3003 ──▶ FastAPI :8002 ──▶ Postgres :5433
                                    │
                                    ├──▶ asr  :8101    faster-whisper
                                    ├──▶ tts  :8102    Piper
                                    ├──▶ pron :8103    wav2vec2 + torch
                                    └──▶ Ollama :11434 on the host
```

FastAPI is the only orchestrator. There is no message queue, no service mesh and no agent
framework: the request path is a handful of HTTP calls and a token budget, and a framework
would hide the token budget — the part actually worth reviewing.

### Three model services instead of one

They have different weights, different runtimes and different costs, and folding them
together would make the cheapest pay for the most expensive.

| Service | Runtime | Size | Starts |
|---|---|---|---|
| `asr` | faster-whisper on CTranslate2 | 790 MB image, no torch; 464 MB of Whisper weights on first start | by default |
| `tts` | Piper on onnxruntime | 722 MB image, no torch, its 61 MB voice inside | by default |
| `pron` | wav2vec2 + torch | 1.84 GB image, and 1.2 GB of weights | with `make pron-up` |

`pron` has a profile of its own so that someone who wants to try a conversation never
downloads torch.

**The API image contains no model weights and no torch.** It is 826 MB, about half of it
the dependency parser and its model, and `api/tests/test_health.py` asserts the absence of
torch, transformers, faster-whisper and piper rather than trusting a comment. Dependencies
acquire dependencies; that test turns "the image grew by two gigabytes" into a red test in
CI.

### Ollama runs on the host

Docker Desktop on macOS cannot pass the Apple GPU into a Linux container, so a
containerised Ollama runs on the CPU while the host's uses Metal — the same model, several
times slower. `OLLAMA_BASE_URL` defaults to `http://host.docker.internal:11434`, and the
`api` service declares `extra_hosts: ["host.docker.internal:host-gateway"]` so that the
default works on Linux too. For a Linux host with a GPU, or a machine with no Ollama at all,
an `ollama` service is declared under the `llm` profile; `make llm-up` starts it.

---

## 2. Compose profiles

| Profile | Services | Started by |
|---|---|---|
| *(default)* | `postgres`, `api`, `frontend`, `asr`, `tts`, and the `volume-owner` job | `make setup`, `make up` |
| `pron` | `pron` | `make pron-up` |
| `llm` | `ollama` | `make llm-up` |
| `tools` | `test` | `make test` and the measurement targets |

A profiled service is left out of both `up` and `build`, so the default stack never builds
or downloads what it does not run.

### What every image does the same way

- **An unprivileged account.** The four Python images run as `speaklab`, uid 10001, the
  same id in each, because `asr`, `tts` and `pron` share the model cache and `api` owns
  the recordings; the frontend runs as the Node image's own `node`. `volume-owner` runs
  before them, hands any file on the two named volumes that someone else owns to uid
  10001, and exits — a volume first written by an image that ran as root would otherwise
  hold files the services cannot replace.
- **The security fixes the distribution has published since the base image was built**,
  applied at build time, on a base pinned to its exact release (`python:3.12.14-slim`,
  `node:24.21.0-alpine`, `postgres:16.15`). Dependabot proposes each new release as a
  change to that line.
- **Its own health check**, in the Dockerfile: a line of Python for the four Python
  images, busybox `wget` for the frontend. No image installs a package to answer one.
- **Only what it runs.** The API's test and lint tools are in a separate `test` stage;
  the frontend image carries pnpm, and not npm or corepack.

---

## 3. Health: a dependency and a feature are different things

The database is a dependency; the model services are not. Getting that backwards is the
easiest way to make the stack unstartable.

```
GET /health         200 while any model service is missing; 503 only if Postgres is gone
GET /health/models  always 200 — a monitoring endpoint, not a liveness one
```

If `/health` answered 503 because `pron` was down, the container healthcheck would fail,
`depends_on: service_healthy` with it, and the frontend would refuse to start over a
service most people never run. Instead the API reports `degraded`, names each service, and
keeps serving everything that is not speech.

The four probes — `asr`, `tts`, `pron` and the conversation model, reported as `llm` — run
concurrently under one timeout (`HEALTH_PROBE_TIMEOUT_S`, 1.5 s by default), so a dead
model layer costs that timeout once. `/health` is what the container healthcheck calls
every ten seconds, and a liveness probe that can hang is worse than none.

The status vocabulary is closed, so the frontend can switch on it:

| | |
|---|---|
| `ok` | reachable, answering 2xx |
| `unreachable` | no answer — not started, not built, DNS failure, or timed out |
| `error` | answered, but not with a 2xx. Up and unwell is a different problem from absent |

A service's own answer is passed through under `reports`. The model services answer 200
with `model_loaded: false` while their weights download — a cold start is minutes and must
not read as a crash — so *reachable* and *ready* are reported as two facts.

---

## 4. Data and accounts

Plain PostgreSQL 16, pulled, not built. No PostGIS — nothing here is spatial — and no
pgvector — nothing here is a retrieval problem. An unused extension is a claim about the
system that is not true.

Alembic owns the schema, and there is no `docker-entrypoint-initdb.d` script: an `init.sql`
that also created tables would be a second source of truth that runs once, on an empty
volume, and diverges after that. Fourteen tables, four enum types, seven revisions.
`api/db_models/` holds the columns and `api/models/` the wire shapes, because they answer
different questions — `scenarios.persona_prompt` is loaded on every query and serialised by
nothing. The tables, and why five columns are JSONB while two adjacent ones are not, are in
[data-model.md](data-model.md).

Two database URLs, derived from one so they cannot drift: `DATABASE_URL` with `+asyncpg`
for requests, and `SYNC_DATABASE_URL` for Alembic, which runs synchronously and cannot parse
the async dialect.

Scenarios, passages and answer prompts are **seeded data, not fixtures**: real rows
versioned as JSON in `api/seeds/` and loaded idempotently by slug with `make seed`. They sit
under `api/` so that one path resolves the same in the container, in CI and in a host shell.

Audio lives in a named volume, never in the working tree; `.gitignore` excludes `*.wav`,
`*.webm`, `*.mp3` and `audio_data/`. The golden evaluation sets are the exception — among
them ten LibriSpeech utterances in `eval/golden/asr/`, 1.5 MB of FLAC, committed so that a
number measured in CI and one measured on a laptop mean the same thing.

**Accounts.** Passwords are Argon2id with the library's defaults, so raising the cost is a
library upgrade rather than a migration: the parameters travel inside each hash, and a
successful login re-hashes an older one. The session is a JWT in an **httpOnly** cookie.
The frontend cannot read the token — so it cannot attach it to a header, store it, or leak
it through an XSS payload — and cannot delete it either, which is why there is
`POST /auth/logout`. Every browser call carries `credentials: "include"`; without it the
cookie is dropped cross-origin, and a login appears to succeed while every request after it
answers 401.

**Access control** is one dependency and one helper in `api/dependencies.py`, enforced by
reading the router table: `tests/test_ownership.py` asserts that every route either depends
on `current_user` or appears in an explicit table of public paths with a written reason — a
claim about every endpoint, including ones nobody has written yet. Another account's rows
answer **404, not 403**: a 403 confirms the row exists, which turns an incrementing id into
an enumeration of the table.

**Export.** `GET /progress/export` returns everything an account holds as one JSON
document, sent as a download: sessions with their turns and what was measured and corrected
in each, readings with their scored sounds, spoken answers and the weekly snapshots, with
each recording listed by the address that streams it rather than embedded. It takes no user
id, so no request can export somebody else's.

---

## 5. Audio in: what the recogniser is for

Every fluency figure in the product is arithmetic on word timings, and every accuracy
figure is gated on word confidence; nothing else in the system produces either. So `asr`
returns `{w, start_ms, end_ms, logprob}` for every word, and that shape appears in three
places: the service emits it, `api/models/audio.py` types it, and the `turns.words` column
stores it. The typed middle copy is the authority — the client parses into it, so a field
the service renames fails at the boundary instead of becoming a fluency figure of zero.

**Decoding happens in the service, not in the API.** Chrome sends Opus in WebM and Safari
AAC in MP4, and the API holds no media library. PyAV — the ffmpeg libraries in-process —
resamples everything to 16 kHz mono inside `asr`, and `audio_assets.format`,
`.sample_rate` and `.duration_ms` are what the decoder reported: the duration comes from
the decoded sample count, not the container header, because a truncated upload declares
the duration the recorder intended.

The service promises `0 <= start <= end <= duration` and **counts the timings it had to
repair** to keep that promise, rather than repairing them silently: a `timestamp_fixups`
count that climbs is a fact about the model.

**The recogniser misses its own latency budget, on purpose.** `small.en` takes 1231 ms on
about six seconds of audio against a 700 ms stage budget, at 1.72 % word error. `base.en`
meets the budget at 525 ms and costs 4.31 %, and that error rate is the input to the
grammar analysis, the fluency figures and read-aloud. The whole turn meets its 3 s budget
with `small.en` (§7), so the recogniser is not downgraded; switching is one environment
variable. [decisions/0001](decisions/0001-asr-model-choice.md) has the argument, and a case
where `base.en` at beam 5 invents a word and takes 4.5 s.

### Storing a recording

Content-addressed: the file name is the sha256 of the bytes, and `audio_assets` is unique on
`(user_id, sha256)`, so a double-tapped send or a retry after a timeout is one row. Scoped
to the user, not global: two people reading the same passage are two recordings, and a
shared row would be a deletion request that cannot be honoured.

The insert runs inside a **savepoint**, because it is called inside a larger transaction
that also writes a turn, and a plain rollback on the duplicate path would discard that turn.

Nothing from a request reaches the filesystem. The stored name is a digest the API
computed, and `resolve_path` checks containment after `resolve()` anyway, because a prefix
comparison passes a symlink that points out of the volume.

**With audio retention off** (`users.retain_audio`), a turn is transcribed and the
recording is not kept: no file and no `audio_assets` row, while the turn still carries the
transcript, the word timings and the confidence that every later figure is computed from.
The persona's audio is stored either way; it is synthesised, not the speaker's voice.
Read-aloud refuses with a 409 that names the setting, because a reading that cannot be
rescored would break what its schema promises.

---

## 6. Speech out: two ways to ask for it

`tts` is Piper on onnxruntime — no torch, and no `espeak-ng` package, because `piper-tts`
carries the phonemiser as a compiled extension — with a 61 MB voice **baked into the
image**. It is the one place the system puts weights in an image rather than on the shared
volume: 61 MB fits in a cached layer, and it removes the cold first turn. Another voice is
downloaded into `model_cache` and survives rebuilds there.

**Two endpoints, because one of them cannot always meet the budget.** `POST /synthesize`
returns a whole reply as one WAV: 320 ms for an 80-token reply on a quiet machine against a
400 ms budget, and 771 ms on a busy one. `POST /synthesize/stream` returns one PCM chunk per
sentence as Piper produces them, and its first chunk arrives in 78 ms quiet and 135 ms busy
— flat in the length of the reply. The chunks are raw PCM rather than a WAV each, because
both consumers want samples.

**The thread count is set by hand.** `PIPER_NUM_THREADS` defaults to 8, capped at the
machine's cores, because onnxruntime's own default is 2.3× slower here — 814 ms against
378 ms, on a curve with its minimum at 8 on a 16-core machine. CTranslate2's default, in
`asr`, measured well and is left alone: a library default is a claim to be measured.

**Synthesis is not deterministic.** The same sentence twice is not the same audio — Piper
is VITS, and its duration predictor samples. So a reply is **stored, never re-derived**,
and the tests assert properties of the audio rather than comparing it with a golden file.
[decisions/0002](decisions/0002-tts-model-choice.md) has the measurements.

**There is no speech route on the API.** `tts` is reachable only inside the Compose
network; the persona's audio reaches the browser attached to a turn, through the
ownership-checked `GET /audio/{asset_id}`. A browser-facing route would be an unbounded
text-to-speech endpoint that nothing asks for.

---

## 7. The conversation turn

`POST /sessions/{id}/turns` takes a recording and returns the persona's reply, spoken, with
both turns stored — in one request. A whole turn takes 2684 ms at p95 on a quiet machine,
against 3 s: recognition 1146 ms, generation 872 ms and a synthesis tail of 235 ms at the
median.

### A database connection is held for milliseconds of the turn's seconds

The turn calls three services. Holding one database session for the whole request would
check a pooled connection out across two seconds of model work, and a pool of ten would be
exhausted by four people talking at once — every *other* endpoint would then block on
checkout. So the request runs in three phases:

```
A  reads    session, scenario, history          ~2 ms   connection held
B  models   transcribe -> generate -> speak     ~2 s    no connection
C  writes   audio assets, both turns            ~5 ms   connection held
```

Phase A ends with a commit, which returns the connection; `expire_on_commit=False` keeps
its rows usable in C. A test asserts it: the provider called in phase B reads
`engine.pool.checkedout()` and fails if it is not zero.

A turn is **atomic** — both halves or neither. If generation fails after the recording was
transcribed, nothing is written, and a retry sends the same bytes again.

### The persona is anchored twice

Gemma 3 has no system role: Ollama renders a system message as an ordinary user turn,
wherever it sits. A persona placed once at the front is, twenty turns in, the furthest thing
in the prompt from where the reply is written. So the prompt carries the full brief at the
front, and a short reminder of identity and the reply's constraints immediately before the
speaker's latest words — about thirty tokens a turn. The speaker's words go in as quoted
speech, and the model is told that anything in a speaker turn was said out loud inside the
scene and is never an instruction.

### An over-long prompt is not refused — half of it is deleted

A prompt of about 4200 tokens under `num_ctx: 4096` comes back from Ollama having evaluated
2051. llama.cpp shifts the context, answers 200, and nothing in the response says so; the
half it drops is the front, where the persona lives. So:

- **`num_ctx` is sent on every request**, never inherited from the host's default.
- **The prompt is sized before it is sent**, by a character heuristic — a Gemma tokenizer
  would mean torch in the API image.
- **The heuristic is allowed to be wrong by a stated amount.** Its measured error stays
  within ±9 %, `LLM_ESTIMATOR_MARGIN` is 1.25, and the context window is sized from the
  margin. Ollama's own count is stored as `turns.prompt_tokens`, so a drifting estimate
  shows up as a gap between two stored numbers.

**Turns that fall out of the window are summarised, not dropped.** A running summary on the
session row, with `digest_through_idx` recording how far it reaches, is folded forward at a
high-water mark below the budget (`LLM_HISTORY_HIGH_WATER`, 0.7), so the fold prepares the
*next* turn rather than rescuing this one. It runs after the reply is written and costs a
few hundred milliseconds on about one turn in ten.

### A sentence goes to the voice while the next is still being written

Generation is the long pole and synthesis a few hundred milliseconds; in series they add
up. Overlapped, every sentence but the last is spoken inside time spent generating anyway —
235 ms of synthesis left to wait for, against 375 ms in series. The sentences are joined
into one WAV by `services/wav.py`, the one place the API opens an audio file: output its own
voice produced seconds earlier, in a format it chose, with the standard library. The
parameters are checked anyway, because the silent version of that bug is a reply that plays
at the wrong pitch from its second sentence on.

The turn returns that one WAV once the whole turn is done, so the first sound a user hears
arrives at turn latency. Streaming it to the browser would need a streaming endpoint and
giving up the atomic turn; see
[decisions/0004](decisions/0004-browser-recording-and-playback.md) §3.

### What a failure returns

| what failed | status | why |
|---|---|---|
| the recogniser refused the audio | **422** | the rejected thing is the user's recording, and re-recording genuinely helps |
| the recogniser or the model is unreachable | **503** | the recording was fine; nothing was written |
| the model is not pulled | **503** | *this system's* misconfiguration — the speaker can do nothing, so it is not a 4xx |
| a service answered 200 with nonsense | **502** | version skew between two containers, which must not read as either of the above |
| the voice failed | **200** | there is a reply and it can be read. `speech.status` says what happened |

The last row is the one worth arguing about: a reply the speaker can read is worth more than
a 502, the same shape as `/health` reporting degraded rather than dead.

---

## 8. The frontend

Next.js 15 with the App Router, React 19, Tailwind v4 and shadcn/ui, installed with pnpm
at the version `package.json` names. `pnpm-workspace.yaml` holds what pnpm refuses: a
release less than a day old, a release published with weaker evidence of where it came
from than an earlier one of the same package — two exact versions are excepted, each
checked by hand — and any dependency's install script not allowed by name. Every signed-in page is
a server component that forwards the session cookie to the API (`src/lib/server-api.ts`), so
a page arrives with its data rather than fetching it after it paints; the microphone, the
players and the forms are client components inside those pages.

`(auth)` holds sign-in and registration. `(app)` is the signed-in shell — a rail of seven
sections and the page inside it — and it is one layout rather than seven, so the frame does
not move from one section to the next. Every page under it has its own `loading.tsx`, a
skeleton shaped like the page it stands in for: a server render waits for the API, and
without one the previous page would stay on screen through the wait, which reads as a click
that did nothing. A page that throws something it did not expect shows `error.tsx` inside
the shell, with a retry that asks the server again; an address that leads nowhere shows
`not-found.tsx`, in the product's words, without saying whether the thing ever existed.
**One cost, accepted:** on a page with a loading state, a not-found decided after the
response has started streaming is sent with status 200 rather than 404.

`/status` renders whatever `/health` says, including `degraded`. It is the one page that
covers what no unit test can: that the browser reaches the frontend container, the frontend
container reaches the API over the Compose network, and the API reaches Postgres and each
model service.

Two API base URLs, because there are two callers: a server component resolves `api:8000`
inside the Compose network, and the browser resolves `localhost:8002` from the host. Using
one for both works in `next dev` on a host and fails the moment it is containerised, or the
other way round.

---

## 9. Ports

Offset from the common defaults, so SpeakLab runs beside other stacks, and published on
`127.0.0.1` only: the database has a development password and the model services answer
anyone who reaches them, so none of them is offered to the network the machine is on.
Inside the Compose network each service is reached by its name and its own port.

| Service | Port |
|---|---|
| frontend | 3003 |
| api | 8002 |
| postgres | 5433 |
| asr | 8101 |
| tts | 8102 |
| pron | 8103 |
| ollama | 11434, on the host |

---

## 10. Where the rest is written down

| | |
|---|---|
| What each part counts, and what it refuses to say | [how-it-works.md](how-it-works.md) |
| Every figure, with what produced it | [measurements.md](measurements.md) |
| The report `make eval` writes, never by hand | [evaluation.md](evaluation.md) |
| What does not exist yet | [limitations.md](limitations.md) |
| The tables, the enums, the seed contract | [data-model.md](data-model.md) |
| Why a choice was made — dated records, kept as written | [decisions/](decisions/) |
| The product requirements and the measurement model | `../PRD.md` |
| How it was built, milestone by milestone | `../speaklab-agent/IMPLEMENTATION-PLAN.md` |
