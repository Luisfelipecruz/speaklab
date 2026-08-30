# Architecture

What the system is made of, and why each piece is where it is. The README summarises
this; this file is the version that defends itself.

Status: **m1**. Everything below that describes a model service describes a design that
has been decided and not yet built. Where that is the case it says so.

---

## 1. The shape

One orchestrator, one database, three model services, one language model on the host.

```
browser ──▶ Next.js :3003 ──▶ FastAPI :8002 ──▶ Postgres :5433
                                    │
                                    ├──▶ asr  :8101   faster-whisper       (m4)
                                    ├──▶ tts  :8102   Piper                (m5)
                                    ├──▶ pron :8103   wav2vec2 + torch     (m8)
                                    └──▶ Ollama :11434 on the HOST         (m6)
```

FastAPI is the only orchestrator. There is no message queue, no service mesh and no
agent framework: the request path is a handful of HTTP calls and a token budget, and a
framework would hide the token budget — the part actually worth reviewing.

### Why three model services instead of one

Because they have different weights, different runtimes and different costs, and folding
them together would force the cheapest to pay for the most expensive.

| Service | Runtime | Size | Profile |
|---|---|---|---|
| `asr` | faster-whisper on CTranslate2 | ~400 MB, no torch | `speech` |
| `tts` | Piper on ONNX | ~60 MB per voice | `speech` |
| `pron` | wav2vec2 + torch | ~2 GB | `pron`, alone |

`pron` has its own profile rather than sharing `speech`, and that is the whole point of
the split: someone who wants to try the conversation loop should not have to download two
gigabytes of torch to do it.

**Invariant I5 — the API image contains no model weights and no torch.** It is 422 MB
(measured), and `api/tests/test_health.py` asserts the absence of torch, transformers,
faster-whisper and piper rather than trusting a comment. Dependencies acquire
dependencies; that test is what turns "the image grew by two gigabytes" from something
noticed at deploy time into a red test in CI.

### Why Ollama runs on the host

Docker Desktop on macOS cannot pass the Apple GPU into a Linux container. A containerised
Ollama runs CPU-only while the host's uses Metal — the same model, several times slower,
for no benefit. So `OLLAMA_BASE_URL` defaults to `http://host.docker.internal:11434`,
and the `api` service declares `extra_hosts: ["host.docker.internal:host-gateway"]` so
that default is portable to Linux rather than being a Mac-only trick.

The `ollama` service is still declared, under `profiles: ["llm"]`, for a Linux host with
a GPU and for CI, where a self-contained stack matters more than throughput.

---

## 2. Compose profiles, and why the file is complete before the code is

`docker-compose.yml` declared all seven services from m1, including build contexts —
`infra/asr`, `infra/tts`, `infra/pron` — that did not exist and would not until m4, m5
and m8. This works because a profiled service is excluded from `up` **and** from `build`,
so a missing context is inert rather than fatal.

Two of those three contexts now exist, and their profiles went with them.

| Profile | Services | State |
|---|---|---|
| *(default)* | `postgres`, `api`, `frontend`, `asr`, `tts` | five services as of m5 |
| ~~`speech`~~ | ~~`asr`, `tts`~~ | **removed at m5.** It held two contexts that did not exist; m4 and m5 created them, and an empty profile is something people paste into a command that then does nothing |
| `pron` | `pron` | m8. The only build context still missing, and the only 2 GB one |
| `llm` | `ollama` | not on this machine — see above |
| `tools` | `test` | m1 |

The alternative — growing the file milestone by milestone — would make every later pull
request a diff against infrastructure rather than a diff against a feature, and would put
the same file in six `git add` lists. See `IMPLEMENTATION-PLAN.md` §1.1.

---

## 3. Health, and the difference between a dependency and a feature

The database is a dependency. The model services are not. Getting that backwards is the
single easiest way to make this stack unstartable.

```
GET /health         200 while any model service is missing; 503 only if Postgres is gone
GET /health/models  always 200 — a monitoring endpoint, not a liveness one
```

If `/health` returned 503 because `pron` was down, the compose healthcheck would fail,
`depends_on: service_healthy` would fail with it, and the frontend would refuse to start
because a milestone eight steps away had not been written. Instead the API reports
`degraded`, names each service, and keeps serving everything that is not speech. That is
requirement FR-27 and invariant I6, and until m4 it is also the *normal* state of this
repository.

The three probes run concurrently under a single timeout ceiling
(`HEALTH_PROBE_TIMEOUT_S`, 1.5 s), so a completely dead model layer costs that ceiling
once rather than three times. `/health` is what the container healthcheck curls every ten
seconds; a liveness probe that can hang is worse than no probe.

The status vocabulary is closed, so the frontend can switch on it:

| | |
|---|---|
| `ok` | reachable, answering 2xx |
| `unreachable` | no answer — not started, not built, DNS failure, or timed out |
| `error` | answered, but not with a 2xx. Up and unwell is a different problem from absent |

A service's own body is passed through under `reports`. The model services answer 200
with `model_loaded: false` while their weights download, because a cold start is minutes
and must not read as a crash — so *reachable* and *ready* are two different facts and
both are reported.

---

## 4. Data

Plain PostgreSQL 16, pulled not built. No PostGIS: nothing here is spatial. No pgvector:
nothing here is a retrieval problem. An unused extension is a lie about the system.

There is no `docker-entrypoint-initdb.d` script either. Alembic owns the schema from m2
onward, and an `init.sql` that also created tables would be a second source of truth that
runs exactly once, on an empty volume, and diverges silently after that.

Two database URLs, derived rather than configured separately so they cannot drift apart:
`DATABASE_URL` with `+asyncpg` for the request path, and `SYNC_DATABASE_URL` for Alembic,
which runs migrations synchronously and cannot parse the async dialect suffix.

Audio lives in a named volume, never in the working tree. `.gitignore` excludes `*.wav`,
`*.webm`, `*.mp3` and `audio_data/` for the same reason. The one exception is the golden
evaluation set, which arrived at m4 rather than m11: ten LibriSpeech utterances in
`eval/golden/asr/`, 1.5 MB, human-recorded, committed so that a number measured in CI and
a number measured on a laptop mean the same thing. They are FLAC, which needs no
`git add -f` — and which also exercises the format conversion a set already in the target
format would never test.

Since m2 the schema exists: twelve tables, three enum types, one revision. Two layers
above it — `api/db_models/` for columns, `api/models/` for wire shapes — because they
answer different questions, and `scenarios.persona_prompt` is the standing example of a
column that is loaded on every query and serialised by nothing. The tables, and why five
columns are JSONB while two adjacent ones are not, are in
[data-model.md](data-model.md).

Scenarios and passages are **seeded data, not fixtures**: real rows versioned as JSON in
`api/seeds/`, loaded idempotently by slug with `make seed`. They sit under `api/` rather
than at the repository root so that one path resolves identically in the container, in
CI and in a host shell.

Since m3 there are accounts. Passwords are Argon2id (`argon2-cffi`, library defaults, so
that raising the cost later is a library upgrade rather than a migration — the parameters
travel inside each hash and a successful login re-hashes anything behind). The session is
a JWT in an **httpOnly** cookie, which decides more than it looks like it does: the
frontend cannot read the token, so it cannot attach it to a header, cannot store it, and
cannot leak it through an XSS payload — but it also cannot delete it, which is why there
is a `POST /auth/logout` the plan's API surface did not forecast. Every browser call
carries `credentials: "include"`; without that flag the cookie is silently dropped
cross-origin and a login appears to succeed while every following request 401s.

Access control is one dependency and one helper, in `api/dependencies.py`, and the
interesting part is how it is enforced. `tests/test_ownership.py` walks the registered
router table and asserts that every route either depends on `current_user` or appears in
an explicit table of public paths with a written reason. FR-4 is a claim about *all*
endpoints including the ones nobody has written yet, and the only test that can make
that claim is one that reads the router table rather than a list somebody maintains.
Cross-user reads are **404, not 403** — a 403 confirms the row exists and belongs to
somebody else, which turns an incrementing id into an enumeration of the table.

---

## 5. Audio, and what the recogniser is for

`asr` exists because of one line in PRD §7.1: **every fluency metric in the product is
arithmetic on word-level timings, and every accuracy metric is gated on word-level
confidence.** Nothing else in the system can produce either. So `word_timestamps=True` is
not a configuration choice, it is the reason the service is a separate process at all.

It returns `{w, start_ms, end_ms, logprob}` per word, and that shape appears in exactly
three places: the service emits it, `api/models/audio.py` types it, and the `turns.words`
JSONB column stores it. Three copies is two chances to drift, so the middle one is the
authority — the client parses into it, which means a field the service renames fails
validation at the boundary rather than becoming a fluency metric of zero six months later.

**Decoding happens in the service, not in the API.** The browser sends Opus in WebM on
Chrome and AAC in MP4 on Safari; neither reaches the model, and the API holds no media
library at all (invariant I5 is about weights, but the same logic applies to codecs). PyAV
— the ffmpeg libraries in-process — resamples everything to 16 kHz mono. That is also why
`audio_assets.format`, `.sample_rate` and `.duration_ms` are reported *back* by the
recogniser and stored as measured: the row describes what a decoder actually saw, and
`duration_ms` comes from the decoded sample count rather than the container header,
because a truncated upload declares the duration the recorder intended.

The service promises `0 <= start <= end <= duration` and **counts the timings it had to
repair to keep that promise** rather than silently repairing them. A `timestamp_fixups`
that starts climbing is a fact about the model; the same instinct as invariant I3, which
rejects out-of-taxonomy labels *and* counts them.

### The latency budget is missed, and that is written down

`small.en` scores **1.72 % WER** on the golden set and takes **1231 ms** on ~6 s of audio,
against PRD §9.1's **≤ 700 ms**. `base.en` at beam 1 meets the budget at 525 ms and costs
**4.31 % WER**. The default did not change, because that error rate is the input to the
grammar analyser, the fluency metrics and the read-aloud reference — and because §9.1's
own fallback order spends a cheaper lever first. **m5 has since built that lever**: the
streaming synthesis path in §6 returns first audio in 78 ms instead of 320 ms, which
hands back roughly 242 ms of the 531 ms this stage overspends. The switch to `base.en` is
still one environment variable, already measured, and m6 is where a whole turn decides
whether it is needed (Q8). The full argument, and the
reproducible case where `base.en` at beam 5 hallucinates a word and takes 4.5 s, is
[decisions/0001-asr-model-choice.md](decisions/0001-asr-model-choice.md).

### Storing a recording

Content-addressed: the filename is the sha256 of the bytes and `audio_assets` is unique on
`(user_id, sha256)`, so a double-tapped send or a retry after a timeout is one row rather
than two attempts. Scoped to the user, not global — two people reading the same passage
are two attempts, and a shared row would be a deletion request that cannot be honoured.

The insert runs inside a **savepoint**. That is not tidiness: from m6 this pipeline is
called inside a larger transaction that also writes a turn, and a plain rollback on the
duplicate path would discard that turn — a data-loss bug that appears only on a retry.

Nothing from a request ever reaches the filesystem. The stored name is a hex digest the
API computed, so there is no `..` and no separator to smuggle; `resolve_path` checks
containment *after* `resolve()` anyway, because a prefix comparison passes a symlink
pointing out of the volume.


## 6. Speech, and why there are two ways to ask for it

`tts` is Piper 1.7 on onnxruntime: no torch, no `espeak-ng` package — `piper-tts` carries
the phonemiser as a compiled extension — and a 61 MB voice that is **baked into the
image at build time**. That last part is the one place this system puts weights in an
image rather than on the shared volume, and the reason is size: Whisper is 746 MB and
wav2vec2 is ~2 GB, but 61 MB fits in a cached layer, and it buys the removal of the cold
first turn entirely. A voice other than the default is still downloaded into
`model_cache` and survives rebuilds there (FR-28).

### Two endpoints, because one of them cannot meet the budget

`POST /synthesize` returns the whole reply as one WAV. It is what m6 stores on the
`audio_assets` row, and on a quiet machine it takes **320 ms** for an 80-token reply
against PRD §9.1's **≤ 400 ms**. On a machine also running an iOS simulator and a build,
the same call takes **771 ms** and misses.

`POST /synthesize/stream` returns one PCM chunk **per sentence**, as Piper produces them.
Time to first audio is **78 ms** quiet and **135 ms** busy — and, crucially, flat in the
length of the reply, because a first sentence is a first sentence. This is PRD §9.1's
first prescribed fallback (*stream the LLM reply into TTS sentence by sentence*), built
in m5 rather than m6 so that the milestone which measured the problem is the one that
shipped the lever.

The chunks carry raw PCM rather than a WAV each, because both consumers want samples:
the API concatenates them into the single asset it stores, and a browser playing a queue
of separate `<audio>` elements gets an audible gap at every sentence boundary.

### The thread count is set by hand, and that is the finding

`intra_op_num_threads = 8` rather than onnxruntime's own default, which is **2.3×
slower** here — 814 ms against 378 ms. The curve is a U with its minimum at 8 on this
16-core machine; 16 threads is as bad as 1. Note that this is the *opposite* of m4's
conclusion, where CTranslate2's own default was left alone: a library default is a claim
to be measured, and two libraries in this system gave opposite answers.

### Synthesis is not deterministic

The same sentence twice is not the same audio — five runs of one reply spanned
8011–8475 ms. Piper is VITS and its duration predictor samples from a learned
distribution, which is what stops synthetic prosody sounding metronomic. Two consequences
belong to m6: a reply must be **stored rather than re-derived**, because `audio_assets` is
keyed by sha256 and two syntheses hash differently; and there is no golden WAV to assert
against, so the tests assert properties instead.

Everything above is measured in
[decisions/0002-tts-model-choice.md](decisions/0002-tts-model-choice.md).

### There is no TTS route on the API

`POST /synthesize` is reachable only from inside the compose network. The plan sketched
an "internal preview endpoint" on the API; it does not exist, because no requirement asks
for one — FR-6 and FR-7 deliver reply audio as part of a session turn, and it reaches the
browser through the ownership-checked `GET /audio/{asset_id}`. Adding a browser-facing
route would have been an unbounded text-to-speech endpoint with no requirement behind it.
Same question as m4's `POST /audio`, same answer.

---

## 7. The conversation, and the two ways it can quietly go wrong

This is the milestone where the product exists: audio in, transcript, persona reply,
speech out, persisted, in one request. The interesting parts are not the HTTP.

### The turn holds a database connection for about seven milliseconds of its two seconds

`POST /sessions/{id}/turns` calls three services. Written the obvious way — one session
from `Depends(get_db)`, held for the whole request — a pooled connection is checked out
across two seconds of model work, and a pool of ten is exhausted by four people talking
at once. The symptom would not be this endpoint being slow; it would be every *other*
endpoint blocking on checkout.

So the request runs in three phases:

```
A  reads    session, scenario, history          ~2 ms   connection held
B  models   transcribe -> generate -> speak     ~2 s    no connection
C  writes   audio assets, both turns            ~5 ms   connection held
```

Phase A ends with a commit, which returns the connection to the pool;
`expire_on_commit=False` is what keeps the rows loaded in A usable in C. The property is
asserted rather than described: a test hands the endpoint a provider that reads
`engine.pool.checkedout()` at the moment it is called, and fails if it is not zero.

A turn is **atomic** — both halves or neither. If generation fails after the recording
was transcribed, nothing is written. Keeping the user's half would leave a conversation
whose last turn is a question nobody answered, and a retry would then have to decide
whether it was continuing that turn or starting a new one.

### Gemma 3 has no system role, so anchoring the persona once anchors it in the wrong place

PRD R7 says the persona is re-anchored in the system message every turn, and on this
model that instruction needs reading twice. Ollama's template for `gemma3:4b` is explicit:

```
{{- if or (eq .Role "user") (eq .Role "system") }}<start_of_turn>user
```

A system message is rendered as an ordinary user turn, wherever it happens to sit in the
list. So "put the persona in the system message" means "put the persona in the first user
turn" — and by turn twenty that is the furthest thing in the prompt from where the reply
gets written.

The assembly therefore anchors twice: the full brief at the front, where it sets the
scene, and a short reminder of identity and the reply constraints immediately before the
latest thing the speaker said, where it is the last instruction the model reads. The
second anchor costs about thirty tokens a turn. What it buys is measured in decision 0003
with two deterministic proxies the personas make checkable — replies within their
sentence cap, and replies that end with a question — rather than with a model grading
another model, which is what invariant I1 exists to forbid.

### An over-long prompt is not refused. Half of it is deleted.

The most expensive thing this milestone learned, measured against Ollama 0.33.1 and
`gemma3:4b`:

| prompt | `num_ctx` | `prompt_eval_count` | what happened |
|---|---|---|---|
| ~3935 tokens | 4096 | 3935 | intact |
| ~4200 tokens | 4096 | **2051** | llama.cpp shifted the context |

There is no error, no warning, and no field in the response that says it happened. The
reply comes back 200 and reads perfectly well. The discarded half is the front of the
conversation — which is where a system message lives, so the persona is the first thing
to go, and the symptom is "it drifts out of character after turn twelve": PRD R7,
arriving through a mechanism nobody would think to look for.

Three things follow, and together they are the whole context strategy:

- **`num_ctx` is sent on every request**, never inherited from whatever the host's
  default is this version.
- **The prompt is sized before it is sent**, by a character heuristic — there is no Gemma
  tokenizer in this image and there will not be one, because it means torch (I5).
- **The heuristic is allowed to be wrong, and by a stated amount.** Characters per token
  is a property of the text, not of the language: measured error ran from −8.9 % to
  +5.7 % on realistic prompts. `LLM_ESTIMATOR_MARGIN` is 1.25, the context window is
  sized from it, and the live suite asserts the margin still covers the error.

The estimate only ever decides *what to send*. What gets reported is
`turns.prompt_tokens`, which is Ollama's own count — so a drifting constant shows up as
a widening gap between two stored numbers rather than as a context that silently overflows.

### Turns that fall out of the window are summarised, not dropped

FR-8. A scenario that forgets your name at turn twelve is not practice. The digest is a
running prose summary on the session row, with `digest_through_idx` recording how far it
reaches so that folding is incremental rather than a full re-read every turn.

The fold is triggered at a **high-water mark below the budget**, not at the budget, and
that gap is the design. At the mark every turn still fits, so the fold is preparation for
the *next* turn rather than a rescue for this one — which is what makes it correct to run
it after the reply has been sent. It is awaited rather than fired into a background task,
so it costs a few hundred milliseconds on roughly one turn in ten; `BackgroundTasks`
would hide that cost from the caller and the failure from the log, and m9 is where the
background-job machinery is actually built.

### A sentence goes to the voice while the next one is still being written

PRD §9.1's first prescribed fallback. Generation is the long pole; synthesis is a few
hundred milliseconds. In series they add up. Overlapped, all but the last sentence is
spoken inside time that was being spent generating anyway.

That produces N little WAVs where the turn needs one, so `services/wav.py` joins them —
the one place in the API that opens an audio file, and worth distinguishing from the
claim in `services/audio.py` that it never does. The API still does not decode anything a
*user* uploads: format, sample rate and duration for a recording are reported by the
service that decoded it. What this joins is output its own voice produced seconds
earlier, in a format it chose, using the standard library. The parameters are checked
anyway, because the silent version of that bug is a reply that plays at the wrong pitch
from the second sentence on, and nothing asserts against a sound.

### A failure of the voice does not fail the turn

Three services, three different answers when one of them is down:

| what failed | status | why |
|---|---|---|
| the recogniser refused the audio | **422** | the rejected thing is the user's recording, and re-recording genuinely helps |
| the recogniser or the model is unreachable | **503** | the recording was fine; nothing was written |
| the model is not pulled | **503** | *this system's* misconfiguration — the speaker can do nothing, so it is not a 4xx |
| a service answered 200 with nonsense | **502** | version skew between two containers, which must not read as either of the above |
| the voice failed | **200** | there is a reply and it can be read. `speech.status` says what happened |

The last row is the one worth arguing about. A reply the speaker can read is worth more
than a 502, and this is the same shape `/health` uses when it reports degraded rather
than dead (invariant I6).

### FR-26 finally means something

`users.retain_audio` has been settable since m3 and nothing stored a waveform until now.
With it off, a turn is transcribed and the recording is then not kept: no file, no
`audio_assets` row, and the turn still carries the transcript, the word timings and the
confidence — everything every later metric is computed from. The setting drops the audio
and keeps the derived data, which is exactly what the requirement asks for. The persona's
own audio is stored either way; it is synthesised speech, not the speaker's voice.

---

## 8. The frontend

Next.js 15 with the App Router, React 19, Tailwind v4 and shadcn/ui. One page today,
which renders `/health`.

That page is not a placeholder. It is the only test that covers the thing no unit test
can: that the browser reaches the frontend container, the frontend container reaches the
API container over the compose network, and the API reaches Postgres. It renders whatever
`/health` actually says, including `degraded`.

Two API base URLs, because there are two callers: a server component resolves `api:8000`
inside the compose network, and the browser resolves `localhost:8002` from the host.
Using one for both works in `npm run dev` and fails the moment it is containerised, or
the other way round.

---

## 9. Ports

Offset from the other stacks on this machine so all of them run at once.

| Service | Port | Note |
|---|---|---|
| frontend | 3003 | |
| api | 8002 | 8001 was taken by an unrelated stack — see the decision log |
| postgres | 5433 | |
| asr | 8101 | m4 |
| tts | 8102 | m5 |
| pron | 8103 | m8 |
| ollama | 11434 | on the host, shared |

---

## 10. Where the rest is written down

| | |
|---|---|
| What the product is, and the measurement model | `../PRD.md` §5, §7 |
| The twelve milestones, the schema, the API surface | `../speaklab-agent/IMPLEMENTATION-PLAN.md` |
| The tables, the enums, the seed contract | [data-model.md](data-model.md) |
| Why each milestone is shaped the way it is | the **Decisions** block of that milestone in §7 |
| Does pronunciation scoring actually work | m0 passed — the writeup lands in `decisions/` at m8; the headline numbers are in the README |
