# Changelog

One entry per milestone. Numbers here are counted against the running system at the time
of writing, never recalled — if a figure cannot be re-measured it does not belong here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [0.4.0] — 2026-08-30 · m4, the recogniser and the audio pipeline

Audio in, transcript with per-word timings and logprobs out — and the first stage of the
product whose latency budget is measured rather than assumed.

### Added

- **`asr` service** (`infra/asr/`): faster-whisper on CTranslate2, `small.en` at int8,
  word timestamps forced on. No torch, and no ffmpeg binary either — PyAV carries the
  ffmpeg libraries in-process, which is 200 MB of Debian dependencies and one subprocess
  saved. It joins the **default** compose stack; the `speech` profile now holds only tts.
- **`POST /transcribe`** returns `{w, start_ms, end_ms, logprob}` per word, plus the
  decoder settings and what the source media actually was. `GET /health` answers 200 with
  `model_loaded: false` while weights load and 503 only when a load has *failed* — the
  difference between a cold start and a dead container.
- **The audio pipeline** — `services/audio.py` and `services/asr_client.py`. Recordings
  are content-addressed by sha256 and unique per user, so a double-tapped send is one row.
  The insert runs in a savepoint, because from m6 it is called inside a transaction that
  also writes a turn.
- **`GET /audio/{asset_id}`**, ownership-checked, 404 for a stranger. The twelfth of
  thirty forecast operations.
- **`eval/golden/asr/`** — ten LibriSpeech test-clean utterances, ten speakers, 232
  reference words, committed with a manifest that carries each file's sha256 and a
  `fetch.py` that reproduces the set. `make asr-wer` scores against it.
- **`services/wer.py`** — word error rate with the three edit types counted separately,
  written out rather than imported, because the normalisation is what moves the number.

### Fixed

- **`make lint` was reaching into a read-only mount.** Inside the container `eval/` is
  mounted under `/app` read-only (invariant I7), so a formatter pointed at `/app` failed
  on a file CI never lints. Both now lint the same thing.
- **The test service was no longer hermetic.** Its `ASR_URL` was `http://asr:8101`,
  chosen because it did not resolve — and then m4 put `asr` on the same network, so the
  health tests quietly began asserting against a service that was up. The URLs now name
  hosts that cannot exist.

### Measured

| | |
|---|---|
| Operations in `app.openapi()` | 12 of 30 (was 11) |
| Tests | **146** — 139 pass with no recogniser, all 146 with one |
| WER, `small.en` int8 beam 5 | **1.72 %** (4 substitutions in 232 words, 0 del, 0 ins) |
| Latency, ~6 s of audio | **1231 ms** against PRD §9.1's ≤ 700 ms — **the budget is missed** |
| `base.en` beam 1, the declared fallback | 525 ms, WER 4.31 % |
| VAD off | WER 3.45 % and *slower* (1772 vs 1416 ms) — the default is right on both axes |
| Timestamp repairs across the golden set | 0 |
| `asr` image | 746 MB, no torch (planned: ~400 MB) |
| Host load during the latency runs | **21** — see the caveat below |

### Decided

- **`small.en` stays, and the missed budget is reported rather than engineered away**
  (D26). `base.en` would meet it today for 2.6× the word error rate, and that error rate
  is the input to the grammar analyser, the fluency metrics and the read-aloud reference.
  PRD §9.1's own fallback order spends a cheaper lever first — streaming TTS — which m5
  and m6 have not built. The switch is one environment variable and is already measured.
- **No Alembic revision at m4** (D27), for the second milestone running: `audio_assets`
  and `turns` were created complete at m2 and m4 changed no column.
- **No `POST /audio`** (D28). Audio enters attached to a turn (m6) or an attempt (m8); a
  bare upload endpoint would create recordings that belong to nothing.
- **PyAV instead of the ffmpeg binary** (D29), a deviation from the plan's wording.

### Known limits

- **The WER is a floor, not a forecast.** LibriSpeech test-clean is native, fluent,
  adult, read-aloud English in good conditions. Learner speech will be worse by an amount
  this set cannot estimate.
- **232 reference words means one word is 0.43 %.** Enough to separate `small.en` from
  `base.en`; not enough to rank two configurations four errors apart.
- **Latency was measured on a machine at load 21**, with three other project stacks
  running. The ratios between configurations are the claim; the absolutes carry the
  machine's state with them.
- **Concurrency is unmeasured.** Inference is serialised on purpose, so a second
  simultaneous turn waits.

### Not in this release

No upload endpoint, no transcript persistence (`turns` needs a session, which is m6), no
frontend — m4 adds no UI. Full argument in
[decisions/0001-asr-model-choice.md](decisions/0001-asr-model-choice.md).

---

## [0.3.0] — 2026-08-30 · m3, auth and per-user scoping

Accounts exist, and every route now has to say whether it needs one.

### Added

- **Registration and sign-in.** `POST /auth/register`, `POST /auth/login`,
  `POST /auth/logout`, `GET /auth/me`, `PATCH /auth/me`. Registration captures native
  language, which is what selects the L1 phoneme priors at m8 — asked at the one moment
  somebody will answer it rather than left to a settings page nobody opens.
- **Argon2id password hashing**, via `argon2-cffi`. Cost parameters travel inside each
  hash, and a successful login re-hashes any row that is behind the current defaults.
- **JWT in an httpOnly cookie.** The frontend never sees the token: `document.cookie` is
  empty in a signed-in browser, and the same request without `credentials: "include"`
  is a 401.
- **`api/dependencies.py`** — one `current_user` dependency and one `get_owned_or_404`
  helper, which fold "does it exist" and "is it yours" into a single `WHERE`.
- **Frontend.** `/login` and `/register`, and a `useAuth` hook with a three-state
  `status` so that "checking" and "signed out" are not the same thing.

### Fixed

- **The test client had no transaction boundary.** `conftest`'s `get_db` override
  yielded a session and never committed, so every write made through the client was
  rolled back at the end of the request. m2's suite only read, so it was green and
  meaningless at the same time. Removing the fix now breaks 12 tests.
- **A blank `JWT_SECRET` was worse than an absent one.** Compose passes an unset
  `${JWT_SECRET:-}` through as `""`, and `os.environ.get("JWT_SECRET", DEV)` returns
  that empty string — signing every token with a zero-length key *and* skipping the
  startup warning, because `""` is not the sentinel it compares against.

### Measured

| | |
|---|---|
| Operations in `app.openapi()` | 11 (was 6) |
| Tests | 98 passing (was 52), 5.2–8.3 s |
| `POST /auth/register` | 61 ms median — one Argon2 hash at 64 MiB |
| `POST /auth/login` | 73 ms median |
| Wrong password vs. unknown email | 75.6 vs 78.1 ms median, n=12 each |
| The same gap without the dummy-hash equaliser | ~3.6 ms vs ~76 ms, a 21× tell |
| `GET /auth/me`, no session | 3.6 ms |
| Stored hash | `$argon2id$v=19$m=65536,t=3,p=4$…` |

### Decided

- **Argon2id, and `argon2-cffi` rather than passlib** (D22). PRD FR-1 required Argon2;
  m1's requirements file shipped `passlib[bcrypt]` arguing the opposite. Since the hash
  was changing regardless, the wrapper went too: passlib 1.7.4 is from 2020, is
  unmaintained, and its bcrypt backend raises on bcrypt ≥ 4.1.
- **No Alembic revision at m3** (D23). m2 created `users` complete. An empty revision
  would make `alembic history` claim a change that never happened.
- **One access token, no refresh token, and a logout endpoint** (D24). The plan's API
  surface forecast four auth operations; a token in an httpOnly cookie cannot be deleted
  by the script that cannot read it, so logging out has to be a server operation. Five.

### Known

- **The suite is ~3× slower than at m2** and that is the correct trade: every
  registration in it performs a real 64 MiB Argon2 hash rather than a stubbed one. Worth
  revisiting only if it passes ~30 s.
- **No server-side revocation.** Logout clears the cookie; a copy taken beforehand stays
  valid until `ACCESS_TOKEN_TTL_HOURS` (168) elapses.
- **Sessions, attempts and progress do not exist yet**, so `test_ownership.py` currently
  guards two routes. Its value is that it guards *every* route, including the ones m6
  and m8 have not written.

### Not in this release

- Password reset, email verification, rate limiting on login. Each needs something this
  system does not have — an outbound mail path, or a shared counter — and none is on the
  path to measuring whether somebody's pronunciation improved.

## [0.2.0] — 2026-08-30 · m2, data model and seeds

The database has a shape, and the first content a user could actually browse.

### Added

- **Schema.** One Alembic revision, `0001_initial_schema`, creating the twelve tables of
  the plan's §5 and three native Postgres enum types (`session_mode`, `session_status`,
  `attempt_status`). `make migrate` applies it; `make migrate-down` and
  `make migrate-status` are the other two things anyone ever needs.
- **ORM.** `api/db_models/`, twelve mapped classes over those tables, with a constraint
  naming convention so that every later autogenerated revision diffs content rather than
  names.
- **Seeds.** `api/seeds/scenarios.json` and `api/seeds/passages.json` — 8 scenarios and
  12 passages, loaded by `make seed`, keyed by slug and idempotent. Each passage is
  written to force one or two sounds repeatedly rather than mention them; each scenario
  declares the grammatical forms it exists to elicit, which is what m11 will check it
  against.
- **API.** `GET /scenarios`, `GET /scenarios/{slug}`, `GET /passages`,
  `GET /passages/{slug}`, with filters on band, category, target grammar and phoneme
  focus. An unknown band is a 422, not an empty list.

### Measured

| | |
|---|---|
| Tables created by `alembic upgrade head` | 12 |
| `make seed`, first run | 8 scenarios, 12 passages inserted |
| `make seed`, second run | 0 inserted, 0 updated, 20 unchanged |
| `GET /scenarios`, warm | 2.5–3.8 ms over 5 calls |
| ORM vs. migration drift | 0 differences (`compare_metadata`) |
| API test suite | 52 passed in 2.1–2.4 s over 4 runs |
| `make test` wall time | 3–38 s — container start-up, not the suite. See *Known* |
| API operations | 6 of the 29 forecast |
| Passage length | 73–79 words |
| ARPAbet coverage of `phoneme_focus` | 39/39 symbols known, matching the m0 phone map |

### Decided

- **Seeds live at `api/seeds/`, not at the repository root.** One path that resolves
  identically in the container (`/app/seeds`), in CI (which runs from `api/`) and in a
  host shell. A root-level `seeds/` would need a bind mount in one of those and a
  different relative path in another, and the day they disagree the loader reads an
  empty directory and reports success.
- **The test suite builds its schema with Alembic, never with `create_all`.**
  `create_all` builds what the ORM says; the migration builds what is actually applied
  to a database. A suite that tests the first is green while the second is broken.
- **`persona_prompt` is never serialised.** It is the exercise — a user who reads the
  persona's instructions is no longer practising against them — and it is the one string
  in a turn the user is not meant to influence. A test asserts its absence from every
  response body.
- **`words`, `report` and the four progress families stay JSONB.** They are read whole
  for one screen and never queried across rows. Errors and phoneme scores are tables
  precisely because they *are* aggregated across rows.

### Known

- **`make test` wall time is not the suite's.** The suite itself is 2.1–2.4 s, measured
  four times inside one container. `make test` measured anywhere between 3 s and 38 s on
  the same machine, because `docker compose run` creates a container per invocation and
  this laptop runs several stacks. The number to quote is the in-container one; the
  variance is Docker Desktop scheduling, and it is worth knowing before anyone concludes
  the suite is degrading.
- The passage density check in `test_passages.py` is orthographic, not phonetic — it
  counts letters, not phones. The honest version needs G2P, which arrives with m8. What
  it catches today is a passage edited until it no longer exercises its declared focus.
- `language_errors.category` is TEXT, not an enum, although the taxonomy is closed
  (invariant I3). The taxonomy is expected to be revised once real transcripts are read,
  and a revision should be a code change with a test rather than an `ALTER TYPE` that
  cannot run inside a transaction. m9 enforces it in the application layer.

### Not in this release

Accounts (m3) — the `users` table exists and nothing writes to it. Speech in and out
(m4, m5), the conversation loop (m6, m7), pronunciation scoring (m8), grammar analysis
(m9), progress (m10), the evaluation harness (m11).

---

## [0.1.0] — 2026-08-29 · m1, scaffold

The stack exists and reports on itself. No feature does.

### Added

- **Compose stack.** Seven services declared, three started by default
  (`postgres`, `api`, `frontend`). `asr`, `tts`, `pron`, `ollama` and the `test` job sit
  behind profiles, which is what lets this file name build contexts that m4, m5 and m8
  have not created yet.
- **API.** FastAPI on Python 3.12, async SQLAlchemy 2.0 against PostgreSQL 16.
  Two operations: `GET /health` and `GET /health/models`.
- **Frontend.** Next.js 15, React 19, Tailwind v4, shadcn/ui. One page, which renders
  `/health` — the only check that covers browser → frontend container → API container →
  Postgres. It has a healthcheck of its own (busybox `wget --spider`, 60 s start period
  because `next dev` compiles the first route on demand), so all three default containers
  report `healthy` rather than merely `up`.
- **CI.** Three jobs: API lint and tests, frontend lint/types/build, and a Compose parse
  of the default stack and of every profile.

### Measured

| | |
|---|---|
| Containers up and healthy | 3 of 3 |
| `GET /health`, warm | 13–20 ms over 5 calls |
| API test suite | 13 passed in 0.21 s |
| API image | 422 MB |
| API operations | 2 of the 29 forecast |

### Decided

- **No `infra/postgres/` image or `init.sql`.** Plain `postgres:16`. With no extensions
  to add, a Dockerfile whose only line is `FROM postgres:16` implies a customisation
  that does not exist, and an `init.sql` that created tables would be a second source of
  truth alongside the Alembic revisions that own the schema from m2.
- **API on 8002, not 8001.** 8001 is occupied by an unrelated stack on this machine.
- **Next.js 15.5.24, not 15.5.12.** The version the plan was written against carries
  24 published advisories, all fixed within the 15.5 line.
- **The API build context is the repository root**, so the image carries `api/` and runs
  without a bind mount. `.dockerignore` keeps that context small; without it every build
  would ship `spike/.venv` (875 MB) and `frontend/node_modules` (549 MB) to the daemon.

### Known

- `npm audit` reports 2 advisories against the copy of `postcss` bundled inside Next 15's
  own `node_modules`. The only fix upstream is Next 16, which is outside this plan. It
  affects CSS source-map loading in the build pipeline, not the served application.
- `/health` reports `degraded` on a fresh checkout. That is correct: no model service
  exists before m4.

### Not in this release

Everything else. The schema and seeds (m2), accounts (m3), speech in and out (m4, m5),
the conversation loop (m6, m7), pronunciation scoring (m8), grammar analysis (m9),
progress (m10), the evaluation harness (m11).
