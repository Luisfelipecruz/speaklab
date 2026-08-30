# SpeakLab — Implementation Plan

**Status:** v1.2 — **m0 passed; m1 through m6 are built, merged into `main` and CI green.**
m7 is next. The repository exists at `Luisfelipecruz/speaklab`; every git command is still
prepared in `GIT-COMMANDS.md` for the human to run, never by an agent.
**Date:** 2026-08-29, last revised 2026-08-30 (m6)
**Companion to:** `../PRD.md`

---

## 0. How to read this

Thirteen milestones, `m0` through `m12`. `m0` is a throwaway spike; `m1`–`m12` each
become exactly one stacked pull request.

Every milestone states:

- **Goal** — one sentence
- **Why here** — what forces this ordering
- **Deliverables** — the file list that PR commits
- **Decisions** — the choices worth defending in a review
- **Tests** — what proves it
- **Done when** — the observable condition, measured not assumed

A milestone is complete when *Done when* is verifiably true and its block in the command
sheet has been extended. Writing the code is not completion.

**On `D<n>` tags.** They are entries in the project's decision log, which is a working
file kept out of the repository along with the rest of the session scaffolding (D18) —
it is rewritten every session and is state, not documentation. Nothing here depends on
reading it: wherever a decision matters to this plan, its reason is restated in full at
the point of use, and the tag is only a stable handle for it.

---

## 1. Conventions

Carried over from `dubai-real-estate-platform`, which is the reference implementation for
how this developer works.

| Concern | Convention |
|---|---|
| Branches | `feature/mN-slug`, stacked — each cut from the previous, not from `main` |
| Commits | Conventional prefix, one-line subject, ≤ 72 chars. Detail belongs in the PR body |
| PR bodies | Files under `.pr-bodies/`, referenced with `gh pr create --body-file` |
| PR template | What / Why / Measured / Test plan / Not-in-this-PR |
| Git execution | **Manual only.** No agent runs a mutating git or gh command. See `GIT-COMMANDS.md` |
| Staging | One `git add` per step listing every file that step commits. Never `git add -p` |
| Shared files | A file touched by several milestones is added **whole** in the first milestone that touches it, and is absent from every later `git add` |
| Python | 3.12 in-container, type hints throughout, `ruff` + `black` |
| TypeScript | strict, no `any`, components under 200 lines, tests co-located |
| Migrations | Alembic, one revision per milestone that changes schema |
| Tests | `pytest` in-container via `make test`; Jest + RTL for the frontend |

### 1.1 The shared-file rule in practice

Six files are edited by nearly every milestone:

```
docker-compose.yml     api/main.py        infra/api/requirements.txt
Makefile               README.md          docs/changelog.md
```

Under the staging rule they are committed **whole, in m1**, carrying forward content that
later milestones will use. This is deliberate: it is what makes each later PR a clean
diff instead of a merge conflict. `docker-compose.yml` therefore declares `asr`, `tts`,
and `pron` in m1, before those services exist — profiled or with build contexts that
arrive later, so the missing directories stay inert until their milestone creates them.

---

## 2. Environment

Verified on this machine on 2026-08-29. See `SESSION-HANDOFF.md` §2 for the raw output.

| Component | Status |
|---|---|
| Docker | 28.5.2, Compose v2.40.3 — ready |
| Ollama | 0.33.1 on the host, **`gemma3:4b` already pulled** — ready |
| Hardware | Apple M4 Max, 16 cores, 128 GB — generous headroom |
| Node | v22.20.0 — ready |
| Python | 3.14.5 on host; containers pin 3.12 |
| `gh` | 2.86.0, authenticated as `Luisfelipecruz` — ready |
| `ffmpeg` | **absent on host.** Required only inside the `asr`/`pron` images, which install it. Install on host only for m0 spike convenience: `brew install ffmpeg` |
| Git identity | **UNSET globally.** Must be set before the first commit — see `GIT-COMMANDS.md` §0.1 |

### 2.1 Ports

Offset from the Dubai platform so both stacks run at once.

| Service | SpeakLab | Dubai |
|---|---|---|
| frontend | 3003 | 3002 |
| api | 8002 | 8000 |
| postgres | 5433 | 5432 |
| asr | 8101 | — |
| tts | 8102 | — |
| pron | 8103 | — |
| ollama | 11434 (host, shared) | 11434 |

---

## 3. Target repository layout

```
speaklab/
├── .env.example
├── .gitignore
├── .dockerignore                   the api build context is the repo root
├── CLAUDE.md                       agent directive — git rules
├── LICENSE
├── Makefile
├── PRD.md
├── README.md
├── docker-compose.yml
├── .github/workflows/ci.yml
├── .pr-bodies/                     PR bodies, one per milestone
├── speaklab-agent/
│   ├── IMPLEMENTATION-PLAN.md      this file
│   ├── SESSION-HANDOFF.md
│   └── GIT-COMMANDS.md
├── api/
│   ├── main.py  config.py  database.py
│   ├── dependencies.py             current_user, get_owned_or_404 — m3
│   ├── alembic/versions/
│   ├── db_models/                  SQLAlchemy ORM — write path
│   ├── models/                     Pydantic — request/response
│   ├── routers/                    auth scenarios sessions turns passages
│   │                               attempts progress health
│   ├── services/                   security (m3) · asr_client audio wer (m4)
│   │                               tts_client pron_client llm conversation
│   │                               grammar errors fluency progress recommend
│   ├── scripts/                    seed.py  rollup.py
│   ├── seeds/                      scenarios.json, passages.json
│   └── tests/
├── frontend/
│   └── src/{app,components,lib,hooks}
├── infra/
│   ├── api/{Dockerfile,requirements.txt}      context is the repo root
│   ├── frontend/Dockerfile
│   ├── asr/{Dockerfile,app.py,requirements.txt}
│   ├── tts/{Dockerfile,app.py,requirements.txt}
│   └── pron/{Dockerfile,app.py,gop.py,g2p.py,requirements.txt}
├── eval/golden/asr/                ten LibriSpeech utterances + manifest — m4
├── spike/                          m0 only — never merged
└── docs/                           architecture, data-model, decisions, changelog
```

`seeds/` sits under `api/`, not at the repository root as this plan originally had it.
One path then resolves identically in all three places the loader runs: the container,
where `api/` is `/app`; CI, which runs from `api/`; and a host shell. A root-level
`seeds/` needs a bind mount in one of those and a different relative path in another, and
the day the two disagree the loader reads an empty directory and reports success.
Recorded as **D20**.

There is deliberately no `infra/postgres/`. Plain `postgres:16` is pulled, not built
(D9 — no PostGIS, no pgvector), so a Dockerfile whose only line is `FROM postgres:16`
would imply a customisation that does not exist; and an `init.sql` that created tables
would be a second source of truth beside the Alembic revisions that own the schema from
m2. Recorded as D15.

---

## 4. Architecture in one paragraph

The browser records Opus/WebM via `MediaRecorder` and posts it to FastAPI. FastAPI is the
only orchestrator: it normalises audio to 16 kHz mono PCM, calls `asr` for a transcript
with word timestamps and logprobs, computes deterministic fluency and grammar metrics
in-process with spaCy, calls host Ollama for the persona's reply, calls `tts` for audio,
and returns both. Read-aloud takes a second path: the same transcript plus a canonical
phoneme sequence from G2P go to `pron`, which force-aligns and returns per-phone GOP.
Everything lands in Postgres. A nightly rollup collapses per-turn rows into per-user
snapshots, which is what the progress page reads. No model weights live in the API image.

---

## 5. Physical data model

Indicative DDL. Authoritative version is the Alembic revision from m2.

```sql
CREATE TABLE users (
    id                  BIGSERIAL PRIMARY KEY,
    email               TEXT NOT NULL UNIQUE,
    password_hash       TEXT NOT NULL,              -- argon2id
    native_language     TEXT NOT NULL DEFAULT 'es', -- selects L1 phoneme priors
    cefr_self_assessed  TEXT,
    retain_audio        BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE audio_assets (
    id            BIGSERIAL PRIMARY KEY,
    user_id       BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    path          TEXT NOT NULL,          -- on the audio volume, never a blob
    duration_ms   INTEGER NOT NULL,
    sample_rate   INTEGER NOT NULL,
    format        TEXT NOT NULL,
    sha256        TEXT NOT NULL,
    device_hint   TEXT,                   -- PRD P4: trends must survive a mic change
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, sha256)
);

CREATE TABLE scenarios (
    id               BIGSERIAL PRIMARY KEY,
    slug             TEXT NOT NULL UNIQUE,
    title            TEXT NOT NULL,
    description      TEXT NOT NULL,
    category         TEXT NOT NULL,
    cefr_band        TEXT NOT NULL,
    persona_prompt   TEXT NOT NULL,
    goal             TEXT NOT NULL,
    target_grammar   JSONB NOT NULL DEFAULT '[]',   -- closes the elicitation loop
    target_functions JSONB NOT NULL DEFAULT '[]',
    rubric           JSONB NOT NULL DEFAULT '{}',
    is_active        BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE passages (
    id            BIGSERIAL PRIMARY KEY,
    slug          TEXT NOT NULL UNIQUE,
    title         TEXT NOT NULL,
    body          TEXT NOT NULL,
    cefr_band     TEXT NOT NULL,
    phoneme_focus JSONB NOT NULL DEFAULT '[]',      -- ARPAbet, e.g. ["TH","V","IH"]
    word_count    INTEGER NOT NULL,
    is_active     BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TYPE session_mode AS ENUM ('conversation', 'read_aloud');
CREATE TYPE session_status AS ENUM ('active', 'completed', 'abandoned');

CREATE TABLE sessions (
    id          BIGSERIAL PRIMARY KEY,
    user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    scenario_id BIGINT REFERENCES scenarios(id),
    mode        session_mode NOT NULL,
    status      session_status NOT NULL DEFAULT 'active',
    started_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at    TIMESTAMPTZ,
    report      JSONB
);
CREATE INDEX ON sessions (user_id, started_at DESC);

CREATE TABLE turns (
    id             BIGSERIAL PRIMARY KEY,
    session_id     BIGINT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    idx            INTEGER NOT NULL,
    role           TEXT NOT NULL CHECK (role IN ('user','assistant')),
    audio_asset_id BIGINT REFERENCES audio_assets(id),
    transcript     TEXT,
    words          JSONB,        -- [{w,start_ms,end_ms,logprob}] — source of §7.1 fluency
    asr_confidence REAL,         -- gates a turn out of accuracy trends (PRD §7.5)
    asr_model      TEXT,
    latency_ms     INTEGER,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (session_id, idx)
);

CREATE TABLE fluency_metrics (
    turn_id           BIGINT PRIMARY KEY REFERENCES turns(id) ON DELETE CASCADE,
    speech_rate_wpm      REAL,
    articulation_rate    REAL,   -- excludes pauses >= 250 ms
    pause_ratio          REAL,
    mean_length_run      REAL,
    filler_count         INTEGER,
    word_count           INTEGER,
    response_latency_ms  INTEGER
);

CREATE TABLE grammar_usage (
    id       BIGSERIAL PRIMARY KEY,
    turn_id  BIGINT NOT NULL REFERENCES turns(id) ON DELETE CASCADE,
    feature  TEXT NOT NULL,      -- past_simple, present_perfect, conditional_2 ...
    count    INTEGER NOT NULL,
    UNIQUE (turn_id, feature)
);

CREATE TABLE language_errors (
    id           BIGSERIAL PRIMARY KEY,
    turn_id      BIGINT NOT NULL REFERENCES turns(id) ON DELETE CASCADE,
    category     TEXT NOT NULL,   -- closed taxonomy, PRD §7.2
    subcategory  TEXT,
    span_start   INTEGER,
    span_end     INTEGER,
    original     TEXT NOT NULL,
    correction   TEXT NOT NULL,
    explanation  TEXT,
    detector     TEXT NOT NULL CHECK (detector IN ('llm','rule')),
    confidence   REAL NOT NULL
);
CREATE INDEX ON language_errors (turn_id, category);

CREATE TYPE attempt_status AS ENUM ('pending','scoring','scored','failed');

CREATE TABLE attempts (
    id             BIGSERIAL PRIMARY KEY,
    session_id     BIGINT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    passage_id     BIGINT NOT NULL REFERENCES passages(id),
    audio_asset_id BIGINT NOT NULL REFERENCES audio_assets(id),
    transcript     TEXT,
    wer            REAL,
    status         attempt_status NOT NULL DEFAULT 'pending',
    error_message  TEXT,          -- FR-16: a failure states its reason
    scored_at      TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE phoneme_scores (
    id               BIGSERIAL PRIMARY KEY,
    attempt_id       BIGINT NOT NULL REFERENCES attempts(id) ON DELETE CASCADE,
    word             TEXT NOT NULL,
    word_idx         INTEGER NOT NULL,
    phone_idx        INTEGER NOT NULL,
    canonical_phone  TEXT NOT NULL,
    recognized_phone TEXT,        -- what won instead: /TH/ -> /S/ is the actionable bit
    start_ms         INTEGER,
    end_ms           INTEGER,
    gop              REAL NOT NULL,
    posterior        REAL
);
CREATE INDEX ON phoneme_scores (attempt_id);
CREATE INDEX ON phoneme_scores (canonical_phone);

CREATE TABLE progress_snapshots (
    id            BIGSERIAL PRIMARY KEY,
    user_id       BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    period        TEXT NOT NULL CHECK (period IN ('day','week')),
    period_start  DATE NOT NULL,
    fluency       JSONB NOT NULL DEFAULT '{}',
    accuracy      JSONB NOT NULL DEFAULT '{}',   -- errors per 100w by category
    complexity    JSONB NOT NULL DEFAULT '{}',
    pronunciation JSONB NOT NULL DEFAULT '{}',   -- mean GOP per phone, z-scored
    sample_counts JSONB NOT NULL DEFAULT '{}',   -- gates thin data out of charts
    cefr_estimate TEXT,
    UNIQUE (user_id, period, period_start)
);
```

**Why `words JSONB` rather than a `words` table.** Word timings are read as a whole array
for exactly one purpose — computing §7.1 metrics — and never queried across rows. A table
would add ~150 rows per turn and buy nothing. Errors and phoneme scores *are* separate
tables precisely because they are queried across rows, aggregated by category and phone.

---

## 6. API surface

Target: **30** operations — 29 as first forecast, plus the `POST /auth/logout` that m3
found was forced by the httpOnly-cookie decision (D24): a script that cannot read the
token cannot delete it either, so logging out has to be a server operation. Counted
against `app.openapi()` at m12, not recalled — this list is the forecast, the running
system is the authority. **18 exist as of m6**, counted from the running app rather than
from this list. m5 added none: its `POST /synthesize` is a model-service internal API, and
the "internal preview endpoint" the m5 deliverable list named was not built (D31, resolving
Q9). m6 added the six session routes below, exactly as forecast.

```
GET    /health                        liveness; reports each model service independently
GET    /health/models                 which model services are up, which degraded

POST   /auth/register                 FR-1                                    m3
POST   /auth/login                    FR-2                                    m3
POST   /auth/logout                   clears the cookie; see D24              m3
GET    /auth/me                       FR-2                                    m3
PATCH  /auth/me                       native language, retention preference   m3

GET    /scenarios                     filter: band, category, target_grammar   FR-5
GET    /scenarios/{slug}
GET    /passages                      filter: band, phoneme_focus              FR-11
GET    /passages/{slug}

POST   /sessions                      start; returns opening turn             FR-6
GET    /sessions                      history, paginated
GET    /sessions/{id}                 full transcript                         FR-10
POST   /sessions/{id}/turns           audio in -> transcript + reply + audio  FR-7
POST   /sessions/{id}/end             produces the session report             FR-9
DELETE /sessions/{id}

POST   /attempts                      audio + passage; enqueues scoring       FR-12
GET    /attempts/{id}                 poll; status + scores when ready        FR-15
POST   /attempts/{id}/rescore         retry a failed job                      FR-16
GET    /attempts                      history for a passage or user

GET    /audio/{asset_id}              streams stored audio, ownership-checked

GET    /progress/summary              window param; all four families         FR-21
GET    /progress/fluency
GET    /progress/accuracy             optional category filter
GET    /progress/complexity
GET    /progress/pronunciation        z-scored, sample-gated                  FR-23
GET    /progress/phonemes/{phone}     one phone's full history
GET    /progress/recommendations      one scenario + one passage, with reasons FR-24
GET    /progress/export               full JSON export                        FR-25
```

Model-service internal APIs, never exposed to the browser:

```
asr  :8101   POST /transcribe    wav -> {text, words[], confidence, model}
             GET  /health
tts  :8102   POST /synthesize    {text, voice} -> audio/wav
             GET  /health  GET /voices
pron :8103   POST /align         {wav, reference_text} -> {phones[], gop[], recognized[]}
             POST /g2p           {text} -> canonical ARPAbet sequence
             GET  /health
```

---

## 7. Milestones

### m0 — GOP feasibility spike *(not merged)*

> **This is the gate on the entire product.** PRD risk R1. Nothing else starts until it
> passes or the fork is taken.

**Goal.** Prove that a wav2vec2 CTC phoneme model plus forced alignment produces a GOP
that separates deliberately bad pronunciation from good, on this developer's own voice.

**Why here.** m8 is the hardest milestone and the one the product's premise rests on. If
GOP does not work, discovering that at m8 wastes seven milestones of work built around a
promise that cannot be kept. A spike costs a day.

**Method.**
1. Record the same 3 passages twice: once naturally, once with 10 deliberate, logged substitutions — `think` → `sink`, `very` → `berry`, `ship` → `sheep`, `speak` → `espeak`.
2. Run G2P (`g2p_en`) over the reference to get canonical ARPAbet.
3. Run `facebook/wav2vec2-lv-60-espeak-cv-ft` (or the Charsiu frame classifier) to get frame-level phone posteriors.
4. Resolve **Q1**: build the mapping between the G2P phone set and the model's inventory. Log every phone that fails to map — silent mismatch is the failure mode this spike exists to catch.
5. Force-align with `torchaudio.functional.forced_align`.
6. Compute GOP per phone. Compare the deliberately-broken phones against their clean counterparts.

**Done when.** A markdown writeup in `spike/gop-feasibility.md` reports the mean GOP gap
between deliberate errors and clean production, with an effect size, plus the per-phone
mapping table and its unmapped residue. **Pass** = clear separation on at least 8 of the
10 planted errors. **Fail** = take the ASR-diff fork, rewrite m8, and amend PRD §6.2.

**Not committed.** `spike/` is gitignored. Its *findings* move into `docs/decisions/`
in m8; the throwaway code does not.

---

### m1 — Scaffold, Compose, Postgres

> **Built and verified on 2026-08-29.** Every number in *Done when* below was counted
> against the running stack, not forecast. See `docs/changelog.md` 0.1.0.

**Goal.** `docker compose up -d` brings up postgres, api, and frontend healthy, with the
full service graph declared.

**Why here.** Every later milestone needs a place to land. The shared files (§1.1) are
committed whole here.

**Deliverables.**
```
.dockerignore  .env.example  LICENSE  README.md  Makefile
docker-compose.yml                    7 services; asr/tts/pron/ollama/test profiled
infra/api/{Dockerfile,requirements.txt}
infra/frontend/Dockerfile
frontend/.dockerignore
api/{main.py,config.py,database.py,pytest.ini}
api/routers/health.py
api/tests/{__init__.py,conftest.py,test_health.py}
frontend/  Next.js 15.5.24, React 19, Tailwind v4, shadcn/ui, one page
docs/{architecture.md,changelog.md}
.github/workflows/ci.yml
```

`CLAUDE.md` and `.gitignore` are **not** in this list. `CLAUDE.md` is gitignored (D18);
`.gitignore` belongs to the repository's initial commit on `main`, because a branch older
than the commit that adds it has no ignore rules at all (D19). There is no
`infra/postgres/` — see §3.

**Decisions.**
- Plain `postgres:16`, pulled not built, with no `init.sql`. No PostGIS, no pgvector — nothing here is spatial or a retrieval problem, and an unused extension is a lie about the system. Alembic owns the schema from m2 (**D15**).
- `api` declares **no `depends_on`** for model services (FR-27). `/health` is 200 while all three are unreachable and 503 only when Postgres is gone; a 503 for a missing `pron` would take the compose healthcheck, `depends_on: service_healthy` and the frontend down with it.
- The three model probes run **concurrently** under one 1.5 s ceiling, so a dead model layer costs that ceiling once rather than three times. `/health` is what the container healthcheck curls every ten seconds.
- `ollama` is `profiles: ["llm"]` and the API defaults to `host.docker.internal:11434`, with `extra_hosts: host-gateway` so the default is portable to Linux.
- `asr`/`tts` are `profiles: ["speech"]`, `pron` has `profiles: ["pron"]` **alone** (D10 — nobody should download 2 GB of torch to try the conversation loop). Profiled services are excluded from `up` *and* `build`, so their missing directories are inert.
- **The API build context is the repository root**, not `infra/api/`, so the image carries `api/` and runs without a bind mount. `.dockerignore` is what keeps that context small: without it every build ships `spike/.venv` (875 MB) and `frontend/node_modules` (549 MB) to the daemon.
- **API on 8002, not 8001** — 8001 is taken by an unrelated stack on this machine (**D16**).
- **Next.js 15.5.24, not 15.5.12** — the version this plan was written against carries 24 published advisories, all fixed inside the 15.5 line (**D17**).

**Tests.** `test_health` — 200 and the documented shape; unreachable model services
reported as `degraded`, not fatal; 503 only when the database is gone; `error`
distinguished from `unreachable`; a loading service's `model_loaded: false` passed
through; and **invariant I5 asserted** — torch, transformers, faster-whisper and piper
are absent from the API image.

**Done when.** `docker compose up -d` → 3 healthy containers. `curl localhost:8002/health`
→ 200. `http://localhost:3003` renders. `make test` green.

**Measured 2026-08-29:** 3/3 containers healthy · `/health` 200 in 13–20 ms warm over
5 calls · frontend 200, rendering the API's live `degraded` state · 13 tests passed in
0.21 s · `make lint` clean · API image 422 MB · 2 of the 29 forecast operations.

**Branch** `feature/m1-scaffold` · **PR** `feat: scaffold Compose stack with FastAPI, Next.js and Postgres`

---

### m2 — Data model and seeds

> **Built and verified on 2026-08-30.** Every number in *Measured* below was counted
> against the running stack. See `docs/changelog.md` 0.2.0 and `docs/data-model.md`.

**Goal.** The full schema of §5 exists via Alembic, seeded with 8 scenarios and 12 passages.

**Why here.** Everything downstream writes to these tables. Getting the shape right once
is cheaper than eleven migrations that reshape it.

**Deliverables.**
```
api/alembic.ini  api/alembic/{env.py,script.py.mako}
api/alembic/versions/0001_initial_schema.py
api/db_models/{__init__.py,base.py,user.py,scenario.py,passage.py,
               session.py,turn.py,attempt.py,phoneme.py,metrics.py}
api/models/{scenario.py,passage.py,common.py}
api/routers/{scenarios.py,passages.py}
api/scripts/seed.py
api/seeds/{scenarios.json,passages.json}          under api/, not the root — D20
api/tests/{test_scenarios.py,test_passages.py,test_migrations.py,test_seed.py}
docs/data-model.md
```

`api/models/common.py` also carries the closed `CEFRBand` enum and the 39 ARPAbet
symbols. `api/tests/conftest.py`, `api/main.py`, `Makefile`, `README.md`,
`docs/architecture.md` and `docs/changelog.md` are edited rather than added — the shared
files of §1.1, plus the fixtures.

**Decisions.**
- Scenarios and passages are **seeded data, not fixtures**: real rows, versioned in `seeds/`, loaded idempotently by slug. Re-running the seed inserts 0 rows.
- Passages are written to be phoneme-dense for their declared focus — a `/θ/` passage is not prose that happens to contain "think", it is engineered to force the sound repeatedly.
- Enums are Postgres native types, so bad values fail at the database rather than in Python. Three of them — `session_mode`, `session_status`, `attempt_status`. `turns.role`, `language_errors.detector` and `progress_snapshots.period` are CHECK constraints instead: two members, or a vocabulary expected to change. `language_errors.category` is TEXT and enforced in the application at m9, because a closed taxonomy that will be revised after reading real transcripts should be a code change with a test, not an `ALTER TYPE` that cannot run inside a transaction.
- **The test suite builds its schema with Alembic, never `Base.metadata.create_all`.** `create_all` builds what the ORM says; the migration builds what is applied to a real database. A suite that tests the first is green while the second is broken. Costs about a second per run.
- **Every constraint and index is named explicitly**, following the convention in `db_models/base.py`. Postgres names a constraint one way and SQLAlchemy names it another, and then the next `--autogenerate` emits a drop-and-recreate for something that never changed.
- **`persona_prompt` is never serialised to a client.** It is the exercise — a user who reads the persona's instructions is no longer practising against them — and it is the one string in a turn the user is not meant to influence. Asserted by a test against the prompt text, not the field name.
- **Seeds live at `api/seeds/`** rather than the repository root (**D20**), so the loader has one path in the container, in CI and on a host.

**Tests.** Migration up, down and up again on a scratch database, enum types included;
**`compare_metadata` between the ORM and the migrated schema must be empty**, which is
what catches a column added to a model and never migrated; seed idempotency (twice → 0
new rows) and an edit reported as an update that keeps the row id; both list endpoints
with every filter, an unknown band rejected as 422 rather than answered with `[]`, a
404 that names the slug; and the seed content itself — stored `word_count` matches the
body, every `phoneme_focus` symbol is one of the 39 the pron service can score, every
scenario declares the forms it exists to elicit.

**Done when.** `alembic upgrade head` on an empty volume creates all 12 tables. `make seed`
loads 8 scenarios and 12 passages, and loads 0 on a second run.

**Measured 2026-08-30:** 12 tables created · 3 enum types · `make seed` 8 + 12 inserted,
then 0 inserted / 0 updated / 20 unchanged · `GET /scenarios` 200 in 2.5–3.8 ms warm over
5 calls · ORM-vs-migration diff 0 entries · 52 tests passed in 2.1–2.4 s · `make lint`
clean · 6 of the 29 forecast
operations · passages 73–79 words · the 39 ARPAbet symbols match the m0 phone map exactly.

**Branch** `feature/m2-data-model` · **PR** `feat: add schema, migrations and scenario/passage seeds`

---

### m3 — Auth and user session — **BUILT** (2026-08-30)

**Goal.** Register, log in, and scope every practice row to its owner.

**Why here.** Adding a `user_id` foreign key after four milestones of data-writing code is
a rewrite. Adding it before is a column.

**Delivered.**
```
api/models/auth.py                    request and profile shapes; no field for the hash
api/routers/auth.py                   5 operations, not the 4 forecast — see D24
api/services/security.py              Argon2id + JWT, importing neither FastAPI nor the ORM
api/dependencies.py                   current_user, and get_owned_or_404
api/tests/{test_auth.py,test_ownership.py}    46 tests
frontend/src/app/(auth)/{layout,login/page,register/page}.tsx
frontend/src/lib/auth.ts              every call sets credentials: "include"
frontend/src/hooks/useAuth.ts         three-state status, not a boolean
```

No Alembic revision (**D23**) and `db_models/user.py` gained only a corrected comment:
m2 created `users` complete, and an empty revision would make `alembic history` claim a
change that never happened. Shared files touched: `config.py`, `main.py`,
`docker-compose.yml`, `.env.example`, `infra/api/requirements.txt`, `tests/conftest.py`.

**Decisions.**
- **D22 — Argon2id, via `argon2-cffi`, and passlib removed.** PRD FR-1 required Argon2
  and m1's requirements file shipped `passlib[bcrypt]` arguing the opposite; the PRD is
  the authority over a convenience call made in a requirements comment. Dropping the
  wrapper as well is a second decision: passlib 1.7.4 is from 2020, is unmaintained, its
  bcrypt backend raises on bcrypt ≥ 4.1, and a library whose value is switching between
  schemes buys nothing when there is one scheme and no legacy hashes. **Q6 closed.**
- **D23 — no Alembic revision at m3.** **Q7 closed.**
- **D24 — one access token in an httpOnly cookie; no refresh token; a logout endpoint.**
  The cookie is read by nothing in the browser, which also means nothing in the browser
  can clear it, so §6's four auth operations became five. The cost is stated rather than
  hidden: there is no server-side revocation, so a token copied out before logout stays
  valid for the rest of `ACCESS_TOKEN_TTL_HOURS` (168).
- **D25 — cross-user reads are 404, not 403**, enforced by one `get_owned_or_404` that
  folds existence and ownership into a single `WHERE` rather than a fetch-then-compare.
- Native language captured at registration: it selects the L1 phoneme priors of PRD §7.4.

**Measured.**

| | |
|---|---|
| Tests | 98 passing (was 52), 5.2–8.3 s in one container |
| Operations in `app.openapi()` | 11 of the 30 forecast |
| `POST /auth/register` | 61 ms median — one Argon2id hash at 64 MiB |
| Wrong password vs. unknown email | 75.6 vs 78.1 ms median, n=12 each — a 3% gap |
| The same pair without the dummy-hash equaliser | ~3.6 ms vs ~76 ms, a 21× tell |
| Stored hash | `$argon2id$v=19$m=65536,t=3,p=4$…` |
| API image | 424 MB (was 422 MB; argon2-cffi and email-validator cost 2 MB) |
| Browser check | `document.cookie` empty while signed in; the same fetch without `credentials: "include"` is 401 |

**Tests.** The two that carry the milestone:

- `test_ownership.py::test_every_route_is_either_scoped_to_a_user_or_declared_public`
  enumerates the registered router table and asserts each route either depends on
  `current_user` or is listed public **with a written reason**, in both directions. FR-4
  is a claim about every endpoint including the unwritten ones, and a per-endpoint check
  can only test the ones somebody remembered. Verified by mutation: adding an unscoped
  route makes it fail and name the route.
- `test_auth.py::test_registration_survives_the_request_that_created_it` proves the test
  client commits. It found a real defect — m2's `get_db` override yielded a session and
  never committed, so every write through the client was rolled back. m2 only read, so
  the suite was green and meaningless together. Verified by mutation: 12 failures.

**Done when.** ✅ Two users register and neither can read the other's rows;
`test_ownership` covers every user-scoped route by enumerating the router table.

**Branch** `feature/m3-auth` · **PR** `feat: add argon2id auth with JWT cookies and per-user scoping`

---

### m4 — ASR service and the audio pipeline · **BUILT (2026-08-30)**

**Goal.** Audio in, transcript with word timestamps and per-word logprobs out.

**Why here.** Every metric in the product derives from this output. It comes before
anything that consumes it.

**Delivered.**
```
infra/asr/{Dockerfile,app.py,requirements.txt}     faster-whisper on CTranslate2, PyAV
api/services/{asr_client.py,audio.py,wer.py}       client, pipeline, scorer
api/models/audio.py                                Word, SourceMedia, Transcription
api/routers/audio.py                               GET /audio/{asset_id}
api/tests/{test_asr_client.py,test_audio.py,test_asr_golden.py}
eval/golden/asr/                                   10 utterances + manifest + fetch.py
docs/decisions/0001-asr-model-choice.md
Makefile                                           `make asr-wer`
docker-compose.yml  .env.example  api/config.py  api/main.py
```

Three deliverables in the original list were **not** produced, each for a reason:

- **`api/alembic/versions/0003_audio_assets.py` — not written (D27).** `audio_assets` and
  `turns` were created complete at m2, and m4 changed no column. The second milestone
  running where the honest answer was "no revision"; see D23.
- **`api/db_models/audio.py` (extended) — not created.** `AudioAsset` lives in
  `db_models/user.py` by m2's design: audio has no meaning apart from its owner. Moving
  it to satisfy a filename in this plan would have been the plan editing the code.
- **A test file became three**, not two: `test_asr_client.py` (error taxonomy + the WER
  scorer), `test_audio.py` (storage, path safety, the endpoint) and `test_asr_golden.py`
  (the measurement, skipped without a live recogniser).

**Decisions.**
- **faster-whisper on CTranslate2, not `openai-whisper`.** Held. No torch in the image.
- **`profiles: ["speech"]` removed from `asr`.** Held — it is in the default stack, and
  the profile now holds only `tts`.
- **`small.en` at int8, overridable by env.** Held, and now measured: 1.72 % WER.
- **`word_timestamps=True` is non-negotiable.** Held.
- **ffmpeg normalises at the service boundary.** Deviated: **PyAV, in-process** (D29).
  It *is* the ffmpeg libraries, is already a faster-whisper dependency, and saves ~200 MB
  of Debian multimedia packages plus a subprocess. The source metadata comes from the same
  object that does the decoding, which is why the `audio_assets` row records what a
  decoder measured rather than what an uploader claimed.
- **Content-addressed by sha256.** Held, scoped to the user, and the insert runs in a
  **savepoint** so that m6's surrounding transaction survives a duplicate.
- **`/health` 200 before weights load.** Held, and sharpened: **503 when a load has
  failed**, which is permanent and is a different fact from a cold start.
- **New — `small.en` stays although it misses the latency budget (D26).** See below.
- **New — no `POST /audio` (D28).** Audio enters attached to a turn (m6) or an attempt
  (m8). A bare upload endpoint would create recordings that belong to nothing, and
  something would then have to decide what to do with the orphans.

**Measured.** Ten LibriSpeech test-clean utterances, ten speakers, 232 reference words.
Latency is the minimum of 7 runs after 3 warm-ups, service-side.

| Configuration | WER | ~6.8 s | ~10.1 s |
|---|---:|---:|---:|
| **`small.en` int8 beam 5 (default)** | **1.72 %** | **1231 ms** | 1416 ms |
| `small.en` int8 beam 1 | 1.72 % | 1352 ms | 1289 ms |
| `small.en` beam 5, VAD off | 3.45 % | — | 1772 ms |
| `base.en` int8 beam 5 | 6.03 % | 4420 ms | 984 ms |
| `base.en` int8 beam 1 | 4.31 % | 525 ms | 599 ms |
| `tiny.en` int8 beam 1 | 4.74 % | — | 384 ms |

| | |
|---|---|
| Tests | 146 — 139 without a recogniser, all 146 with one |
| Operations | 12 of 30 |
| `asr` image | 746 MB, no torch (planned ~400 MB — the estimate was optimistic) |
| Timestamp repairs on the golden set | 0 |
| Model load, warm cache | 1.3 s · cold download 139 s |
| Host load during the latency runs | 21 |

**Tests.** Transcript within a WER ceiling per model; timestamps monotonic, ordered and
inside the duration; `timestamp_fixups == 0`; sha256 dedup, per user, through a savepoint;
malformed audio 422 not 500; a truncated file does not claim its intended duration; the
golden audio matches the manifest's hashes. Two mutations were run to prove the new tests
are load-bearing: reverting the savepoint to a full rollback fails 2 tests, and replacing
`resolve()`-then-contain with a string prefix fails the symlink test.

**Done when.** *Partially met, and the gap is the finding.* A 10-second file returns text
with per-word timings — **but in 1416 ms, not the 700 ms this line asked for**, and ~6 s
of audio takes 1231 ms against PRD §9.1's ≤ 700 ms. Measured WER **is** recorded in
`docs/decisions/0001`. The model was not swapped to make the gate pass: `base.en` meets it
at 525 ms for 2.6× the error rate, that error rate feeds every downstream metric, and
§9.1's own fallback order spends a cheaper lever — streaming TTS — that m5 and m6 have not
built. **Carried to m6 as Q8**, where a whole turn can be measured instead of one stage.

**Branch** `feature/m4-asr` · **PR** `feat: add faster-whisper ASR service with word-level timestamps`

---

### m5 — TTS service · **BUILT (2026-08-30)**

**Goal.** Text in, natural speech out, fast enough to be inside a conversational turn.

**Why here.** Small, independent, and needed by m6. Landing it alone keeps m6's diff about
conversation rather than about audio plumbing.

**Delivered.**
```
infra/tts/{Dockerfile,app.py,requirements.txt}     Piper 1.7 on onnxruntime
api/services/tts_client.py                         client, three-outcome taxonomy
api/models/speech.py                               Speech, SpeechChunk
api/tests/{test_tts_client.py,test_tts_live.py}
frontend/src/components/AudioPlayer.tsx
docs/decisions/0002-tts-model-choice.md
Makefile                                           `make tts-latency`, `make tts-sample`
docker-compose.yml  .env.example  api/config.py  .github/workflows/ci.yml
```

**Two deviations, both deliberate and both measured.**

- **`api/routers/tts.py` — not written (D31, resolving Q9).** §6 of this plan forecasts
  exactly 30 operations, none of them a TTS route, and lists `POST /synthesize` under
  *"Model-service internal APIs, never exposed to the browser"* — two lines above the
  deliverable that would have exposed one. No FR asks for it: FR-6 and FR-7 deliver
  reply audio as part of a session turn, and it reaches the browser through the
  ownership-checked `GET /audio/{asset_id}` that m4 built. The same question as m4's
  `POST /audio`, and the same answer (D28). The count stays at **12 of 30**.
- **`POST /synthesize/stream` — written, and not in the list (D32).** Piper produces
  audio one sentence at a time. Exposing that drops time-to-first-audio from 320 ms to
  78 ms and, on a contended machine, is the difference between missing PRD §9.1's budget
  (771 ms) and meeting it (135 ms). It is PRD §9.1's own first prescribed fallback, it
  lives in the file this milestone was writing anyway, and leaving it to m6 would have
  meant m6 reopening `infra/tts/app.py` — which is exactly what this milestone exists to
  prevent.

The plan's *"voices download at build time into the shared `model_cache` volume"* was not
literally implementable — a volume is not mounted during a build. Resolved by honouring
the reason rather than the wording: the 61 MB voice is baked into the image, which
removes the cold first turn entirely, and the volume caches any other voice (**D33**).

**Decisions, as planned and now with evidence.**
- **Piper over Coqui or Bark**, confirmed. 50× real time on CPU, no torch, no GPU — and Docker Desktop on macOS cannot pass the Apple GPU into a container anyway (D14), so every GPU-bound alternative runs on CPU here for no benefit.
- **`profiles: ["speech"]` removed**, and with `asr` already un-profiled at m4 the profile itself is gone. `docker compose up -d` now brings up five containers; only `pron` stays opt-in. `make speech-up` is deleted.
- `en_US-lessac-medium` default, env-configurable as both a build argument and a runtime variable.
- WAV out, not MP3. No encode step inside the budget, and every browser plays it.
- **New: `intra_op_num_threads = 8`, measured not chosen.** onnxruntime's own default is 2.3× slower here (814 ms against 378 ms). The curve is a U with its minimum at 8 on 16 cores. This is the *opposite* of m4's conclusion for CTranslate2, whose default was fine — a library default is a claim to be measured.

**Tests.** 22 client tests against `httpx.MockTransport` (the taxonomy, the WAV magic
check, every metadata header, the streaming contract) and 9 live tests that skip unless a
voice answers. **177 tests total**, 161 of which pass with no model service running.
Three mutations confirmed the new guards are load-bearing: dropping the RIFF check,
ignoring a mid-stream error object, and relaxing `duration_ms` to `ge=0` each fail
exactly the one test that names them.

**Done when — met, with one number worth stating plainly.** `POST /synthesize` returns
playable audio in **320 ms** for an ~80-token reply on a quiet machine, inside the 400 ms
budget. On a machine also running an iOS simulator and a build it takes **771 ms** and
misses, while first-sentence streaming holds at **135 ms** — which is why both endpoints
exist. The frontend player is written and type-checked but nothing mounts it yet: m7 is
the first page with audio on it, and m7 is also where the Jest/RTL harness lands.

**Branch** `feature/m5-tts` · **PR** `feat: add Piper TTS service with cached voices`

---

### m6 — Scenario engine and the conversation loop · **BUILT (2026-08-30)**

**Goal.** A full spoken turn works end to end, API-side: audio in → transcript → persona
reply → speech out, persisted.

**Why here.** First milestone where the product exists. Everything before it was capability.

**Deliverables.**
```
api/services/llm/{__init__.py,ollama.py,base.py}
api/services/conversation.py           persona anchoring, history budget, summarisation
api/services/turns.py                  ADDED — shared by both endpoints that generate
api/services/wav.py                    ADDED — joins per-sentence synthesis into one file
api/models/{session.py,turn.py}
api/routers/{sessions.py,turns.py}
api/db_models/{session.py,turn.py}     (extended: 2 columns + 4 columns)
api/alembic/versions/0002_conversation_context.py   NOT 0004 — see the deviation below
api/tests/{test_conversation.py,test_sessions.py,test_turns.py,test_llm_provider.py,
           test_wav.py,test_conversation_live.py}
docs/decisions/0003-conversation-context-strategy.md
```

**Decisions.**
- A thin provider interface with an Ollama implementation. Not LangChain: this is an HTTP call, a token budget, and a message list, and a framework would hide the token budget — the part actually worth reviewing.
- **The persona is re-anchored in the system message every single turn**, never left to survive in history. PRD risk R7; long conversations drift otherwise.
- History budget is fixed in tokens. Past the cap, the oldest turns are **summarised into a running digest**, not dropped — a scenario where the AI forgets your name at turn 12 is not practice.
- `latency_ms` recorded per turn from the first turn ever served. Regressions must be visible, not felt (R3).
- ASR, grammar analysis, and reply generation are dispatched concurrently where they do not depend on each other.
- Generation degrades explicitly: Ollama unreachable → 503 with a plain message, never a fabricated reply.

**Tests.** A scripted 10-turn conversation with a stub provider; history stays under
budget; summarisation preserves named entities; persona text present in every request;
provider down → 503.

**Done when.** `POST /sessions/{id}/turns` with a real recording returns transcript, reply
text, and reply audio, p95 under 3 s over 20 turns against `gemma3:4b`.

**Branch** `feature/m6-conversation` · **PR** `feat: add scenario conversation loop over local Gemma`

---

#### What was actually built, and where it differs

**Done, and the gate is met.** Six operations (18 of 30 exist), 274 tests, one migration,
and `docs/decisions/0003`. The turn works end to end against real models.

**The "done when" is met: p95 2684 ms against a 3000 ms budget**, twenty turns on a quiet
target machine (load 1.7 → 5.0). ASR 1146 ms, generation 872 ms, synthesis tail 235 ms.
The one stage over its own budget is ASR, and the turn absorbs it — which is what D26 bet
on. **The margin is 316 ms**: the same run with §9.1's first fallback off sat at 3043 ms,
and the same twenty turns on a busy machine measured 7283 ms, 2.7× on identical code.

**D34 — the migration is 0002, not 0004.** The deliverable list guessed 0004 by counting
milestones. m3, m4 and m5 each needed no schema change (D23, D27), and numbering
migrations after milestones rather than after migrations would put two gaps in a history
that never existed.

**D35 — the turn endpoint releases its database connection across the model calls.**
`database.get_db` warned about this at m1. The request reads, commits, spends ~2 s in
three services holding nothing, then re-acquires to write. Asserted by a test that has the
stub provider read `engine.pool.checkedout()` at the moment it is called.

**D36 — a turn is atomic; a silent voice is not a failed turn.** Both turns are written or
neither. But synthesis failing returns 200 with `speech.status` set, because a reply the
speaker can read is worth more than a 502 — the same shape `/health` uses for degraded.

**D37 — `POST /sessions/{id}/end` produces a report split by provenance**: `measured`
(counted from rows), `narrative` (written by the LLM), `pending` (the parts of FR-9 that
need m8 and m9). Invariant I1 made structural rather than documented.

**D38 — two extra service modules.** `services/turns.py` because the opening turn and a
mid-conversation turn are the same operation with a different message list, and
`services/wav.py` because per-sentence synthesis produces N files where a turn stores one.
The latter is the first place the API opens an audio file; `services/audio.py`'s claim that
it never does is now scoped to uploads, where it still holds.

**Three findings that changed the code**, all in decision 0003:

1. **Ollama silently discards half an over-long prompt.** No error, no warning; the
   discarded half is the front, where a system message lives. `num_ctx` is now stated on
   every request and the prompt is sized before it is sent, with a measured margin.
2. **Gemma 3 has no system role** — Ollama's template renders `system` as a user turn — so
   "re-anchor in the system message" does not do what it says. The persona is anchored
   twice. Whether the second anchor helps is **unresolved**: both deterministic proxies
   saturate at 100 % with and without it (n = 25). Logged as Q12 for m11.
3. **PRD §9.1's first fallback is worth ~140 ms**, measured against its own control on a
   quiet machine — 235 ms of synthesis left to wait for against 375 ms in series — not the
   second it was assumed to be worth. It stays on; it pays properly at m7.

**A fourth finding is about measurement rather than the system.** Two attempts to quantify
the overlap from within a single run were both wrong and both plausible (traps 33), and
the first three turn measurements were taken on a machine at load 10–16 and said the budget
was missed by a factor of two. Read the load average the suite prints beside its table.

**Q8 is resolved: no.** The turn meets its budget with `small.en` in it. ASR misses its
own stage budget at 1146 ms against 700 ms and the turn absorbs the overspend; downgrading
to `base.en` would buy ~620 ms and cost 2.6× the word error rate for a requirement already
met. **D26 is confirmed rather than reopened** — the turn-level measurement it asked for
now exists. Carried forward, unmeasured: §9.1's fallback order lists the reply cap last,
and reply length drives generation *and* synthesis, so it is plausibly the largest lever
of the three.

**Not built, deliberately:** no concurrent dispatch of grammar analysis (it is m9, so
there is nothing to run in parallel with; the only genuine concurrency at m6 is synthesis
overlapping generation, which is built). No `BackgroundTasks` for the digest fold — it is
awaited, visibly, because m9 is where this project's background-job machinery is designed.

---

### m7 — Conversation UI

**Goal.** A person who is not the author can hold a conversation without instructions.

**Why here.** m6 proved the loop server-side. This makes it usable and is what a portfolio
reviewer actually sees.

**Deliverables.**
```
frontend/src/app/scenarios/page.tsx
frontend/src/app/scenarios/[slug]/page.tsx
frontend/src/app/sessions/[id]/page.tsx
frontend/src/components/{RecordButton,Waveform,TranscriptPane,
                         TurnBubble,ScenarioCard,SessionReport}.tsx
frontend/src/hooks/{useRecorder.ts,useSession.ts}
frontend/src/lib/api.ts
frontend/src/components/**/*.test.tsx
```

**Decisions.**
- Push-and-hold to record, with a keyboard equivalent (space). Voice-activity detection guesses wrong and cutting someone off mid-sentence is worse than a held button.
- Live waveform during recording. It is the only honest signal that the mic is actually working; a spinner is not.
- Optimistic transcript bubble the moment recording stops, reconciled when ASR returns. Three seconds of blank screen reads as broken.
- `MediaRecorder` MIME negotiated per browser — Opus/WebM where available, MP4/AAC on Safari, with an explicit unsupported-browser message rather than a silent failure.
- Microphone permission denial is a designed state with recovery instructions, not an unhandled rejection.

**Tests.** RTL over recorder states (idle/recording/uploading/playing), permission denial,
network failure mid-turn, transcript reconciliation, keyboard-only operation.

**Done when.** A first-time user completes a 10-turn scenario in Chrome and Safari with no
console errors, and the session survives a page reload (FR-10).

**Branch** `feature/m7-conversation-ui` · **PR** `feat: add scenario conversation interface with browser recording`

---

### m8 — Read-aloud and pronunciation scoring

> The hardest milestone. Gated by m0 — **which passed on 2026-08-29.** Read
> `spike/gop-feasibility.md` before starting; it carries the mapping table, the measured
> effect size, three container-dependency findings, and the caveats that are still open.

**Goal.** A read passage returns per-phoneme GOP with the recognised phone for every
canonical phone.

**Why here.** After the conversation loop, because it reuses ASR, audio handling, and
session plumbing — and because m0 already retired its risk.

**Deliverables.**
```
infra/pron/{Dockerfile,app.py,gop.py,g2p.py,phone_map.py,requirements.txt}
api/services/pron_client.py
api/services/scoring.py                async job orchestration
api/models/attempt.py
api/routers/attempts.py
api/db_models/{attempt.py,phoneme.py}  (extended)
api/alembic/versions/0005_attempts_phonemes.py
frontend/src/app/read/{page.tsx,[slug]/page.tsx}
frontend/src/components/{PassageReader,PhonemeHeatmap,PhonemeTable}.tsx
api/tests/{test_gop.py,test_g2p.py,test_phone_map.py,test_scoring.py}
eval/golden/pron/                       clean + deliberately-broken pairs, HUMAN-recorded
docs/decisions/0004-gop-pipeline.md     m0's findings, promoted
```

**Decisions.**
- Scoring is **asynchronous**. It takes seconds and must not block an HTTP request; the client polls (FR-15).
- `phone_map.py` is **carried over from `spike/phone_map.py` nearly as-is**. Q1 is answered: all 39 ARPAbet symbols map, zero residue. Keep both safety properties — it raises on an unmapped phone, and it asserts its whole table against the model's real `vocab.json` at import. Two traps are live in that vocabulary: `ɡ` is U+0261 (ASCII `g` is absent entirely) and `r` is the trill, not English `ɹ`. Neither raises on its own; both silently produce confident nonsense.
- `recognized_phone` is stored, not just GOP. `/θ/ → /s/ ×34` is a lesson; "your GOP is −4.1" is a number.
- GOP thresholds are stored in config and **per phone — m0 settled that much of Q2.** Consonant mismatches dropped ~9.0 nats, vowels ~4.2; one global cut-off would either miss every vowel or drown in false positives. Set each threshold as a percentile of the *correct-speech* GOP distribution so it carries a stated false-positive rate. Calibrate from real recordings; the spike's −3.119 is one speaker's number and must not be copied in.
- `pron` is profiled. With it down, an attempt still returns transcript and WER, and phoneme scores report `unavailable` rather than the endpoint 500ing (PRD R6).
- Torch lives here and nowhere else.
- **Image build, all three learned in m0:** read `vocab.json` off the hub rather than instantiating `Wav2Vec2PhonemeCTCTokenizer`, which drags in `phonemizer` *and* the espeak-ng binary we do not need; use `soundfile` for I/O because `torchaudio.load` now requires `torchcodec`; download NLTK `averaged_perceptron_tagger_eng` and `cmudict` at **build** time — a container that fetches corpora on first request is broken.
- Measured cost, for reference: ~99 ms per attempt on 3.4 s of audio, against a 10 000 ms budget. Memory and image size are the constraint, not latency.

**Tests.** GOP arithmetic against hand-computed posteriors; alignment monotonicity and
coverage; every ARPAbet phone maps or the test fails; **the golden pair test — deliberately
broken recordings must score measurably worse than clean ones**, which is criterion S4 as
a unit test; `pron` down → degraded response, not an error.

**Do not synthesise the golden pairs with TTS.** Not because TTS is unusable — good neural
TTS decodes cleanly through this model; macOS `say` specifically does not. The reason that
holds is that **TTS produces categorical substitutions and learner errors are gradient**: a
retracted `/s/`, epenthesis with a particular vowel quality, an unreleased final stop.
Synthetic pairs would test the easy case while appearing to pass, and a cloned voice gives
no ground truth on which phones are wrong. Human recordings only (handoff D13, §9 trap 8).

**Done when.** A 60-word passage returns scores for every canonical phone within 10 s, the
heatmap renders, and the golden-pair separation is reported in `docs/decisions/0004`.

**Branch** `feature/m8-pronunciation` · **PR** `feat: add forced-alignment pronunciation scoring with per-phoneme GOP`

---

### m9 — Error taxonomy and grammar analysis

**Goal.** Every user turn yields deterministic grammar usage and validated error records.

**Why here.** Needs a corpus of real turns to develop against — m6 and m7 produce it.

**Deliverables.**
```
api/services/{grammar.py,errors.py,fluency.py}
api/services/taxonomy.py               the closed taxonomy as code
api/models/analysis.py
api/db_models/metrics.py               (extended)
api/alembic/versions/0006_analysis.py
api/scripts/analyze_backfill.py
api/tests/{test_grammar.py,test_errors.py,test_fluency.py,test_taxonomy.py}
eval/golden/errors/                    hand-labelled turns
docs/decisions/0005-error-taxonomy.md
```

**Decisions.**
- **Two detectors, deliberately.** spaCy morphology gives tense/aspect/modality/clause counts — deterministic, fast, and the source of every *trend* (PRD P1). Gemma proposes *errors*, which is a judgement call no rule set makes well.
- LLM output is constrained to the closed taxonomy. Anything outside it is **rejected, counted, and logged** (FR-19) — the rejection rate is itself a model-quality metric, and Q4 gets answered by watching it.
- Spans are validated against the transcript. A correction whose span does not match real text is discarded; the LLM does not get to invent locations.
- Analysis runs as a **background job**, not inline (Q3 resolved: latency wins). The session report at `/sessions/{id}/end` is where it surfaces.
- Fluency lands here rather than m4 because it belongs with the other analysers, and m4's word timestamps were already the hard part.
- Turns below the ASR confidence threshold are analysed but flagged, and excluded from accuracy trends (PRD R2).

**Tests.** Morphology extraction over a fixture of known sentences; taxonomy rejection of
invented categories; span validation against tampered offsets; precision on the golden
labelled set; filler and pause arithmetic against hand-computed timings.

**Done when.** Backfill over all existing turns completes; error detection precision on
the golden set is ≥ 0.70 (criterion S5) and reported in `docs/decisions/0005`.

**Branch** `feature/m9-analysis` · **PR** `feat: add grammar analysis and closed-taxonomy error detection`

---

### m10 — Progress, trends and recommendations

**Goal.** The user sees whether they are improving, and what to practise next.

**Why here.** Needs everything above it to have produced data.

**Deliverables.**
```
api/services/{progress.py,rollup.py,recommend.py}
api/routers/progress.py
api/scripts/rollup.py                  scheduled aggregation
api/db_models/progress.py              (extended)
api/alembic/versions/0007_progress.py
frontend/src/app/progress/page.tsx
frontend/src/components/{TrendChart,MetricPanel,PhonemeTrend,
                         RepertoireChart,NextUpCard}.tsx
api/tests/{test_progress.py,test_rollup.py,test_recommend.py,test_zscore.py}
docs/decisions/0006-progress-metrics.md
```

**Decisions.**
- Rollups are **materialised**, not computed per request. The progress page reads snapshot rows; scanning every turn on page load stops working around session 200.
- Phoneme trends are z-scored within the user against their own rolling baseline (PRD P4), and **gated on a minimum sample count** (Q5 — 5 as the working default, revisited with real data). Below the gate the UI says "not enough data yet" rather than drawing a confident line through noise.
- The repertoire chart implements P3 directly: forms used, alongside accuracy per form. A shrinking repertoire with a falling error rate is rendered as a **warning**, not a win.
- Recommendations are a **transparent weighted score** over weakest categories, least-used forms, worst phones, and recency. Every recommendation states its measured reason (FR-24). No ML, because a model here would be unexplainable and unnecessary.
- A device change annotates the pronunciation chart (PRD R5) rather than being silently absorbed.

**Tests.** Rollup arithmetic against a fixture of known turns; z-score correctness;
the sample gate suppressing thin series; recommendation determinism; a repertoire
regression producing the warning.

**Done when.** 30-day trends render for all four families from ≥ 20 real sessions
(criterion S7), and every recommendation carries a reason traceable to a stored metric.

**Branch** `feature/m10-progress` · **PR** `feat: add progress trends, rollups and explainable recommendations`

---

### m11 — Evaluation harness

**Goal.** Turn every model-facing claim into a number produced by a command.

**Why here.** Everything to be evaluated now exists. Before this, the README's numbers are
assertions.

**Deliverables.**
```
eval/{run.py,report.py}
eval/golden/{asr,pron,errors,personas}/
api/tests/test_eval_harness.py
Makefile                               (eval target activated)
docs/evaluation.md
.github/workflows/ci.yml                (extended)
```

**Decisions.**
- Four suites: **ASR** (WER on the golden set), **pronunciation** (GOP separation on clean/broken pairs, the S4 criterion automated), **error detection** (precision/recall against hand labels), **persona adherence** (does the model stay in character and elicit its declared `target_grammar`).
- Golden sets are **mounted read-only into the eval path and nowhere else**. The corpus a system is evaluated on must not be reachable by the system being evaluated — the Dubai project learned this the expensive way, and the isolation is a test here, not a convention.
- `make eval` emits a markdown report with dated numbers. The README quotes that report and nothing else (criterion S10).
- Persona adherence uses an LLM judge — the one legitimate place for one, because it evaluates prose rather than producing a plotted metric (P1 is not violated; nothing here reaches a user's trend chart).

**Tests.** The harness is tested against known-good and known-bad fixtures, so a broken
evaluator cannot report a passing grade.

**Done when.** `make eval` runs all four suites and writes `docs/evaluation.md` with
measured numbers, and CI runs the deterministic subset.

**Branch** `feature/m11-eval` · **PR** `feat: add evaluation harness for ASR, GOP, error detection and personas`

---

### m12 — Polish, documentation, demo

**Goal.** A stranger clones the repo, runs it, and understands the engineering.

**Why here.** Last. Documentation written before the system is finished documents an
intention.

**Deliverables.**
```
README.md                              (rewritten against measured reality)
docs/{architecture.md,data-model.md,evaluation.md}   (finalised)
docs/changelog.md
demo/{record.cjs,speaklab-walkthrough.mp4,cover.png}
frontend/src/app/**                    empty states, loading skeletons, error boundaries
api/main.py                            OpenAPI descriptions and examples
Makefile                               (all targets documented)
```

**Decisions.**
- Every number in the README is counted from the live system at write time — operation count from `app.openapi()`, test count from pytest, WER and GOP separation from `make eval`.
- The README states the honest limitations: local-model accuracy versus hosted, the GOP caveats of PRD §7.5, and the minimum machine that actually runs it.
- A recorded walkthrough, because a reviewer will not install Ollama to evaluate a portfolio project.
- Empty states matter disproportionately: a new user's progress page has no data, and "not enough data yet — practise 5 more times" is the correct design, not a blank chart.

**Done when.** A clean clone reaches all-healthy with no manual editing (criterion S1),
every S-criterion is verified and recorded, and the walkthrough is recorded.

**Branch** `feature/m12-polish` · **PR** `feat: finalise documentation, demo and empty states`

---

## 8. Dependency graph

```
m0 (spike, gates m8)
 │
m1 scaffold
 └─ m2 data model
     └─ m3 auth
         ├─ m4 asr ──┬─ m6 conversation ─ m7 conversation UI ─┐
         └─ m5 tts ──┘                                        │
                      m8 pronunciation (needs m4, gated by m0)┤
                                                              ├─ m9 analysis
                                                                  └─ m10 progress
                                                                      └─ m11 eval
                                                                          └─ m12 polish
```

m4 and m5 are genuinely independent and could be worked in either order. Everything else
is a chain. Branches stack in the order listed; each `--base` points at its parent, never
at `main` except m1.

---

## 9. Risk-to-milestone map

| PRD risk | Retired by | How |
|---|---|---|
| R1 GOP does not work | **m0** | Spike before any production code; explicit pass/fail with a written fork |
| R2 ASR errors read as grammar errors | m4, m9 | Per-word logprob gating; WER published |
| R3 Latency | m6 | Per-turn `latency_ms` from the first turn; ordered fallback list |
| R4 LLM invents categories | m9 | Closed taxonomy, span validation, rejection counted |
| R5 GOP varies with hardware | m10 | Within-user z-score, device fingerprint, sample gate |
| R6 `pron` memory pressure | m1, m8 | Profiled service, graceful degradation tested |
| R7 Persona drift | m6, m11 | Per-turn re-anchoring, summarised history, adherence suite |
| R8 Scope creep | this document | m1–m12 fixed; new ideas go to PRD §15 |

---

## 10. Effort

Evenings-and-weekends pace, one developer.

| Milestone | Sessions | Note |
|---|---|---|
| m0 | 1–2 | Gate. Do not skip |
| m1 | 2 | Compose and CI eat the time, not the code |
| m2 | 2–3 | Writing 12 phoneme-dense passages is most of it |
| m3 | 2 | |
| m4 | 3 | Browser audio format handling is the tax |
| m5 | 1 | Smallest milestone |
| m6 | 3–4 | Context budget and summarisation |
| m7 | 4 | UI always costs more than planned |
| m8 | 5–6 | Hardest, even with m0 done |
| m9 | 4 | Golden labelling is manual and slow |
| m10 | 4 | Charts and rollup arithmetic |
| m11 | 3 | |
| m12 | 3 | |
| **Total** | **~37–40** | |

---

## 11. First three actions

1. Set the git identity — it is **unset** and would produce unlinkable commits. `GIT-COMMANDS.md` §0.1.
2. Run the **m0 spike**. Do not write production code before it passes.
3. Create the repository and land m1. `GIT-COMMANDS.md` §0.2 and §A.1.
