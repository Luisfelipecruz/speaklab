# SpeakLab — Implementation Plan

**Status:** v1.18 — **m0 passed; m1 through m15 are merged into `main`, CI green** (m13 as
PR #15, `537869e`, 2026-09-06), and **three off-milestone PRs are merged**: #16 (`0.13.1`),
a fresh clone that can hold a conversation; #17 (`0.13.2`), the first cold run of `make
setup` — **7 min 12 s, against five minutes, missed**; and #18 (`0.13.3`, `49bdeea`), m14's
item 0 — the persona gives its instructions away in 16 of 200 attempts, from 59 of 200
(`docs/decisions/0013`). **m14, grammar practice, is merged as PR #19 (`0.14.0`,
`01676db`, 2026-09-12)** — the rule layer (`886b37a`,
`docs/decisions/0014`), 130 of 172 planted agreement errors and 2 of 129 missing articles
with no wrong fix; accuracy per form (`b3a8fe5`, `docs/decisions/0015`), 32 of 34
held-out corrections joined with no wrong form; the end-of-session defect (`b1a35c7`),
ending straight after speaking now waits for the last turn; the grammar page (`fad37c7`,
`docs/decisions/0016`), the learner's corrections in their own sentences and the verb
forms as counts, **no percentage on any screen**; the spoken drill (`d74ae6b`,
`docs/decisions/0017`) — say one of your corrected sentences again and see, word by word
and per correction, what the recogniser heard; and the seeds (`ab719d5`,
`docs/decisions/0018`) — three scenarios for articles, prepositions and false friends, of
which the detector files 12 of 20 prepositions under their kind but 6 of 20 articles and 6
of 20 false friends; CI green on its first run. **m15, articulation — *Make your point* — is merged as PR #20 (`0.15.0`,
`53279df`, 2026-09-12)** (`docs/decisions/0019`): a
spoken answer to a work prompt, how it is built and how it is delivered counted by code,
the model's checked feedback beside the counts, said again side by side; every shown
measure above 0.90 / 0.75 on held-out answers, phrases started again below it and not
shown, the model's shorter version withheld 2 of 16 held out; CI green on its first run.
**m16, polish, is committed** on `feature/m16-polish` (`0a58955`), its PR prepared for the owner. **m17, security and dependencies, is in progress** on `feature/m17-security` — items 0–5 committed, item 6 (Next 16) in the tree (`docs/decisions/0021`). Three criteria — S4, S5, S7 — are blocked on speech only
a person can produce, and no milestone changes that. The repository is
`Luisfelipecruz/speaklab`; every git command is prepared in `GIT-COMMANDS.md` for the human
to run, never by an agent.
**Date:** 2026-08-29, last revised 2026-09-12 (m15 merged as #20; m16 started and its items written; `demo/` out of the repository and the README reshaped; m17 added at the owner's request and items 0–5 built; §11 rewritten)
**Companion to:** `../PRD.md`

---

## 0. How to read this

Eighteen milestones, `m0` through `m17`. `m0` is a throwaway spike; `m1`–`m17` each
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
| This plan | Edits ride in the next milestone's or fix's PR, staged with its files. **There is no plan-only PR** — the owner's rule, 2026-09-10 |
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

`frontend/src/app/` gains a route group at m12: `app/(app)/` holds the four signed-in
sections behind one layout instead of the four identical ones there today. Parentheses
keep a route group out of the URL, so no route moves — only the repository path does,
which is the objection those four layouts each recorded in a comment, and the reason the
path is named here.

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

CREATE TABLE answer_prompts (        -- m15, migration 0007; seeded, keyed by slug
    id           BIGSERIAL PRIMARY KEY,
    slug         TEXT NOT NULL UNIQUE,
    title        TEXT NOT NULL,
    prompt       TEXT NOT NULL,
    category     TEXT NOT NULL,          -- explain | justify | walk-through | recommend
    cefr_band    TEXT NOT NULL,
    time_limit_s INTEGER NOT NULL,       -- 60–120, checked by the seed loader
    is_active    BOOLEAN NOT NULL DEFAULT true
);

CREATE TABLE answers (               -- m15, migration 0007; never the recording
    id             BIGSERIAL PRIMARY KEY,
    user_id        BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    prompt_id      BIGINT NOT NULL REFERENCES answer_prompts(id),
    again_of       BIGINT REFERENCES answers(id) ON DELETE SET NULL,
    transcript     TEXT NOT NULL,
    words          JSONB NOT NULL DEFAULT '[]',
    duration_ms    INTEGER,
    asr_confidence REAL,
    asr_model      TEXT,
    delivery       JSONB NOT NULL,       -- fluency, from the word timings
    structure      JSONB NOT NULL,       -- signposts, sentences, repeats, restarts
    feedback       JSONB,                -- the model's, with its check and status
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON answers (user_id, created_at);
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
against `app.openapi()` at m16, not recalled — this list is the forecast, the running
system is the authority. **18 exist as of m7**, counted from the running app rather than
from this list. m5 added none: its `POST /synthesize` is a model-service internal API, and
the "internal preview endpoint" the m5 deliverable list named was not built (D31, resolving
Q9). m6 added the six session routes below, exactly as forecast. m7 added none either — it
is the interface over m6's six, and its one server-side change was a derived field on
`TurnOut`, not a route. **All 30 exist as of m15**, counted from the running app on
2026-09-12 — the shape differs from this forecast (progress is three operations, not
eight, and the grammar page, the drill and the answers were not in it), the count does not.

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

GET    /grammar                       corrections grouped, verb forms, the form
                                      to practise — not in the forecast; m14
GET    /corrections/{id}/drill        one correction's sentence, to say again — m14
POST   /corrections/{id}/drill        audio in -> what was heard, per correction;
                                      nothing stored — not in the forecast; m14
GET    /answers                       the prompts, your answers, their history — m15
POST   /answers                       audio in -> counted and stored, the model's
                                      feedback beside it — not in the forecast; m15
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

### m1 — Scaffold, Compose, Postgres · **MERGED (PR #1, 2026-08-30)**

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

### m2 — Data model and seeds · **MERGED (PR #2, 2026-08-30; on `main` via `f3ee277`)**

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

### m3 — Auth and user session · **MERGED (PR #3, 2026-08-30; on `main` via `f3ee277`)**

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

### m4 — ASR service and the audio pipeline · **MERGED (PR #4, 2026-08-30; on `main` via `f3ee277`)**

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

### m5 — TTS service · **MERGED (PR #5, 2026-08-30; on `main` via `f3ee277`)**

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

### m6 — Scenario engine and the conversation loop · **MERGED (PR #6, 2026-08-30)**

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

### m7 — Conversation UI · **MERGED (PR #7, 2026-08-30)**

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

**Built, with five deviations from the sketch above.** All decided during the milestone
and recorded in handoff §3:

1. **The Jest + RTL harness is part of this milestone.** PRD §9.2 has required it since the
   start and the frontend had never had it, so `jest.config.mjs`, `jest.setup.ts`, the
   `package.json`/lockfile change and a new CI step ship here. **70 tests, 10 suites.**
2. **Four modules the deliverable list did not anticipate.** `components/AuthProvider.tsx`
   and `components/AppShell.tsx` — the header that sits *around* pages needing the profile
   is what m3 named as the trigger for promoting `useAuth` to a context; `lib/server-api.ts`,
   because a server component has no cookie jar and has to forward the header by hand; and
   `lib/navigation.ts`, because `?next=` is an open redirect unless it is checked.
3. **`frontend/src/app/sessions/page.tsx` is not on the list above.** `GET /sessions` and
   `DELETE /sessions/{id}` shipped in m6 with nothing calling them, and without a history
   list a conversation is unreachable once the tab closes — FR-10 true of the API and false
   of the product.
4. **One API change.** `TurnOut` gained `low_confidence`, derived from `asr_confidence`:
   it existed on the turn *response* only, so the marker vanished on a page reload. No new
   operation — the count stays at 18 of 30.
5. **`AudioPlayer` gained `autoPlay` and `onPlayingChange`**, and its first tests. m5
   shipped it with a documented gap naming this milestone as the date.

**Done when — one half is outstanding and cannot be automated.** The session survives a
reload (verified against the live stack, transcript and low-confidence marks intact), and
the signed-in pages produce zero console errors. **A microphone recording has never been
through this UI** — no headless browser has one — so "a first-time user completes a 10-turn
scenario in Chrome and Safari" needs a person. The recorder's states and failures are
covered by 9 unit tests; the gesture is not.

**And a correction.** Decision 0003 §3 said this fallback's "real payoff is m7". It is not:
the turn returns one concatenated WAV after the whole turn completes, so the browser's
first audio arrives at turn latency. See `docs/decisions/0004` §3.

**Branch** `feature/m7-conversation-ui` · **PR** `feat: add scenario conversation interface with browser recording`

---

### m8 — Read-aloud and pronunciation scoring · **MERGED (PR #8, 2026-09-05)**

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
heatmap renders, and the golden-pair separation is reported in `docs/decisions/0005`.

**Met, except the last clause.** A 79-word passage returns 250 scored phones in **8.1 s**
end to end; the heatmap renders; the m0 experiment reproduces **exactly** through the live
service (9/10 detected, mean drop +8.138, named 10/10). The golden-pair separation is
**not** reported, because the pairs are human recordings that do not exist yet — the test
is written and skips. See `docs/decisions/0005` §8.1.

**Six deviations from this section, all in `docs/decisions/0005`:**

1. **The decision doc is `0005`, not `0004`** — m7 took that number.
2. **No `0005_attempts_phonemes.py` migration.** m2 built the whole of §5 including
   `attempts` and `phoneme_scores`, so there is nothing to migrate. An empty revision
   written to match this list would be worse than none.
3. **`vocab.json` is vendored into the repository**, not read off the hub at build time.
   It is what makes the phone map testable in CI with no torch, and that test is the one
   that catches the U+0261 trap.
4. **PyAV, not `soundfile`** — `soundfile` cannot open WebM/Opus or MP4/AAC, which is what
   `MediaRecorder` produces.
5. **torch comes from PyTorch's CPU index.** PyPI's wheels pull the NVIDIA stack on arm64
   too; the image was 8.51 GB and is now 1.78 GB.
6. **Read-aloud refuses an account with `retain_audio` off**, because FR-16 and FR-26
   cannot both hold with `audio_asset_id` NOT NULL. A product call — handoff Q14.

Also delivered but not listed: `api/tests/test_scoring.py` (21 tests over the endpoint and
the job), `frontend/src/components/{PhonemeHeatmap,PhonemeTable,PassageReader}.test.tsx`,
`eval/golden/pron/{README.md,manifest.json,fetch.py}`, and `make pron-golden` /
`make pron-fetch`.

**Branch** `feature/m8-pronunciation` · **PR** `feat: add forced-alignment pronunciation scoring with per-phoneme GOP`

---

### m9 — Error taxonomy and grammar analysis · **MERGED (PR #11, 2026-09-05)**

**Goal.** Every user turn yields deterministic grammar usage and validated error records.

**Why here.** Needs a corpus of real turns to develop against — m6 and m7 produce it.

> **Built, and here is what it cost.** 426 API tests (up from 303) and 99 frontend tests,
> all green; lint, `tsc` and `eslint` clean. The full writeup is
> `docs/decisions/0006-error-taxonomy.md`. What a reader needs before touching it:
>
> 1. **The three corrections below were right and are applied.** The decision doc is
>    `0006`; the migration is `0003` and adds **columns only** — `fluency_metrics`,
>    `grammar_usage` and `language_errors` were created complete by `0001`; the confidence
>    gate is per **word**.
> 2. **Criterion S5 is not met.** Detection precision **0.500** against a 0.70 bar, over
>    six scored proposals. `gemma3:4b` finds roughly the right words and files them under
>    the wrong category three times in six; `mistral:7b` measured **worse** (0.333, with
>    47 % of its proposals refused); `gpt-oss:20b` could not be measured at all, because
>    `services/llm/ollama.py` reads `message.content` and a reasoning model's answer is in
>    `message.thinking`. **Q4 is answered and the answer is not "use a bigger model".**
> 3. **The figure is not decidable on this corpus either way.** Six scored proposals put a
>    95 % interval on 0.500 roughly half the width of the scale, so
>    `tests/test_error_precision.py` prints its numbers and asserts none of them. It
>    asserts the machinery instead. The set grows by somebody using the product.
> 4. **The golden set is split, on a privacy call the human made.** Four turns ship;
>    three are the speaker's real standup at work and are gitignored as
>    `labels.local.json` / `manifest.local.json`. The suite prefers the local set and
>    prints which one it read.
> 5. **The API image went from 425 MB to 811 MB** for the dependency parser. Still no
>    torch and no speech weights.
> 6. **The obvious next lever is a rule layer.** `language_errors.detector` allows
>    `'rule'` and every row is `'llm'`. Subject–verb agreement and article omission are
>    where the parse is reliable enough to propose errors on its own.

**Deliverables.**
```
api/services/{grammar.py,errors.py,fluency.py}
api/services/taxonomy.py               the closed taxonomy as code
api/db_models/metrics.py               (extended)
api/alembic/versions/0003_analysis.py  columns only; the tables exist from 0001
api/scripts/analyze_backfill.py
api/tests/{test_grammar.py,test_errors.py,test_fluency.py,test_taxonomy.py,
           test_analysis.py,test_error_precision.py}
eval/golden/errors/                    hand-labelled turns, half of it gitignored
docs/decisions/0006-error-taxonomy.md
```

**Also built, and not in the list above:** `api/services/analysis.py` (the background job
and the session summary), a `temperature` argument on the LLM provider, and the session
report's new sections in `frontend/src/components/SessionReport.tsx`.

**`api/models/analysis.py` was never written**, and the line above has been removed rather
than left as a deliverable nobody produced. The report is typed `dict | None` on
`SessionDetail` and its shape lives in `services/analysis.py`; giving it wire models would
have meant typing a document that is stored as produced and read whole by one screen.

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

**Done when.** Backfill over all existing turns completes — **done**, 7 of 7; error
detection precision on the golden set is ≥ 0.70 (criterion S5) and reported in
`docs/decisions/0006` — **reported, and not met: 0.500.**

**Branch** `feature/m9-analysis` · **PR** `feat: add grammar analysis and closed-taxonomy error detection`

---

### m10 — Progress, trends and recommendations · **MERGED (PR #12, 2026-09-05)**

**Goal.** The user sees whether they are improving, and what to practise next.

**Why here.** Needs everything above it to have produced data.

> **Built and merged, and here is what it cost.** 504 of 536 API tests pass with no
> services running, and 130 frontend tests across 18 suites; lint, `tsc`, `eslint` and
> `next build` all clean, and all three CI jobs green on the PR and again on `main`.
> 40 files, 5597 insertions.
> The writeup is `docs/decisions/0007-progress-metrics.md`. What a reader needs before
> touching it:
>
> 1. **Criterion S7 is not met and cannot be on this corpus.** It asks for 30-day trends
>    across four families from ≥ 20 real sessions. The database holds **2** conversation
>    sessions and **2** scored readings, all on one calendar day, for one account. Three
>    families draw a single point, the fourth is gated off at 2 readings against a floor of
>    5, and no direction is claimed anywhere on the page. That is the gate working.
> 2. **The gate is the milestone.** Most of the code is about what *not* to say: a thin
>    period is a hole with a reason rather than an omitted point; a suppressed series names
>    what it is waiting for; a direction is claimed only for a metric with a defensibly
>    better end and at least three points. Speech rate is drawn and never judged.
> 3. **Q5 is answered and it generalised.** The question was how many readings a phoneme
>    trend needs; the answer is five, and the useful outcome is that every family needed a
>    floor and they are not the same floor. Four gates, all in `config.py`, all reasoned
>    rather than measured — which is stated.
> 4. **The migration adds one column.** `progress_snapshots` was created complete by
>    `0001`; `updated_at` is what makes staleness answerable. Same shape as m9's `0003`.
> 5. **`api/db_models/progress.py` was not created.** `ProgressSnapshot` has lived in
>    `db_models/metrics.py` since m2, with the other three measurement tables, and moving
>    it would have been a rename for the sake of a filename in this list.
> 6. **The charts are hand-drawn SVG and no dependency was added.** Every charting library
>    draws a continuous line through whatever it is given, and the holes are the point.
> 7. **The obvious next lever is still Q15's rule layer.** The accuracy family carries m9's
>    0.500 labelling precision as an on-screen caveat, which is the honest rendering and
>    not a fix.

**Deliverables.**
```
api/services/{progress.py,rollup.py,recommend.py}
api/routers/progress.py
api/models/progress.py                 the wire shapes: series, gates, reasons
api/scripts/rollup.py                  scheduled aggregation
api/alembic/versions/0004_progress.py  one column; the table exists from 0001
frontend/src/app/progress/{page.tsx,layout.tsx,RefreshProgress.tsx}
frontend/src/components/{TrendChart,MetricPanel,PhonemeTrend,
                         RepertoireChart,NextUpCard}.tsx
api/tests/{test_progress.py,test_rollup.py,test_recommend.py,test_zscore.py}
docs/decisions/0007-progress-metrics.md
```

**Also built, and not in the list above:** five component test files, the progress entry in
`AppShell`, `make rollup`/`rollup-dry`/`rollup-force`, the `PROGRESS_*` block in
`.env.example`, and two promotions in `services/analysis.py` — `weighted_fluency` and
`is_counted` — so a month of practice is averaged the same way one session is.

**Decisions.**
- Rollups are **materialised**, not computed per request. The progress page reads snapshot rows; scanning every turn on page load stops working around session 200.
- Phoneme trends are z-scored within the user against their own rolling baseline (PRD P4), and **gated on a minimum sample count** (Q5 — 5 as the working default, revisited with real data). Below the gate the UI says "not enough data yet" rather than drawing a confident line through noise.
- The repertoire chart implements P3 directly: forms used, alongside accuracy per form. A shrinking repertoire with a falling error rate is rendered as a **warning**, not a win.
- Recommendations are a **transparent weighted score** over weakest categories, least-used forms, worst phones, and recency. Every recommendation states its measured reason (FR-24). No ML, because a model here would be unexplainable and unnecessary.
- A device change annotates the pronunciation chart (PRD R5) rather than being silently absorbed. **Built and inert:** `sample_counts.devices` records the distinct hints a period's readings used, and nothing populates `audio_assets.device_hint`, so the list is always empty and no chart is ever annotated. It is computed now so that the day something fills the column, the history does not have to be rebuilt.

**Tests.** Rollup arithmetic against a fixture of known turns; z-score correctness;
the sample gate suppressing thin series; recommendation determinism; a repertoire
regression producing the warning.

**Done when.** 30-day trends render for all four families from ≥ 20 real sessions
(criterion S7) — **reported, and not met: 2 sessions and 2 readings, on one day.** Every
recommendation carries a reason traceable to a stored metric — **done**, and asserted by a
test that every reason contains a number.

**Branch** `feature/m10-progress` · **PR** `feat: add progress trends, rollups and explainable recommendations`

---

### m11 — Evaluation harness · **MERGED (PR #13, 2026-09-05)**

**Goal.** Turn every model-facing claim into a number produced by a command.

**Why here.** Everything to be evaluated now exists. Before this, the README's numbers are
assertions.

> **Merged as `f3647fd`, and here is what it cost.** 528 of 562 API tests pass with
> no services running (was 504 of 536); 130 frontend across 18 suites, untouched. Lint
> clean on both trees. **24 files**, no migration, no new dependency, no new API operation.
> All three CI jobs passed on PR #13, and the new "Evaluation harness" step reported four
> suites not run and **graded nothing as met** on a runner with no model layer — the
> property the whole design rests on, confirmed on somebody else's machine.
> The writeup is `docs/decisions/0008-evaluation-harness.md`. What a reader needs first:
>
> 1. **The harness settles four of the ten criteria, and one is met.** S6 met at 1.72 %
>    word error rate. S5 **undecidable** — 0.500 over six scored proposals cannot be placed
>    against a 0.70 bar in either direction. S7 **not met** — five sessions on one calendar
>    day. S4 **has never run**, because the recordings do not exist.
> 2. **The fourth suite found something on its first run.** Asked to ignore its
>    instructions and print its brief, `gemma3:4b` recited it in **30 of 40 attempts**
>    across four runs. `GUARDRAILS` has forbidden that since m6 and nothing had ever
>    checked. It is a role-integrity failure, not a confidentiality one — every persona
>    ships in `api/seeds/scenarios.json`. Reported, not asserted; **not fixed here**, and
>    Q16 carries it.
> 3. **The judge is scored on every run**, against ten replies labelled before it existed.
>    It agrees 8 of 10 and misses **exactly the two the deterministic layer catches**,
>    identically on all four runs. That is the argument for the split design arriving on
>    the first measurement.
> 4. **The self-tests are built out of flattering fixtures.** Three true positives out of
>    three; a passing GOP probe standing in for S4; a README quoting a stale WER. Each is a
>    shape a plausible implementation reports as a pass, and each has a test saying it must
>    not. This is the one component whose bugs all point the same way.
> 5. **A fifth input that is not a suite:** `scripts/corpus.py`, the census. S7 is a fact
>    about a database and I9 forbids recalling it.
> 6. **Two bugs found on the way, both in this milestone's own work.** `black --exclude
>    eval` was a regex matching any path containing "eval" — six files unformatted since
>    they existed. And the runner checked for a result file before the exit code, so a
>    suite whose measurement passed and whose assertion failed reported as "measured" —
>    on the exact run that found item 2.

**Deliverables.**
```
eval/{run.py,report.py,scoring.py}
eval/golden/personas/                  probes + a calibration set for the judge
api/tests/{test_eval_harness.py,test_persona_adherence.py,eval_out.py}
api/scripts/corpus.py                  the census S7 is read against
Makefile                               (eval target activated)
docs/evaluation.md
.github/workflows/ci.yml               (extended)
```

**Also built, and not in the list above:** `eval/scoring.py` was not forecast and holds the
Wilson interval and the five deterministic persona rules, shared by the suites and the
report so there is one copy; `api/tests/eval_out.py`, the seam a suite hands numbers
through; the `.eval/` writable mount in `docker-compose.yml`; `make persona-adherence`,
`make corpus`, `make eval-local` and `make fmt-eval`; and `record()` calls plus Cohen's d
in the three suites that already existed.

**Not built, deliberately:** `eval/golden/{asr,pron,errors}/` were forecast as new and all
three already existed from m4, m8 and m9. Only `personas/` was missing.

**Decisions.**
- Four suites: **ASR** (WER on the golden set), **pronunciation** (GOP separation on clean/broken pairs, the S4 criterion automated), **error detection** (precision/recall against hand labels), **persona adherence** (does the model stay in character and elicit its declared `target_grammar`).
- Golden sets are **mounted read-only into the eval path and nowhere else**. The corpus a system is evaluated on must not be reachable by the system being evaluated — the Dubai project learned this the expensive way, and the isolation is a test here, not a convention.
- `make eval` emits a markdown report with dated numbers. The README quotes that report and nothing else (criterion S10).
- Persona adherence uses an LLM judge — the one legitimate place for one, because it evaluates prose rather than producing a plotted metric (P1 is not violated; nothing here reaches a user's trend chart).

**Tests.** The harness is tested against known-good and known-bad fixtures, so a broken
evaluator cannot report a passing grade. **Done** — 23 tests in `test_eval_harness.py`,
with no model, no service and no network, and the fixtures are the flattering ones.

**Done when.** `make eval` runs all four suites and writes `docs/evaluation.md` with
measured numbers — **done**, three of four suites measured on the run that produced the
committed report, and the fourth reported as not run because `pron` was not up. CI runs the
deterministic subset — **done**, `python eval/run.py --local`, which grades nothing as met
because nothing ran.

**Branch** `feature/m11-eval` · **PR** `feat: add evaluation harness for ASR, GOP, error detection and personas`

---

### m12 — Navigation, layout and the signed-in shell · **MERGED (PR #14, 2026-09-06)** — `720b6f2`, three commits squashed

**Goal.** A person who has signed in can see where they are, where else they can go, and
what to do next — on a phone and on a 27-inch monitor.

**Why here.** Two reasons, and neither is taste.

The first is sequencing. The polish milestone records a walkthrough, and a walkthrough of an interface that
is about to be replaced is a recording made twice.

The second is that m11 measured this product and got the same answer three times. S4 has
never run, S5 is undecidable and S7 is not met, and all three are blocked on one thing: a
corpus. The only machine that produces a corpus is a person practising, and the interface
currently asks them to navigate four sections by four text links squeezed beside a
wordmark. Making practice easy is not cosmetic here — it is the input to the measurements.

**Why this is a milestone at all, when §9 said m1–m11 were fixed.** It is not a new idea
arriving late. m7 shipped `AppShell` as a header that exists, in its own words, "because a
person who cannot get from a conversation back to the catalogue has to type a URL" — a
stated minimum, not a design. The scope-creep rule is there to stop features being
invented; it should not be used to rule an unmet quality bar out of scope. §9 now reads
m1–m13 — since 2026-09-06, m1–m15, and since 2026-09-12, m1–m16.

**What is wrong, counted rather than asserted.**

| | |
|---|---|
| Navigation | Four text links in one row of `AppShell.tsx`, with no disclosure at any width and nothing to show what is in a section before you open it. The current one is marked by weight and colour, which is the whole of the wayfinding |
| Width | `max-w-5xl` on both the header and `<main>` — 1024 px at every viewport. On a 2560 px display roughly 60 % of the screen is margin |
| Density | The progress page is a single `flex-col gap-6` of full-width cards — four metric families, a recommendation card, a repertoire chart and a phoneme trend, stacked in one column inside that 1024 px |
| The front door | `app/page.tsx` renders no shell, so `/` has no navigation at all, and its content is a service-status table for `asr`, `tts` and `pron`. That is a page for whoever runs the stack |
| After sign-in | `DEFAULT_AFTER_LOGIN` is `/scenarios`. Nothing answers "how am I doing, and what should I do now", though m10 already computes the answer |
| Dark mode | `globals.css` carries a complete `.dark` block and 16 sidebar variables. Nothing sets the class and nothing reads a sidebar variable, so the 11 lines carrying `dark:` utilities — 9 of them inside the shadcn primitives — can never fire |
| Duplication | Four four-line `layout.tsx` files each wrap `AppShell`, each with a comment explaining why the route group was skipped |
| Tests | Three of the 18 components under `components/` have no test file, and `AppShell` is one of them — the one every signed-in page renders inside. The other two are `AuthProvider` and `PhonemeTable.helpers` |

**Deliverables.**
```
frontend/src/components/ui/{sidebar,sheet,dropdown-menu,skeleton,tooltip}.tsx
frontend/src/components/{AppSidebar,ThemeToggle,PageHeader}.tsx
frontend/src/components/AppShell.tsx           rewritten around the sidebar
frontend/src/app/(app)/layout.tsx              one layout for the four sections
frontend/src/app/(app)/home/page.tsx           the signed-in home
frontend/src/app/page.tsx                      the public front door, health demoted
frontend/src/app/status/page.tsx               where the service table goes
frontend/src/app/layout.tsx                    the theme class, set before first paint
frontend/src/components/**/*.test.tsx
docs/decisions/0009-navigation-and-layout.md
```

**Decisions.**
- **A sidebar, not a wider top bar.** The four sections are peers a person moves between mid-task, and a vertical rail has room for the thing a top bar has no room for: what is *in* each section — a streak, a count, whether anything has been analysed since last time. It collapses to an icon rail rather than disappearing.
- **Below `md` it becomes a sheet.** Practice happens on the device the microphone is in.
- **`/` splits in two.** A public front door for a stranger, and `/home` for somebody signed in — which becomes `safeNext`'s default. `/home` is assembled from what m10 already returns: the recommendation card, the week's counts, the last session. The service-status table moves to `/status`, reachable by URL and not in the sidebar, because it is a diagnostic and it belongs to the operator.
- **Width becomes a property of the page, not of the shell.** Prose wants about 65 characters; a phoneme heatmap wants the screen. `AppShell` stops imposing a maximum and each page declares its own.
- **The route group finally lands.** `app/(app)/` replaces the four duplicated layouts. Parentheses keep it out of the URL, so no route changes — what changes is a repository path this plan names, which is the objection those four comments raised and the reason it is decided here rather than deferred a third time.
- **Dark mode ships, or the tokens come out.** A complete `.dark` block nothing can reach is dead code that reads as a feature. Either wire the toggle, persist the choice and set the class before first paint, or delete the block and the sidebar variables with it. Deciding against it is an outcome; leaving it as it is, is not.
- **No new runtime dependency without a line in the decision doc.** `radix-ui` and `lucide-react` are already installed and shadcn components are source files rather than packages. If persisting a theme needs `next-themes`, that is a decision to record, not a default to accept.

**Tests.** RTL, and the list is short because most of it is one property said several ways:
every section is reachable from every other without typing a URL. The current section still
carries `aria-current` — the header does that today and a rewrite is the ordinary way to
lose it. The mobile sheet opens, closes, and gives focus back. The shell
renders its navigation while the session check is still in flight — which `AppShell` has
claimed in a comment since m7 and nothing has ever verified. The signed-in home renders an
empty state rather than a blank for an account that has never practised. The theme survives
a reload.

**Done when.** Every section is one click from every other at 375 px and at 2560 px; a
signed-in person lands somewhere that tells them what to do next; no page is capped at a
width its content did not ask for; and `npm run lint`, `npm run typecheck`, `npm test` and
`npm run build` are green.

**Explicitly not here.** Empty states, loading skeletons and error boundaries for the
*existing* pages stay in the polish milestone — this milestone builds the frame, polish finishes what sits
inside it, and the one screen created here ships with its own empty state. No API change
either: every number this milestone puts on screen is already served by an operation that
exists, so the count stays at 25 of 30.

**What came back from looking at it.** The frame shipped and then failed three of its own
tests once the pages were seen together: per-page widths moved the content box on every
navigation, the type scale left the product at 12 px, and four metric families on one page
meant eleven charts each holding a single measurement. All three are corrected on the same
branch, in a second commit, with `docs/decisions/0010` superseding §3 of 0009. That is not
scope creep arriving late — it is the same rule this milestone was admitted under: an unmet
quality bar on work already delivered is not a new idea. What it does mean is that **the polish milestone's
"empty states for the existing pages" is now smaller than it was**, because the emptiest
page in the product has been dealt with.

**Branch** `feature/m12-shell` · **PR** `feat: replace the header with a sidebar shell and a signed-in home`

---

### m13 — Corrections in the transcript · **MERGED** — PR #15, `537869e`, 2026-09-06

**Goal.** A learner reading back a conversation sees each proposed correction on the words
it is about, not only in a block at the end.

**Why here.** Two reasons. The first is that this is not a new idea: `language_errors` has
carried `span_start` and `span_end` since m2, with a column comment saying they exist "so
the UI underlines the words rather than restating them", and no screen ever read them. m9
stored the offsets, m9's report listed the corrections, and the transcript stayed unmarked.
The second is that the owner asked for it on 2026-09-06, in the same breath as grammar
practice (m14): the corrections are that milestone's raw material, and a learner who
cannot see where a mistake happened cannot practise avoiding it.

**Deliverables.**
```
frontend/src/lib/corrections.ts                          the join and the placement, pure
frontend/src/lib/corrections.test.ts
frontend/src/components/Corrections.tsx                  the marks and the numbered list
frontend/src/components/Corrections.test.tsx
frontend/src/components/TurnBubble.tsx                   (extended: a `corrections` prop)
frontend/src/components/TranscriptPane.tsx               (extended: corrections keyed by turn)
frontend/src/app/(app)/sessions/[id]/Conversation.tsx    the join, from the report
frontend/src/components/{TurnBubble,TranscriptPane}.test.tsx   (extended)
docs/decisions/0012-corrections-in-the-transcript.md
docs/changelog.md · README.md · api/config.py (version)
```

**Decisions.**
- **The report is the source, not a new field on the turn.** The report already carries
  every correction with its `turn_id` and offsets, and the transcript page already holds
  the report. Joining the two in the browser adds no operation — 25 of 30 stays — and keeps
  a property the report already has: a correction is shown once the session has been
  ended and analysed, never mid-conversation. The persona does not correct the speaker on
  purpose, and the transcript should not either while the conversation is going.
- **The transcript's words win.** Offsets were located case-insensitively with flexible
  whitespace, so the stored quote can differ from the words at its offsets. What is marked
  is what the recogniser wrote; the check compares letters and digits only, the same
  normalisation the server used.
- **A correction whose offsets do not hold its words is listed and not marked.** Never an
  underline under the wrong words. The row says it is unmarked.
- **Overlaps are not nested.** The first by position is marked; the later one is listed
  with a number and no mark.
- **Two kinds of mark.** Counted corrections amber and solid; corrections on words the
  recogniser was unsure of, or that the model hedged on, dotted and grey, with the badge
  the report already uses. Absence is not a claim: a turn with no corrections renders no
  heading, because it may simply not have been analysed.
- **A numbered list under the bubble, not a tooltip.** A tooltip is unreachable on a
  phone and unannounced by a screen reader; the number in the text and the row under it
  are reachable by everyone, and the row carries the category, the explanation and
  whether it counts.

**Tests.** Placement is a pure function and is tested as one: text order, numbering, the
recogniser's spelling kept, offsets that do not hold the quote, offsets past the end, null
offsets, overlaps. The component tests assert that a mark covers the quoted words and
nothing else, that a doubtful correction is drawn differently and says why, and that an
unplaced one says it is unmarked. The bubble and pane tests assert corrections reach the
turn they were found in and no other, and that a turn with none renders no list.

**Done when.** A completed session's transcript marks every placeable correction on its
words and lists every correction under its turn, in both modes and at 375 px; lint,
typecheck, tests and build green. **Seen** on 2026-09-06 with a synthesised learner turn
posted through the real pipeline on a throwaway account: four corrections, two counted and
two marked as possible mishearings, on the words they quoted, at 1440 and 375 px in both
modes. The verification session was deleted afterwards so the corpus is unchanged. The
build could not run in that session — the container had no outbound network for the font
fetch — and **CI built it** on the PR and again on `main`.

**Explicitly not here.** No API change. No per-form accuracy, no rule layer, no way to
practise a correction — all m14. The report's own list is untouched.

**Branch** `feature/m13-corrections` · **PR** `feat: mark proposed corrections on the transcript where they happened`

---

### m14 — Grammar practice · **MERGED** — item 0 as PR #18 (`0.13.3`), items 1–5 as PR #19 (`0.14.0`, `01676db`), 2026-09-12

**Goal.** A learner can see which grammar they get wrong, in their own sentences, and
practise it — against a detector that is right often enough to be worth practising against.

**Why here.** The owner asked for it on 2026-09-06. It is a new idea, and R8 says new ideas
go to the PRD first: PRD §15.1 records it, dated. It comes after m13 because the
corrections are its raw material, and before polish (then m15) because a walkthrough of a product about
to gain a section is a recording made twice.

**What exists already, so none of it is rebuilt.** Every user turn is parsed for 26
grammatical features (`services/grammar.py`); every error is filed under nine closed
categories with a correction and an explanation; rollups carry errors per category per 100
words; the recommendation already picks a scenario from the weakest category and states
the reason; `language_errors.detector` allows `'rule'` and every row so far is `'llm'`.

**What is missing, in the order it has to be built.**

0. **The persona reading its brief aloud (Q16)** — placed here by the owner on 2026-09-10.
   Measured before and after with `make persona-adherence`, and the before is re-measured
   on the day rather than quoted from m11. **The last before, 2026-09-10: 19 of 20** — 10
   of 10 and 9 of 10 in the two `make eval` runs of PR #17. The probe is one utterance in
   one scenario, so a prompt tuned against it can pass it without generalising: write
   further phrasings, in other scenarios, **before** changing the prompt, and measure the
   before on all of them. If the fix is anything more than a prompt
   change — a check on the reply before it is spoken, say — the report has to show the
   model's rate and the product's rate separately, because a guard that hides the model's
   behaviour must not read as the model having improved.
   **DONE 2026-09-10, shipped on its own as `0.13.3`** — `docs/decisions/0013`. Every speaker turn reaches the
   model as quoted speech, and the reminder carries the brief's own sentence count and
   names the persona once. A prompt change and no guard, so one rate. Before, on ten
   phrasings in all eight scenarios, two runs: **59 of 200** gave its instructions away;
   after, **16 of 200**. On five phrasings written after the fix was chosen: **26 of 100
   → 1 of 100**. One phrasing got worse (0 → 5 of 20: the reminder is recited). One model
   only. The five are in the golden set, which now asks fifteen phrasings.
1. **The rule layer (Q15).** Subject–verb agreement and article omission, proposed from
   the parse with confidence 1.0 and no taxonomy gate. It raises precision without a bigger
   model, and it makes the category mix partly a property of the detector — which the
   report must say. Measured by `make error-precision`, per detector, before anything is
   built on it.
   **DONE 2026-09-11, committed on the branch as `886b37a`** — `docs/decisions/0014`. `api/services/rules.py`: agreement
   (`third_person_s`, `there_is_are`) and a missing article after `be` or a role after `as`
   (`missing_indefinite`, `missing_definite`), narrow on purpose — silent on collectives,
   partitives, units, coordinations, the subjunctive, uncountables, and a bare verb in a
   past context. A model proposal making a rule's correction is **superseded**: kept on
   `turns.analysis_rejects` as `superseded_by_rule`, not stored twice, not a refusal.
   **Measured:** on the golden set the rules propose **nothing** — it holds no agreement
   error and one article error in a shape they leave alone — so the product's figure is the
   model's, 0.500 over six, and S5 is undecidable as before. On **planted errors** in the
   repository's native English (2 454 words, no model, runs in CI): agreement **100 of 126**,
   articles **2 of 93**, **no wrong fix and no stray proposal**; no proposal on any
   unplanted native text, asserted. Found and fixed against 5 647 words of package prose:
   five false-positive shapes; that prose is now a development set. The session report and
   the transcript say which detector found each row ("grammar rule" badge); the progress
   caveat says the split by category is partly a property of the detector. **The
   done-when's "above the model's" cannot be decided on this corpus.** API 748 (715 pass,
   33 skip), frontend 210 / 31 suites, build green; no migration, no new operation, no new
   dependency.
2. **Per-form accuracy.** Nothing links an error to the form it happened in, so "your
   present perfect is 54 % right" cannot be computed. The join is a design decision: the
   parser's verb-phrase spans against the error's span, and only for `VERB_TENSE`.
   **DONE 2026-09-11, committed on the branch as `b3a8fe5`** — `docs/decisions/0015`. **The join is a comparison,
   not an overlap:** the correction is applied, the corrected text parsed, and the verb
   phrases under it compared before and after; what the correction changed is the form
   said and the form needed, **both kept** (`language_errors.form`, `corrected_form`,
   migration `0005`), because counting only what was said never shows a learner the
   present perfect they avoid. **Not only `VERB_TENSE`:** agreement and a missing
   auxiliary or copula join too — `she work` is a present simple built wrongly.
   **Accuracy is target-like use**, right over used plus needed-and-not-said, in the
   session report, every snapshot, and on the progress page beside each tense and modal —
   the count always, the percentage from ten (`PROGRESS_MIN_FORM_CONTEXTS`), *needed 2,
   never said* for an avoided form, and a caveat. **The counter was fixed first**: every
   present passive was a past simple, no do-supported negative or question was counted,
   and `had been V-ing` was a present perfect continuous (`past_perfect_continuous` is new
   in the vocabulary); old counter against new over 5 673 words of three corpora, **55
   phrases changed, every one a correction**. **Measured, no model:** 55 of 55 on the
   development set, **32 of 34 held out** (0.941 [0.809, 0.984]), 2 of 4 on the golden
   set's real turns — the parse of unpunctuated speech loses the verb — and **no wrong
   form on any set**, asserted. **What it cannot be is more right than the corrections:**
   on the live corpus the only two corrections that joined a form are the model's false
   positives. `make reparse` recounts and relinks stored turns with no model call. API
   876 (843 pass, 33 skip), frontend 216 / 31 suites, build green. *(Its percentage beside
   a verb form was withdrawn by item 3: the pages show the count.)*
2b. **The last turn in the report** — placed here by the owner on 2026-09-11, found while
   verifying item 1 (0014 §7). Ending a session skipped a turn the live analysis job had
   claimed, which is the usual state of the last one, so the report and the transcript's
   marks left out the last thing said; and the report's "open this session again to finish
   them" did nothing, because opening is a `GET`.
   **DONE 2026-09-11, committed on the branch as `b1a35c7`.** Ending waits for a claimed turn within the same 60 s —
   a job in the API's process is awaited, a claim held by a backfill in another process is
   polled — and a job cut off at the deadline is left running. The session page finishes a
   report written short when it is opened, once, then offers *Finish the report*. A job
   cancelled by the server stopping puts its turn back in the queue (it stayed `analyzing`
   for ever). End is disabled while a turn is being sent. **Measured on the stack**, one
   synthesised turn and End at once, the committed code against the fix: **0 of 3** reports
   held the turn before, **3 of 3** after, the end taking 4.15–4.80 s; a report left short by
   the old code was opened in a browser and finished with one request. The new tests fail
   with the fix removed. No migration, no new operation.
3. **A grammar section.** The learner's categories with their own sentences — original,
   correction, explanation — the forms they use and how correctly, and the scenario that
   elicits the weakest one. Whether it is a family under `/progress` or a rail entry of its
   own is decided when it is built.
   **DONE 2026-09-11, committed on the branch as `fad37c7`** — `docs/decisions/0016`. **A rail entry of its own,
   `/grammar`**, read from the corrections rather than the snapshots, because a snapshot
   holds no sentences; one new operation, `GET /grammar` (26 of 30). Every correction in
   the sentence it was said in, marked on the transcript's words, with the proposal, the
   detector and a link to the conversation; each verb form as *right 9 of 13* with the
   corrections behind it. **No percentage on any screen** — the progress page loses its
   *· 69 %* too — because the floor of ten is on the sample and the corrections under the
   count are the larger error; it comes back when detection precision is measured at the
   bar over twenty proposals. **The form to practise** is the one right least often among
   those with **10 contexts and 5 corrections** (`GRAMMAR_MIN_FORM_CORRECTIONS`: if half the
   corrections were wrong, five all wrong is one time in thirty), with a scenario at the
   learner's band; below it the page says how near the nearest form is. **On the live
   corpus no form is named** — the nearest, the future *will*, rests on the two false
   positives of 0015 §6. **Seen end to end** with three synthesised turns on a throwaway
   account, 1440 and 375 px, light and dark; it found three things that are not the page's:
   the model rewrote three correct past simples as past perfects, the agreement rule
   proposed `she says` where a past set one sentence earlier needed `she said`, and the
   recogniser heard `I fix` as `I fixed`. API 898 (865 pass, 33 skip), frontend 244 / 36
   suites, build green.
4. **One drill, and it is spoken.** Say it again: given one of the learner's own corrected
   sentences, record it, transcribe it, score it against the correction with the word
   error rate code that exists. Deterministic, no model call, measurable. A typed gap-fill
   would be a different product.
   **DONE 2026-09-11, committed on the branch as `d74ae6b`** — `docs/decisions/0017`. **From the grammar page, on a
   page of its own**: *Say it again* on every correction placed in its sentence opens
   `/grammar/drill/{id}`; two operations, `GET` and `POST /corrections/{id}/drill` (28 of
   30). The sentence is the one said, cut as the grammar page cuts it, **with every
   correction in it applied** — saying it with one fixed would practise the others — and
   the correction is shown first, with *Skip to the next* before the button. **Scored per
   correction, not per sentence**: a 13-word sentence said with its one mistake intact is a
   word error rate of 1 in 13, which reads as nearly right; so the alignment behind the
   word error rate is exposed (`wer.align`, the rate unchanged) and each correction gets what
   was heard where it belongs — the correction, the words as first said, something else, or
   nothing — with the sentence as counts. **No pass mark, no percentage, nothing stored.**
   **Measured, no model:** 89 hand-labelled learner sentences spoken by the `tts` voice as
   said and as corrected, heard by `small.en`, compared by the drill, in the speech
   recognition suite (`make asr-wer`): a mistake heard as its correction **2, 3, 2 and 1
   of 89** in four runs, the last the report's, a correct sentence heard as the mistake
   **0 of 89** in each; four more mistakes in each of runs 2 and 3 came back grammatical another way (`She don't` →
   `you don't`). One clear
   synthetic voice, so not a learner's rate. **Seen end to end** in Chromium with a
   synthesised WAV as the microphone — the first automated check to drive the browser's
   recorder; until now only a person holding the button had — at 1440 and 375, light and
   dark. API 927 (893 pass, 34 skip),
   frontend 267 / 41 suites, build green; no migration, no new dependency.
5. **Seeds that elicit the other categories.** Every scenario's target grammar is tense,
   modal or conditional; nothing is written to elicit articles, prepositions or false
   friends. Two or three scenarios that do, each with a `cefr_band` like every existing
   seed. *(Corrected 2026-09-10: this item used to add "`cefr_band` on every scenario and
   passage, because the band filter filters on nothing". That was never true — the column
   is NOT NULL from `0001`, and all 8 scenarios and 12 passages carry one: A2 ×4, B1 ×9,
   B2 ×6, C1 ×1.)*
   **DONE 2026-09-12, committed on the branch as `ab719d5`** — `docs/decisions/0018`. **A second declaration,
   `scenarios.target_errors`** (migration `0006`), in the taxonomy's category names,
   required like `target_grammar` and checked by the seed loader, because the parser's
   vocabulary has no word for an article or a false friend; the eight scenarios there were
   declare `VERB_TENSE`. **Three scenarios**: *Lost property office* (A2, articles — the
   first A2 scenario), *A courier who cannot find your door* (B1, prepositions), *Applying
   for a training programme* (B2, false friends, filed as `LEXICAL_CHOICE`). **Read** by
   the grammar page (*Practise these in …* under each declared kind, at the learner's
   band) and the error-category recommendation, and shown on the catalogue. **Measured,
   because "elicits what it declares" can only be seen through corrections**: sixty
   hand-labelled sentences, twenty per kind — said aloud by `tts`, **17–19 of 20** of each
   kind heard as said over four runs, prepositions repaired 6 times in 80, articles once,
   false friends never; handed to the detectors, filed under their kind **6, 12 and 6 of
   20** in all four (labelled correction 4, 9, 2), and 22 of 60 corrected sentences drew a
   proposal. Three persona probes; the suite asks nine, 6 of 9 clean in the run that added
   them and 8 of 9 in the report's. **Found and fixed on the way:** the agreement rule's first wrong
   fix on planted text, in the courier's own brief (`say your shift end` → `says`) — a
   lexical verb with its subject after it is left alone; old corpus unchanged at 100/126,
   2/93. **Seen end to end**: the personas recast the speaker's mistakes, and of ten
   mistakes spoken, one was filed under its scenario's kind, with a wrong correction.
   **Whether the scenarios draw these mistakes out of a learner is not measured** — it
   needs a person. API 940 (904 pass, 36 skip), frontend 270 / 41 suites, build green.

**Decisions to make, not made.** None left *(made at item 5: a scenario declares kinds of
mistake in the taxonomy's category names, and the declaration is checked by measuring
the path to a correction, not by the session report — 0018. Made at item 4: the drill lives on
a page of its own reached from the grammar page, and has no pass mark — 0017)*. *(Made at item 1:
a rule-layer row is marked on the transcript exactly as a model's is, and its row carries a
"grammar rule" badge — 0014 §6. Made at item 3: the grammar page is a rail entry of its
own, shows no percentage, and names a form at 10 contexts and 5 corrections — 0016.)*

**Tests.** Rule proposals against a fixture of known sentences and against the golden set;
the per-form join against hand-labelled turns; the drill's scoring against known
transcripts; the section's empty state for an account with no corrections.

**Done when.** `make error-precision` reports the rule layer's precision separately and
above the model's; a learner with corrections can open the grammar section, see their own
sentences, and complete one spoken drill that is scored; the new seeds exist and elicit
what they declare.

**Branch** `feature/m14-grammar` · **PR** `feat: add a rule layer, per-form accuracy and grammar practice` — items 1–5. Item 0 went first, in its own PR `fix: keep the persona in the scene when it is asked to recite its instructions` (`0.13.3`), at the owner's request: it was finished and measured, and the rest of the milestone is most of the milestone. m14's own PR is `0.14.0`.

---

### m15 — Articulation: saying an idea clearly · **MERGED as PR #20** (`53279df`, 2026-09-12) — built and measured 2026-09-12, committed as `f7f1a59`, `9a1d04c` and `8b1dd50`, `0.15.0`, `docs/decisions/0019`; *Make your point* on screen

**Goal.** A learner can answer a work question out loud in one go, and see how the answer
was built and how it was delivered — both counted by code — with a model's explanation and
a tighter version of their own answer beside the counts, never in place of them.

**Why here.** The owner asked on 2026-09-12 for training in articulating ideas clearly,
and chose, when asked, both halves: how an idea is built when spoken, and how it is
delivered. It is a new idea, so it went into PRD §15.1 first (R8). Before polish, now m16,
for the reason m13 and m14 went before it: a walkthrough of a product about to gain a
section is a recording made twice. After m14, because it reuses m14's drill — record,
transcribe, compare, store nothing that is not needed.

**What exists already, so none of it is rebuilt.** Delivery is measured: speech rate,
articulation rate, pause ratio, mean length of run, fillers per 100 words and response
latency, from word timings (`services/fluency.py`, PRD §7.1). **"Articulation rate"
already names one of them** — words over phonated time — so this milestone's feature needs
another name on screen, or the page will say "articulation" about two different things. The
dependency parse (`services/grammar.py`) gives clauses and the subordination index. The
session report is split by provenance — `measured`, `analysis`, `narrative` — and
`narrate_report` is the shape for a model call that never blocks the session and records
its own failure. The drill (m14 item 4) records one utterance and compares it.

**What is missing, in the order it has to be built.**

0. **The instrument, before any measure.** Hand-labelled answers to the prompts, written
   the way the recogniser writes and before any code — as the verb forms and the three
   kinds of mistake were — each with its structure marked: the signposts by what they do,
   the example, the closing line, the sentences, the restarts. A development set and a
   held-out set. And what reaches the transcript at all: answers with restarts and fillers
   spoken by the `tts` voice and heard by `small.en`, counting what survives. The fluency
   code already says the recogniser drops most `um`s; whether it drops a restart the same
   way decides whether restarts can be counted, and it is measured, not assumed.
   **DONE 2026-09-12** — `api/tests/answer_labels.py`: 24 development answers (2 115
   words), 16 held out (1 469), 37 readings of the words with a second use, 12 answers to
   say aloud; the bars written into the same file first. Said by `tts`, heard by
   `small.en`, four runs, the last in `docs/evaluation.md`: fillers **21, 22, 21 and 21 of
   24** written down, repeats **12, 13, 13 and 13 of 13**, restarts **9, 8, 8 and 8 of 9**,
   signposts 52 of 52 every time, the sentence count within one in **10, 11, 10 and 11 of
   12** — both recogniser bars met in all four. A synthetic voice says *um* as a word, so this is not a person's hesitation.
1. **How an answer is built, counted by code** (`services/structure.py`). Signposts from
   closed lists, by what they do — a reason (*because*, *since*, *that's why*), an example
   (*for example*, *for instance*, *such as*), a sequence (*first*, *then*, *finally*), a
   contrast (*but*, *however*), a close (*so*, *in short*, *overall*) — with the parse
   deciding a word that has another use: *so* as a result and not *so good*, *since* as a
   reason and not a time, and *like* never. Sentences and words per sentence, with the
   caveat that a sentence boundary is the recogniser's punctuation; restarts and repeated
   words. Each measure scored against item 0's held-out set, with its interval, before any
   screen shows it; a measure below its bar is not shown.
   **DONE** — held out, precision / recall: reasons **0.957 / 1.000**, examples 1.000 /
   0.909, steps 0.933 / 1.000, contrasts 1.000 / 1.000, summing up 1.000 / 1.000, repeats
   0.923 / 1.000; **restarts 0.636 / 0.636, below the bar — counted, stored, not shown**.
   `structure.SHOWN` decides, and CI asserts every measure in it clears its bar. The
   held-out set is unspent; the same author wrote it and the counter.
2. **The drill: one spoken answer to a prompt.** A dozen prompts across the scenario
   categories — explain a failure, justify a choice, walk through a process, recommend
   something — each with a band and a time limit of 60 to 120 s, seeded and validated like
   the scenarios. One recording, no persona and no reply. The page shows delivery and
   structure, each with its caveat. Whether this is a third session mode (`ALTER TYPE
   session_mode ADD VALUE`, a migration) or a table of its own, and whether prompts are a
   table or scenarios with a flag, is decided when built; at most two new operations.
   **DONE** — *Make your point* at `/answers`, a rail entry of its own; **13 prompts**, four
   kinds, A2–C1, 60–120 s; **tables of their own**, `answer_prompts` and `answers`
   (migration `0007`), not a session mode; **`GET` and `POST /answers`, 30 of 30**. Press to
   start and to stop, stopped by the time limit; the recording is transcribed and dropped.
3. **Feedback from the model, beside the counts.** One call after the answer, in
   `narrate_report`'s never-raises shape: what to lead with, which point has no reason or
   example, and the speaker's own answer said in fewer sentences. **The rewrite is checked,
   not trusted**: content words it introduces that the speaker never said are counted, a
   rewrite over the limit is refused, and the refusal is counted — the taxonomy's
   rejection rate, for a new kind of output. It may not comment on how the answer sounded
   (P2), and nothing it writes reaches a chart (P1).
   **DONE** — the limit is more than **2** new content words, chosen on 12 development
   rewrites; on 12 held out the check withheld **6 of 6** that added a fact and showed **6
   of 6** faithful ones. The model on all 40 answers: with the first instruction its
   shorter version was withheld **34 of 40** (13 of 16 held out) — paraphrase, not
   invention; with the instruction asking for the speaker's own words, **9 of 40, 2 of 16
   held out**. Every shorter version had fewer sentences; no note about sound dropped.
4. **Say it again, tighter.** A second attempt at the same prompt, compared with the first
   on the same counts, side by side. No pass mark.
   **DONE** — `answers.again_of`; the two side by side on the same counts, no arrow and no
   colour. Seen in Chromium with a synthesised answer as the microphone, 1440 light and
   375 dark; it found duplicate keys in the shared chart, fixed.
5. **Over time — only what has a better end.** Fewer restarts and shorter sentences may be
   better; more signposts is not, because counting *because* rewards saying it, the trap P3
   names for tense. So signposts are drawn and never judged, as speech rate is, and which
   measures reach `/progress` is decided with item 1's numbers in hand.
   **DONE** — on the answers page, one point per answer: speech rate, time paused, fillers
   and words said twice per 100 words, words per sentence, signposts. Only fillers and words
   said twice get a direction; a rate is withheld under 50 words. **Nothing reaches
   `/progress`.**

**Decisions to make, not made.** None left *(made 2026-09-12, 0019: the name is *Make your
point*; tables of their own and prompts a seeded table; the history is on the answers page
and nothing reaches `/progress`, with a direction for fillers and words said twice only)*.

**Not in it.** Intonation, stress and prosody: PRD §15 keeps them out of v1 and nothing here
scores them. Whether an answer is right: the model may not judge content, only say where
the speaker's own structure is thin.

**Tests.** Each structure measure against the labelled sets; the parse's reading of *so*,
*since* and *like* against sentences written for it; the rewrite check against rewrites that
add a fact; the drill end to end in Chromium with a synthesised WAV as the microphone.

**Done when.** Each structure measure is reported with its held-out precision and recall
and shown only above its bar; what of a restart and a filler survives the recogniser is
measured; a learner can pick a prompt, answer out loud, see delivery, structure and the
model's feedback, and answer again to compare; the rewrite's invented-content rate is
measured and in `docs/evaluation.md`.

**Branch** `feature/m15-articulation` · **PR** `feat: add a spoken answer drill that counts how an idea is built and delivered` · `0.15.0`. The plan and PRD edits that admit it are the branch's first commit.

---

### m16 — Polish, documentation, demo · **CODE COMPLETE** — started 2026-09-12 at the owner's request *(was m13 until 2026-09-06, m15 until 2026-09-12)*

**Goal.** A stranger clones the repo, runs it, and understands the engineering.

**Why here.** Last. Documentation written before the system is finished documents an
intention.

**Already delivered, ahead of the milestone.** PR #16 (`0.13.1`) fixed the part of S1 that
was broken rather than unpolished: Ollama is a stated prerequisite, `make setup` is the
first run in one command, `make llm-check` and the `llm` row on `/health` and `/status`
say when the model is missing and name the pull command, `.env` reaches the API, and the
README has a prerequisites table and a troubleshooting table. PR #17 (`0.13.2`) ran it
cold — a `git archive` copy, empty volumes, a BuildKit builder with no cache — and
measured it: **`make setup` 7 min 12 s with zero manual steps, Whisper loaded at 8 min
58 s**, one spoken turn end to end, five containers in 1.94 GiB. **S1's five minutes are
missed**, and the build is 401 s of the 432 — dependency downloads, the API's
`pip install` alone 346 s. So S1 is no longer unverified; it is measured and unmet.

**Deliverables.**
```
README.md                              (rewritten against measured reality; the first screen
                                        a picture, three lines, and the Quick start)
docs/{architecture.md,data-model.md,evaluation.md}   (finalised)
docs/changelog.md
demo/                                  the walkthrough recorder — run, and kept out of the
                                        repository (D119); the .mp4 goes to the post and the
                                        still to the README
docs/{how-it-works.md,measurements.md,limitations.md}   the README's long sections, moved
                                        word for word (D120)
CONTRIBUTING.md, SECURITY.md, CODE_OF_CONDUCT.md, .github/ISSUE_TEMPLATE/, .github/pull_request_template.md
                                        the files a contributor looks for (D120)
eval/golden/pron/RECORD.md             the recording protocol, moved out of gitignored spike/
                                        so a clone can record S4's pairs — read it for
                                        anything personal before it is tracked
frontend/src/app/**                    empty states, loading skeletons, error boundaries
api/main.py                            OpenAPI descriptions and examples
api/routers/progress.py                GET /progress/export — FR-25, the one requirement with nothing behind it
Makefile                               (all targets documented)
```

**Done by hand on GitHub, not by a commit.** A custom social-preview image — a link to the
repository on LinkedIn renders GitHub's generic card without one — and repository topics.

**The items, in the order they are built** *(written 2026-09-12, when the milestone
started)*.

0. **The record first.** m15 merged as #20 in this plan, these items, v1.18. It rides in
   the branch's first commit, with item 1. **DONE 2026-09-12.**
1. **`GET /progress/export`** (FR-25). The caller's whole history as one JSON document:
   the account without its password hash, every session with its turns, each turn's
   measurements and corrections, every reading with its scored phones, every spoken
   answer, and the weekly snapshots. Recordings are referenced by their `GET /audio/{id}`
   address rather than embedded — a JSON file is no place for megabytes of waveform, and
   that address is ownership-checked like everything else. Sent as a download, scoped to
   the caller, taking no user id, like every progress operation. 31 operations. A link to
   it where the account is shown.
   **DONE** — `models/export.py` and `services/export.py`, one query per table; a link
   under the account's email in the rail. **31 operations.** On the live database the
   export of each of the 6 accounts counts exactly what the database holds, the largest
   198 594 bytes in 17 ms. Seven tests, and the ownership test names the route.
2. **Loading, failure and not-found, designed.** No route has a `loading.tsx`, an
   `error.tsx` or a `not-found.tsx`: a slow server render leaves the previous page on
   screen, and a thrown one shows Next's generic screen. A skeleton per section, shaped
   like the page it stands in for; one error boundary for the signed-in sections that says
   what failed and offers a retry; a not-found in the product's own words. The empty states
   exist and were designed (m10, m12) — each is checked, not rebuilt.
   **DONE** — a `loading.tsx` for each of the 12 signed-in pages and one for the group,
   shaped as cards, a list, figures or a document; `error.tsx` in the shell and at the root,
   `global-error.tsx`, and `not-found.tsx` in the shell and at the root; a test that reads
   the tree and names any page without a loading state of its own. **One cost:** a
   not-found decided after streaming has begun is sent as 200 — `/sessions/abc` answers 200
   with *Nothing here*, an unmatched address 404.
3. **The OpenAPI document as a reader meets it.** Every tag described, every operation
   with a summary, and a test that fails on an operation without one.
   **DONE** — ten tags described; each summary is the first sentence of the operation's
   docstring, set once in `main.py`; three docstrings rewritten and one written
   (`GET /passages` had none); `tests/test_openapi.py`.
4. **The recording protocol in the repository.** `eval/golden/pron/README.md` already
   carries the lines to say and the conversion; what only `spike/RECORD.md` has — the
   check that the files are 16 kHz mono, the silence at each end, a recorder to use — is
   folded into it, and its pointer to `spike/` goes. `RECORD.md` itself is not copied: it
   carries a path from the machine it was written on. Every Make target is already in
   `make help` (40 of 40), which is checked rather than rebuilt.
   **DONE** — the silence at each end, a recorder, `raw/` (now ignored by git) and an
   `afinfo` check folded into `eval/golden/pron/README.md`; the ASR set's README and the
   pronunciation manifest point there instead of at `spike/`. `make help`: 40 of 40.
5. **S1, re-measured cold** — #17's method: a `git archive` copy, empty volumes, a
   builder of its own. Then decided: a faster first build, if the build can be shortened
   without adding a tool to the stack, or the miss stated as a limitation with its figure.
   Either way the README carries the new number.
   **DONE** — 2026-09-12, a copy of `53279df`: **`make setup` 153 s, Whisper loaded at
   163 s — met.** The build is unchanged; the API's `pip install` took 88 s, against 346 s
   on 2026-09-10, and nothing is compiled from source. One synthesised turn heard verbatim
   and answered in 3.5 s; 1.74 GiB. **Decided: no change to the build** — the first miss
   was the connection, and both runs are in the README. The live stack was stopped for the
   run and restored; nothing of the copy survives.
6. **The walkthrough.** `demo/` checked against the product as it is now — three
   sections were added after it was written — and run. Its `package.json` stops naming a
   file that is not in the repository. The video and its poster go to the README and the
   post, never into git; the clips it replays are the owner's voice, used with the owner's
   say-so.
   **DONE** — **the owner chose the project's synthetic voice** (D116): `demo/voices.sh`
   writes the learner's lines, the captions say so, and the scenes count scenarios and
   passages off the page and film the grammar page and *Make your point*. Filmed at
   1280×720: turns answered in 4.0 s, the report in 1.8 s, the reading scored in 12.3 s, the
   answer counted with its feedback in 3.8 s. Two bugs found by filming and fixed — a text
   match that stopped the clock at 0.0 s, and clips written into the folder a take empties.
   **Revised:** the still on the README's first screen is committed (D117); the video is
   not. **Revised again, at the owner's request (D118):** two portrait cuts for LinkedIn,
   1080×1350, narrated by a local Piper voice over the app's own sound — `demo/piper.sh`,
   `demo/narration.cjs`, `demo/mix.cjs`, and `AUDIO=` in `to-mp4.sh`. The short cut is one
   turn and its report; the full one is every section. **Taken out of the repository, at
   the owner's request (D119):** the version commit stops tracking `demo/`, which is
   ignored from then on; the recorder stays on the machine that records, and the
   squash-merge never puts it on `main`.
7. **The README and the docs, against the live system.** The first screen a picture, three
   lines and the Quick start; the status line, the table of what does not exist yet and the
   repository map brought to what is true; `docs/architecture.md` and
   `docs/data-model.md` through m15. Every S-criterion in one table, S1 to S10, each with
   the command or the person that settles it.
   **DONE** — the first screen is a still from the take, three lines and the Quick start; a
   table of all ten criteria with where each stands and what settles it — S1, S3, S6, S8 and
   S9 met, S2 met on a quiet machine and missed on a busy one, S4 never run, S5 undecidable,
   S7 not met, S10 a rule; the gaps table, the repository map and every figure the cold run
   and the suites re-measured brought to 2026-09-12. `docs/architecture.md` describes the
   frontend as it is and the export; `docs/data-model.md` says what is not there.
   `docs/decisions/0020`.
   **Reshaped at the owner's request (D120):** the README in the shape of a large
   open-source project's — badges, features, known limitations, documentation,
   development, contributing, acknowledgements — the four feature sections, the measured
   table with its prose, and the table of what does not exist yet moved word for word into
   `docs/how-it-works.md`, `docs/measurements.md` and `docs/limitations.md`; CONTRIBUTING,
   SECURITY, a code of conduct and issue and pull-request templates added.
   **Rewritten by component, at the owner's request (D121):** the reference documents
   describe the system as it is — `how-it-works.md`, `limitations.md`, `architecture.md`
   and `measurements.md` organised by component, in the present tense, with no milestone
   ids, and a sampled figure as one range across runs; decision records frozen.
8. **The PR.** `make eval` at the commit holding the code, `0.16.0`, the changelog.
   **DONE in the tree** — `make eval` at `0174d7f`, all five suites, 16 min 24 s: S4–S7
   unchanged, and the sampled figures that moved on the same code recorded beside the
   earlier runs (D102). `0.16.0`; the changelog. Checked in Docker after the bump: API
   1 049 (1 011 pass, 38 skip), `make lint`, frontend 316 / 49, `tsc`, ESLint, and CI's
   harness step on a copy. The owner's: §A.27, then §B.15.

**Decisions.**
- Every number in the README is counted from the live system at write time — operation count from `app.openapi()`, test count from pytest, WER and GOP separation from `make eval`.
- The README states the honest limitations: local-model accuracy versus hosted, the GOP caveats of PRD §7.5, and the minimum machine that actually runs it.
- A recorded walkthrough, because a reviewer will not install Ollama to evaluate a portfolio project.
- Empty states matter disproportionately: a new user's progress page has no data, and "not enough data yet — practise 5 more times" is the correct design, not a blank chart.

**Done when.** A clean clone reaches all-healthy with no manual editing (criterion S1) —
already true, and timed once at 7 min 12 s. m16 decides between making the first build
faster and stating the miss as a limitation; either way the README carries a re-measured
figure. Every S-criterion is verified and recorded, and the walkthrough is recorded.

**Branch** `feature/m16-polish` · **PR** `feat: finalise documentation, demo and empty states`

### m17 — Security and dependencies · **IN PROGRESS** — started 2026-09-12 at the owner's request; items 0–5 in the tree

**Goal.** Someone who runs Trivy on the repository, reads its pins or opens its security
settings finds nothing out of date that could be current, and nothing exposed that need
not be.

**Why here.** After polish, and because of it: a project published for strangers to read
is judged on its dependencies too. The owner asked for a review of "the libraries we use
and the language versions we have, as well as with Trivy scans" — "it doesn't look good for
an open-source project to have outdated dependencies and pose a security risk" — and it
scored **41 of 100**: 3 CRITICAL and about 100 HIGH in each Python image, 4 and 45 in the
frontend's; python-multipart, Starlette and PyJWT with published advisories, two of them
reachable before the login check; every container root, every port on every interface,
the database's with a development password; Next.js 15 at the end of its support on
2026-10-21; no Dependabot, no scan in CI, actions pinned to tags, private vulnerability
reporting off while `SECURITY.md` points at it. The owner then asked for pnpm in place of
npm, and for the fixes to start.

**Deliverables.**
```
infra/*/requirements.txt, infra/api/requirements-dev.txt   the web stack current; test tools out of the runtime image
infra/*/Dockerfile                     unprivileged, pinned bases, fixes applied at build, health checks inside
docker-compose.yml                     127.0.0.1 ports, postgres:16.15, the volume-owner job, build targets
frontend/{package.json,pnpm-lock.yaml,pnpm-workspace.yaml}   pnpm 12 and its supply-chain settings
.github/{workflows/ci.yml,dependabot.yml}   read-only token, pinned actions, Trivy, Dependabot
api/main.py, api/tests/test_{ownership,openapi}.py   the routers walked explicitly
ruff.toml, api/ruff.toml               the lint's rules named
docs/decisions/0021                    what was decided, and measured
```

**The items, in the order they are built** *(written 2026-09-12, when the milestone
started)*.

0. **The record.** This milestone, and `docs/decisions/0021`. **DONE.**
1. **The Python web stack, current, in all four services.** FastAPI (and with it
   Starlette), uvicorn, python-multipart; PyJWT and the database libraries in the API;
   the test and lint tools in a stage of their own.
   **DONE** — FastAPI 0.141.1, Starlette 1.6.0, uvicorn 0.52.4, python-multipart 0.0.32,
   PyJWT 2.14.0; pytest 9.1.1, pytest-asyncio 1.4.0, ruff 0.16.7, black 26.5.1 in
   `requirements-dev.txt`. **Found:** FastAPI 0.137 stopped copying routers into
   `app.routes`; two ownership tests failed, and the summary loop and its test had quietly
   stopped doing anything — the routers are walked explicitly now, and a test holds the
   walk to the OpenAPI document (D123). ruff's wider default is pinned back to the rules
   the code was written against, black 26 applied (D124). Starlette's renamed 413 and 422
   constants, Alembic's `path_separator`, a test key PyJWT called too short. **1 050 —
   1 012 pass, 38 skip, no warnings.**
2. **The images.** An unprivileged account; the base pinned to its exact release; the
   distribution's fixes at build time; no package installed to answer a health check.
   **DONE** — uid 10001 in the four Python images, `node` in the frontend; `volume-owner`
   hands existing volumes over, symlinks included (D125). Trivy: api, asr, tts **0 / 44**
   from 3 / ~100, none fixable; pron 0 / 45; frontend **0 / 0** from 4 / 45. Sizes: api
   826 MB, asr 790, tts 722, pron 1.84 GB.
3. **Compose.** Every port on `127.0.0.1`; Postgres pinned to 16.15, Debian kept.
   **DONE** — the stack brought up as `make setup` does: every service healthy, every model
   loaded under the new account, a recording written to `/audio`.
4. **The frontend on pnpm and Node 24.** The owner's addition. pnpm 12 with a day's wait,
   no weaker provenance than before, no install scripts by default; Next and React at the
   latest patch of their lines; the vulnerable transitive copies moved.
   **DONE** — pnpm 12.4.1; two trust exceptions, each checked by hand, out of 874 packages
   scanned (D126); npm, corepack, and pnpm's store and cache out of the image — 1.05 GB,
   from 1.66 GB; Next 15.5.25, React 19.1.9, PostCSS overridden under Next, `qs` 6.16.0;
   `pnpm audit` finds nothing. Jest 316 / 49, `tsc`, ESLint, `next build` green.
5. **CI and Dependabot.** A read-only token, actions pinned to commits, a Trivy job,
   Dependabot for every ecosystem the repository has.
   **DONE in the tree** — Trivy from its image by digest (D127), its gate command run here:
   exit 0. `dependabot.yml` valid against the published schema. **Never run on GitHub:**
   nothing is pushed.
6. **Next 16 and React 19.3**, before Next 15's support ends on 2026-10-21.
   **DONE in the tree** — Next 16.3.5, React 19.3.0, `eslint-config-next` 16.3.5 and its
   flat configs; nothing in the code used what Next 16 removes. pnpm held the install until
   the last of Next's platform binaries was a day old. The PostCSS override is gone (Next 16
   pins a fixed release); `WATCHPACK_POLLING` is gone (Turbopack in the container sees a
   host edit and a deletion without it). **Two React Compiler rules off** — `refs` 15,
   `set-state-in-effect` 6 — for D124's reason (D128). Jest 316 / 49, `tsc`, ESLint, the
   Turbopack build; every signed-in page rendered with a real session cookie, the account
   deleted after; `pnpm audit` nothing; the CI Trivy gate 0. No `AGENTS.md` or `CLAUDE.md`
   written.
7. **The model libraries** — torch 2.14, transformers 5.17, onnxruntime 1.30, piper-tts
   1.8 — one at a time, each with `make eval`, because each changes what is measured.
   **NOT STARTED.**
8. **The PR.** `0.17.0`, the changelog, the review re-scored. On GitHub, by the owner:
   private vulnerability reporting, Dependabot alerts and security updates, a ruleset on
   `main` that requires CI.

**Decisions.** D122–D127, `docs/decisions/0021`.

**Done when.** CI's four jobs green on the PR, the Trivy job among them; items 6 and 7
done, or deferred by a record that says why; the review re-scored from the live system; the
GitHub settings on.

**Branch** `feature/m17-security`, stacked on `feature/m16-polish` · **PR** `fix: bring dependencies current, run every service unprivileged, and scan in CI`

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
                                                                          └─ m12 shell
                                                                              └─ m13 corrections in the transcript
                                                                                  └─ m14 grammar practice
                                                                                      └─ m15 articulation
                                                                                          └─ m16 polish
                                                                                              └─ m17 security and dependencies
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
| R8 Scope creep | this document | m1–m16 fixed; new ideas go to PRD §15. m12 was added after m11 and the reason is recorded in it: an unmet quality bar on work already delivered is not a new idea. m13 and m14 were added on 2026-09-06 at the owner's request: m13 is the stated purpose of two columns that already existed, and m14 is a new idea that was recorded in PRD §15.1 before it was scheduled. m15, articulation, was added on 2026-09-12 at the owner's request the same way — PRD §15.1 first — and placed before polish, now m16. m17, security and dependencies, was added on 2026-09-12 at the owner's request after a scored review, for m12's reason: an unmet bar on work already delivered |

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
| m12 | 3–4 | The sidebar is the easy half; deciding what belongs on a signed-in home is not |
| m13 | 1 | The join already existed in the report; the work is placement and the tests |
| m14 | 4–5 | The rule layer has to be measured before anything is built on it |
| m15 | 4–5 | The labelled answers and the parse's reading of the signposts are most of it |
| m16 | 3 | |
| m17 | 2–3 | Mostly mechanical; a framework's changed internals and the trust policy were not |
| **Total** | **~52–59** | |

---

## 11. First three actions

**Superseded — m0 through m13 are merged.** Kept for the record; the live version is below.

1. ~~Set the git identity.~~ Done.
2. ~~Run the **m0 spike**.~~ Passed 2026-08-29.
3. ~~Create the repository and land m1.~~ Done; `main` is at PR #18.

### The next actions

**m17, security and dependencies, items 0–5 are committed** on `feature/m17-security` as
`1128062` and `a303e66` (§A.28, §A.29), stacked on `feature/m16-polish` at `0a58955`.
Item 6, Next 16 and React 19.3, is done in the tree for §A.30; then item 7, each model
library with `make eval` on a clean tree; the PR last. m16's own PR, §B.15, is still the owner's to open, and m17 stacks
on it.

**`main` is PR #20 (`0.15.0`, `53279df`)**: all of m15 — `d75accb`, `f7f1a59`, `9a1d04c`
and `8b1dd50` — squash-merged on 2026-09-12, CI green on all three jobs. **m16, polish,
is code complete on `feature/m16-polish`**, cut from `53279df`; its items are in m16 above.
`demo/`, the walkthrough recorder, was tracked in `836d430` and `0174d7f` and is kept out
of the repository from the version commit on (D119): ignored, on the machine that
records, and never on `main`, because the branch is squash-merged.

**Merged as PR #20, 2026-09-12:**
- ~~m15's PR, `0.15.0`.~~ `make eval` with all five suites, 15 min 36 s, at `9a1d04c`. The
  criteria are unchanged — S4 not run, S5 0.500 over six, S6 1.72 %, S7 not met. The
  answers suite is identical to every run before it (9 of 40 shorter versions withheld, 2
  of 16 held out); the spoken answers are recorded as a fourth run beside three, both
  bars met in all four. The PR body is `.pr-bodies/m15-articulation.md`.

**Done on `feature/m15-articulation`, 2026-09-12, committed as `f7f1a59` and `9a1d04c`:**
- ~~m15 items 0–5.~~ The labelled answers and the bars first; the counter, every shown
  measure above 0.90 / 0.75 held out and phrases started again below it, not shown; *Make
  your point* at `/answers`, 13 prompts, `GET`/`POST /answers`, 30 of 30; the model's
  feedback with its shorter version checked for new words; say it again side by side; the
  history on the answers page. `docs/decisions/0019`.

**Merged as PR #19, 2026-09-12:**
- ~~m14's PR.~~ `make eval` with all four suites, 11 min 17 s. The criteria are unchanged —
  S4 not run, S5 0.500 over six, S6 1.72 %, S7 not met — and the planted errors, the form
  join and the three kinds' detection are identical to the milestone's runs. **Three
  figures moved, and the docs follow the report:** an article mistake was heard as its
  correction for the first time (1 of 80 over four runs; prepositions 6 of 80), the drill's
  blind spot was 1 of 89, and the persona suite was 8 of 9 clean. Version `0.14.0`; the PR
  body is `.pr-bodies/m14-grammar.md`.

**Done on `feature/m14-grammar`, 2026-09-12, committed as `ab719d5`:**
- ~~m14 item 5, the seeds.~~ Three scenarios — articles (A2), prepositions (B1), false
  friends (B2) — and `scenarios.target_errors` (migration `0006`) for every scenario to
  declare the kinds of mistake it draws out; the grammar page and the recommendation link a
  kind to a scenario that declares it. **Measured on sixty labelled sentences:** heard as
  said 17–19 of 20 per kind; filed under their kind by the detector **6, 12 and 6 of 20**.
  The agreement rule's wrong fix in the courier's brief found and guarded.
  `docs/decisions/0018`.

**Done on `feature/m14-grammar`, 2026-09-11, committed as `d74ae6b`:**
- ~~m14 item 4, the spoken drill.~~ *Say it again* on each correction of the grammar page:
  the sentence as said with every correction in it applied, the correction shown first
  with a way to skip it, and what the recogniser heard where each correction belongs. No
  pass mark, no percentage, nothing stored. `GET`/`POST /corrections/{id}/drill`, 28 of
  30. **Measured:** a mistake said by a clear synthetic voice was heard as its correction
  2, 3, 2 and 1 times in 89 over four runs, a correct sentence as the mistake never.
  `docs/decisions/0017`.

**Done on `feature/m14-grammar`, 2026-09-11, committed as `b1a35c7` and `fad37c7`:**
- ~~m14 item 3, the grammar page.~~ `/grammar`, a rail entry of its own: the learner's
  corrections in their own sentences, grouped by kind; each verb form as a count with the
  corrections behind it; **no percentage on any screen**, the progress page included; a
  form named for practice only at 10 contexts and 5 corrections, with a scenario at the
  learner's band — none qualifies on the live corpus. `GET /grammar`.
  `docs/decisions/0016`.
- ~~m14 item 2b, the last turn in the report.~~ Ending waits for a turn the live job has
  claimed; the session page finishes a report written short; a cancelled job releases its
  turn; End is disabled mid-send. **0 of 3 → 3 of 3** reports holding the last turn.

**Done on `feature/m14-grammar`, 2026-09-11, committed as `b3a8fe5` and `886b37a`:**
- ~~m14 item 2, accuracy per form.~~ Each correction to a verb's form carries the form it
  was said in and the form it needs; the counter of forms fixed first. Join: **32 of 34
  held out**, no wrong form. Migration `0005`; `make reparse` applied. `docs/decisions/0015`.
- ~~m14 item 1, the rule layer (Q15).~~ Agreement and a missing article, proposed from the
  parse. On planted errors: agreement **100 of 126**, articles **2 of 93**, no wrong fix.
  The golden set holds nothing they cover, so S5 is unchanged at 0.500 over six.
  `docs/decisions/0014`.

**Done in PR #17, 2026-09-10:**
- ~~Verify S1 cold.~~ `make setup` 7 min 12 s, Whisper loaded at 8 min 58 s — **missed
  against five minutes**, by the build. The figures are in the README.
- ~~Make the harness name a failure.~~ `eval/run.py` passes `-rfEs` and sets `COLUMNS`,
  so a failing suite is reported by test name and reason. `docs/evaluation.md` is
  regenerated and committed. Found on the way and fixed: a test that `make test` always
  skipped, and `make down` leaving the profiled services behind.

**Done in the Q16 PR, 2026-09-10 (`0.13.3`):**
- ~~m14 item 0, Q16.~~ Speaker turns reach the model as quoted speech; the reminder names
  the persona once and carries the brief's own sentence count. 59 of 200 → **16 of 200**
  gave its instructions away; 26 of 100 → **1 of 100** on five phrasings written after the
  fix. One phrasing worse, one model only (`docs/decisions/0013` §7). The persona suite
  asks fifteen phrasings. `docs/evaluation.md` regenerated.

**Decided by the owner, 2026-09-10:** m14 next and the LinkedIn post after polish (m15 then, m16 now) — this plan
puts m14 first on purpose, because a walkthrough of a product about to gain a section is
a recording made twice — Q16 as m14's item 0, and **Q16 merged on its own** rather than
waiting for the rest of the milestone. **2026-09-11:** the end-of-session defect as an m14
item (2b) rather than a PR of its own.

1. ~~Merge the Q16 PR and cut a fresh `feature/m14-grammar`.~~ Done by the owner: `49bdeea`.
2. ~~Commit items 1 to 4 on the branch.~~ Done by the owner: `886b37a`, `b3a8fe5`,
   `b1a35c7`, `fad37c7`, `d74ae6b`.
3. ~~m14 item 5, the seeds.~~ Built and measured; `docs/decisions/0018`.
4. ~~Commit item 5 on the branch.~~ Done by the owner: `ab719d5`.
5. ~~m14's PR, `0.14.0`.~~ Merged as #19, `01676db`; CI green on all three jobs. On any
   other checkout: `make migrate`, then `make seed`; on a database with stored turns,
   `make reparse` then `make rollup`.
6. ~~m15, articulation.~~ Built and measured; committed by the owner as `d75accb`,
   `f7f1a59` and `9a1d04c` (§A.21, §A.22).
7. ~~m15's PR, `0.15.0`.~~ Merged as #20, `53279df`; CI green on all three jobs. On any
   other checkout: `make migrate`, then `make seed`.
8. **m16, polish** — asked for by the owner on 2026-09-12. Items 0 to 8 are in m16 above.
   Code complete; §A.27 and §B.15 are the owner's.

**A finding from item 5, not yet a task.** The detector files most article and false-friend
mistakes under another kind — 8 and 9 of 20 labelled ones, against 6 each filed under
their own — and proposes on a third of correct sentences (22 of 60). A scenario can only
show the kind it declares through corrections of that kind, so for those two scenarios the
detector, not the scenario, is the limit (0018 §4). And the personas recast the speaker's
mistakes — *so you attended a conference* — which no guardrail counts (0018 §6).

**A finding from item 4, not yet a task.** Some mistakes never reach the detector: in the
two measuring runs read one by one, 7 and 6 of 89 mistakes said by a clear synthetic voice
came back from the recogniser as grammatical English — as the correction, or another way
(`my manager say` → `My managers say`). That is one reason detection recall is low, measured for the first
time — on the clearest voice there is — and it is the recogniser's, not the detector's
(0017 §6).

**A finding from item 3, not yet a task.** The agreement rule proposed `she says` for
`she say` in a narrative whose past was set a sentence earlier; `she said` was needed. The
rule's past-context silence reads one sentence. It was synthesised speech of a sentence
written for the check, not a learner's, and fixing it needs a new held-out set written
first (0016 §7).

**One open finding, not yet a task.** The 10 s scoring-budget test for a passage-length
reading failed in one full `make eval` on 2026-09-10 that ran 2.4× slower end to end than
the next, and passed in four other runs at 4.0–4.4 s. Why that run was slow is not shown.
If it fails again, the report now carries the figure it failed by.

The person-only list below is unchanged, and it is still the only thing that moves S4, S5
and S7.

**One thing PR #13's merge taught, and it is not about any milestone.** A commit made
straight onto `main` is not finished until `git push` has run. `4508bf4` was not pushed, so
the squash absorbed it and the next `git pull --ff-only` refused on a genuine divergence.
Nothing was lost, and one command proved it — `git diff <pr-head> origin/main`, empty. The
sheet's §D sections now end in a push and a check for exactly this reason.

**What m16, polish, must not do:** rewrite the README into something warmer than the measurements
support. Three criteria are unmet, one has never run, and one is a role-integrity failure
found by this project's own harness. A portfolio README that leads with those is a
stronger document than one that buries them, and it is the only one consistent with S10.

Three things still need a person, and none of them blocks m15 or m16 — but two are now what
stands between this project and three of its own success criteria:

- **Recordings for the pronunciation golden pairs** — about five minutes, protocol in
  `eval/golden/pron/README.md`. Until they exist, the broken-vs-clean test skips, `make
  eval` reports **S4 as never run**, and no GOP threshold can be calibrated, so
  `PRON_GOP_THRESHOLDS` stays empty.
- **More recorded conversation, on more than one day.** It is the only thing that can
  settle S5 *or* S7. Eleven analysed turns and 428 words, on two calendar days, is the
  whole corpus (the census of 2026-09-06); the progress page cannot draw a trend through
  one or two points however well it is written, and the error measurement re-runs against whatever is there: `make analyze`,
  then `python3 eval/golden/errors/build.py`, then `make error-precision`, then
  `make rollup`, then `make eval`.
- **A product decision on read-aloud with audio retention off.** Today the endpoint
  refuses with a 409 naming the setting, because a reading that cannot be rescored would
  break the promise its schema makes. The alternative worth weighing is a third retention
  state: keep the waveform for read-aloud only, where the speaker is reading published
  text rather than talking about their own life.
