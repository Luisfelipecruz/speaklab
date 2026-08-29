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

`docker-compose.yml` declares all seven services now, including build contexts —
`infra/asr`, `infra/tts`, `infra/pron` — that do not exist and will not until m4, m5 and
m8. This works because a profiled service is excluded from `up` **and** from `build`, so
a missing context is inert rather than fatal.

| Profile | Services | Arrives |
|---|---|---|
| *(default)* | `postgres`, `api`, `frontend` | m1 |
| `speech` | `asr`, `tts` | m4, m5 — **the profile is removed then**; PRD §10.1 has both in the default stack |
| `pron` | `pron` | m8 |
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
`*.webm`, `*.mp3` and `audio_data/` for the same reason: the one exception is the golden
evaluation set in m11, which is small, human-recorded, and added with `git add -f`.

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

---

## 5. The frontend

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

## 6. Ports

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

## 7. Where the rest is written down

| | |
|---|---|
| What the product is, and the measurement model | `../PRD.md` §5, §7 |
| The twelve milestones, the schema, the API surface | `../speaklab-agent/IMPLEMENTATION-PLAN.md` |
| The tables, the enums, the seed contract | [data-model.md](data-model.md) |
| Why each milestone is shaped the way it is | the **Decisions** block of that milestone in §7 |
| Does pronunciation scoring actually work | m0 passed — the writeup lands in `decisions/` at m8; the headline numbers are in the README |
