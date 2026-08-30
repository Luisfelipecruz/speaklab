# Changelog

One entry per milestone. Numbers here are counted against the running system at the time
of writing, never recalled — if a figure cannot be re-measured it does not belong here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [0.6.0] — 2026-08-30 · m6, the conversation

The first milestone where the product exists: a spoken turn goes in and the persona
answers out loud, persisted. And two measurements that contradict things this project
believed before it took them.

### Added

- **`POST /sessions`** starts a conversation against a seeded scenario and returns the
  persona's **generated** opening turn as text and audio (FR-6). Nothing is written if
  generation fails, so a machine with no Ollama does not accumulate empty sessions.
- **`POST /sessions/{id}/turns`** — the endpoint the product is about (FR-7). Audio in,
  transcript, persona reply, speech out, both turns stored, in one atomic request. It
  reports its own stage breakdown on every response, because R3 is that a latency
  regression is felt long before it is noticed.
- **`GET /sessions`** (paginated), **`GET /sessions/{id}`** (the full transcript, FR-10),
  **`POST /sessions/{id}/end`** (the report, FR-9) and **`DELETE /sessions/{id}`**.
  Six operations; **18 of the forecast 30 now exist**, counted from `app.openapi()`.
- **`services/llm/`** — a provider interface and an Ollama implementation, with the same
  three-outcome taxonomy as the ASR and TTS clients. Not LangChain: this is an HTTP call,
  a token budget and a message list, and a framework would have hidden the token budget,
  which is the part most worth reviewing.
- **`services/conversation.py`** — persona anchoring, the token budget, summarisation into
  a running digest, sentence splitting, and the overlap of generation with synthesis.
- **Two schema columns per table** (`0002_conversation_context.py`): `sessions.context_digest`
  and `digest_through_idx` for FR-8's summarisation, and `turns.llm_model`, `tts_voice`,
  `prompt_tokens`, `completion_tokens` for provenance. Revision **0002**, not the plan's
  guessed 0004 — m3, m4 and m5 each needed no migration at all.
- **`make turn-latency`** and **`make turn-latency-noflow`** — the same 20-turn
  measurement with PRD §9.1's first fallback on and off, which is the only honest way to
  measure what that fallback buys.
- **`docs/decisions/0003-conversation-context-strategy.md`** — the context-shift cliff,
  the Gemma template finding, the estimator's measured error, and the turn breakdown.

### Changed

- **`num_ctx` is now sent on every generation request**, and this is a correctness fix
  rather than tuning. **Ollama does not refuse an over-long prompt** — llama.cpp shifts
  the context, discards half of it, and answers 200 with nothing in the response to say
  so. Measured: a 4200-token prompt under `num_ctx: 4096` came back with
  `prompt_eval_count: 2051`. The discarded half is the front of the conversation, which
  is where a system message lives — so the persona vanishes from exactly the long
  conversations PRD R7 is about, silently.
- **The persona is anchored twice per turn, not once.** Ollama's template for `gemma3:4b`
  renders a `system` message as an ordinary `<start_of_turn>user` block: **Gemma 3 has no
  system role.** "Re-anchor the persona in the system message every turn" therefore means
  "put it in the first user turn", forty turns from where the reply is written. Whether
  the second anchor helps is **unresolved** — both deterministic proxies saturate at
  100 % with and without it (n = 25, 30 turns of history), so m6's instruments cannot
  tell. It is kept on the template argument and logged as Q12 for m11.
- **`users.retain_audio` finally does something.** It has been settable since m3 and
  nothing stored a waveform until now. With it off, a turn is transcribed and the
  recording is not kept — no file, no row — while the transcript, word timings and
  confidence remain. That is FR-26 exactly: drop the audio, keep the derived data.
- **`DELETE /sessions/{id}` deletes the audio too**, but only assets nothing else still
  references. A session removed from the history while its recordings stay on the volume
  is not a promise this project should make.
- **The API opens an audio file for the first time** (`services/wav.py`), and the claim in
  `services/audio.py` that it never does is now scoped to *uploads*, where it still holds.
  Joining per-sentence synthesis into one file is not decoding: known format, known
  parameters, produced by this system's own voice seconds earlier, standard library only.

### Measured

- **A whole spoken turn: 2353 ms median, 2684 ms p95, against a 3000 ms budget — met.**
  Twenty turns through the real recogniser, model and voice on a quiet target machine
  (load 1.7 rising to 5.0). ASR 1146 ms, generation 872 ms, synthesis tail 235 ms. The one
  stage that misses its own budget is ASR, and the turn absorbs it — which is precisely
  the bet m4 made when it declined to downgrade the recogniser (D26).
- **The same twenty turns measured 7283 ms at p95 on a busy machine** — load 10–16, with a
  second Docker VM, an Android emulator and two other Compose stacks running. 2.7× on
  identical code. Both numbers are recorded, because the range is what a developer
  actually meets and because for several hours the contended one was the only measurement
  available and it said the opposite thing.
- **PRD §9.1's first fallback is worth ~140 ms, not the second it was assumed to be.**
  Measured against its own control on a quiet machine: 235 ms of synthesis still to wait
  for when generation ends, against 375 ms in series. A two-to-three-sentence reply is only
  ~500 ms of synthesis work, so that is close to the arithmetic ceiling. It stays on
  because it costs nothing and because m7 — where the browser plays sentence one while
  sentence two is still being made — is where it actually pays.
- **The token estimator errs by −6.4 % to +6.2 %** across three prompt shapes against
  Ollama's own count. `LLM_ESTIMATOR_MARGIN` is 1.25 and the context window is sized from
  it, so the heuristic is a bound rather than a hope.
- **274 tests, up from 177.** 255 run with no model services at all; the other 19 need
  a live recogniser, voice or Ollama and skip without one.

### Answered

- **Q8 — does turn latency force ASR down to `base.en`? No.** The turn meets its budget
  with `small.en` in it: p95 2684 ms against 3000 ms. ASR misses its own 700 ms stage
  budget at 1146 ms and the turn absorbs the overspend, because generation came in at
  872 ms against 1500 ms and synthesis at 235 ms against 400 ms. Downgrading would buy
  ~620 ms and cost 2.6× the word error rate, for a requirement that is already met.
  **D26 is confirmed, not reopened** — the turn-level measurement it asked for now exists.
  The margin is 316 ms and the control arm sat at 3043 ms, so this is met, not met
  comfortably.

### Known gaps

- **§9.1's fallback order looks wrong for this stack, and nothing was changed on it.** The
  order is stream TTS (~140 ms), drop ASR (~620 ms, costs accuracy), shorten the reply cap
  (untested, listed last). Reply length drives generation *and* synthesis, so it is
  plausibly the largest of the three. That is a hypothesis with no measurement behind it.
- `ASR_CONFIDENCE_FLOOR` is **0.60 and that is a placeholder, not a finding** — nothing
  has measured where learner speech sits on this scale. Flagged as Q11 for m9, which has
  the labelled corpus that can answer it.
- The session report's `measured` block is real and its `pending` block names the four
  things FR-9 asks for that need m8 and m9. A report that omitted them would read as a
  session that simply had no errors in it.

---

## [0.5.0] — 2026-08-30 · m5, the voice

Text in, the persona's speech out, fast enough to sit inside a conversational turn — and
a measurement that says the obvious way of doing it is not fast enough.

### Added

- **`tts` service** (`infra/tts/`): Piper 1.7 on onnxruntime, voice
  `en_US-lessac-medium`. No torch and no `espeak-ng` apt package — `piper-tts` carries
  the phonemiser as a compiled extension, so the whole dependency closure is 25 packages.
  The 61 MB voice is baked into the image at build time, which removes the cold first
  turn entirely; any other voice is cached in the shared `model_cache` volume instead.
- **`POST /synthesize`** returns one WAV for the whole reply, with `duration_ms`,
  `sample_rate` and the sentence count in response headers — the service that produced
  the audio is the authority on those, exactly as `asr` is for a recording.
- **`POST /synthesize/stream`** returns one PCM chunk **per sentence**, each tagged with
  how long the caller had been waiting when it arrived. This is PRD §9.1's first
  prescribed fallback, built here rather than in m6 because the measurement that
  demanded it was taken in the milestone that wrote the service.
- **`GET /voices`** reports what this process loaded and what is on disk beside it. It
  does not fetch Piper's catalogue: an endpoint that reaches the network to answer a
  question about itself would fail on the offline machine this system is built for.
- **`services/tts_client.py`** with the same three-outcome taxonomy as the ASR client —
  unavailable, rejected, protocol error. The 503 a loading voice returns is
  *unavailable*, never a rejection: the identical text synthesises a second later.
- **`AudioPlayer.tsx`** — keyboard-operable playback with a caption slot and a visible
  error state, all three from PRD §9.2 rather than from taste. No test beside it yet;
  the Jest and RTL harness arrives with m7, which is also what first mounts it.
- **`make tts-latency`** measures synthesis through the live service; **`make tts-sample`**
  writes a WAV you can actually listen to, into gitignored `spike/`. Voice quality is a
  judgement no assertion makes for you, and **nobody has made it yet** — every number in
  this entry is about latency, size and format.
- **`docs/decisions/0002-tts-model-choice.md`** — the sweep, the three findings, and the
  two deviations from the plan.

### Changed

- **The `speech` profile is gone.** It existed to keep two not-yet-created build contexts
  inert; m4 created `infra/asr` and m5 created `infra/tts`, so it had no members left.
  `docker compose up -d` now brings up the whole conversational stack — five services —
  and only the 2 GB pronunciation service stays opt-in. `make speech-up` is removed.
- **`PIPER_NUM_THREADS` defaults to 8, not to onnxruntime's own choice**, and the
  difference is 2.3×: 378 ms against 814 ms for an 80-token reply, which is the
  difference between meeting PRD §9.1's 400 ms budget and missing it. The curve is a U
  with its minimum at 8 on this 16-core machine, so more is emphatically not better.
  Note this is the *opposite* of m4's conclusion for CTranslate2 — a library default is
  a claim to be measured, and two libraries here gave opposite answers.
- **CI's model-service URLs now name hosts that cannot resolve** (`asr.invalid` and so
  on). They happened to be unreachable on a GitHub runner anyway; the point is that this
  is the assumption which broke in `docker-compose.yml` when m4 put a real `asr` on the
  test network, and CI should not be relying on it either (trap 25).

### Measured

- **Synthesis is not deterministic.** Five syntheses of one reply: 8011, 8220, 8382,
  8382, 8475 ms — a 5.5 % spread. Piper is VITS and its duration predictor samples from
  a learned distribution; that is what stops synthetic prosody sounding metronomic. So a
  reply must be **stored, never re-derived** — `audio_assets` is keyed by sha256 and two
  syntheses of one sentence hash differently.
- **On a quiet machine every reply length meets the budget**: 320 ms for an 80-token
  reply, 50× real time. **On a busy one the whole-reply call misses it** — 771 ms at
  load average 22 — while time-to-first-sentence stays at 135 ms. That gap is the
  streaming endpoint's entire justification.
- **`tts` image 672 MB**, against `asr` at 746 MB and `api` at 424 MB. Counted with
  `docker images`, not recalled.
- **170 tests**, 161 of which pass with no model services running.

### Decided

- **No `api/routers/tts.py`** (D31, resolving Q9). The plan listed an internal preview
  endpoint; plan §6 forecasts 30 operations, none of them a TTS route, and lists
  `POST /synthesize` under *"never exposed to the browser"* two lines above it. No FR
  asks for one — reply audio reaches the browser through the ownership-checked
  `GET /audio/{asset_id}` that already exists. Same question as m4's `POST /audio`, same
  answer (D28). The operation count stays at 12 of 30.

---

## [0.4.0] — 2026-08-30 · m4, the recogniser and the audio pipeline

Audio in, transcript with per-word timings and logprobs out — and the first stage of the
product whose latency budget is measured rather than assumed.

### Added

- **`asr` service** (`infra/asr/`): faster-whisper on CTranslate2, `small.en` at int8,
  word timestamps forced on. No torch, and no ffmpeg binary either — PyAV carries the
  ffmpeg libraries in-process, which is 200 MB of Debian dependencies and one subprocess
  saved. It joins the **default** compose stack; the `speech` profile then held only tts, and
  m5 retired it altogether.
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
