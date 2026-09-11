# Data model

Twelve tables, three enum types, one Alembic revision. This document explains the shape;
`api/alembic/versions/0001_initial_schema.py` is what actually builds it, and
`api/db_models/` is what reads and writes it.

The organising idea is in PRD principle **P1**: *deterministic metrics for trends, the
LLM only for explanation*. Every table below either stores something measured from a
waveform or a transcript by code that produces the same number twice, or stores content
a human wrote. Exactly one table records anything an LLM proposed, and it records which
layer proposed it.

---

## 1. The tables

### Content — written by a person, loaded from `api/seeds/`

| Table | Holds |
|---|---|
| `scenarios` | Persona, goal, target grammar, functions and kinds of mistake, band, rubric |
| `passages` | Reference text, band, phoneme focus, word count |

Both are keyed by `slug`, which is the seed key, the URL segment, and what a session's
history points at across a content edit. Both carry `is_active`: content is retired by
deactivating it, never by deleting it, because a session started last month still has to
render.

### Accounts and recordings

| Table | Holds |
|---|---|
| `users` | Credentials, native language, retention preference |
| `audio_assets` | A path on the audio volume, duration, sample rate, hash, device hint |

`audio_assets.path` is a path, never a blob. A 30-second recording is about a megabyte;
storing those in Postgres would put every recording in every backup and grow the database
at the rate the user practises. `device_hint` exists because PRD **P4** says a score
without a baseline is noise — GOP moves with the microphone, and a trend that cannot see
a hardware change reads a new headset as improvement.

`UNIQUE (user_id, sha256)` makes a double-submit an error rather than a second attempt.

### Practice

| Table | Holds |
|---|---|
| `sessions` | One sitting: user, scenario or none, mode, status, timing, end report |
| `turns` | One utterance: transcript, word timings, ASR confidence and model |
| `attempts` | One read-aloud reading: passage, audio, transcript, WER, scoring status |

`turns.words` is JSONB — `[{w, start_ms, end_ms, logprob}]` straight off the recogniser.
It is read whole, for one purpose (the §7.1 fluency metrics), and never queried across
rows. A `words` table would add roughly 150 rows per turn and buy nothing.

`turns.asr_confidence` is the gate. A turn the recogniser was unsure of must not feed an
accuracy trend: an ASR error scored as a grammar error is a correction the user cannot
act on, and a trend line that moves for the wrong reason.

`attempts.status` is a lifecycle, not a flag, because scoring is asynchronous — ffmpeg,
faster-whisper, G2P, wav2vec2 and forced alignment is seconds of work. `error_message` is
FR-16: a failure has to be able to say why, or it cannot be retried meaningfully.

### Measurement

| Table | Holds |
|---|---|
| `fluency_metrics` | Speech rate, articulation rate, pause ratio, mean length of run, fillers |
| `grammar_usage` | Which forms were used, and how often — breadth (P3) |
| `language_errors` | One correction: span, category, original, fix, and who found it |
| `phoneme_scores` | One scored phone: canonical, recognised, GOP, posterior, timing |
| `progress_snapshots` | Per-user, per-period rollups — what the progress page reads |

`fluency_metrics` is keyed by `turn_id` rather than carrying its own id: there is exactly
one row per turn forever, and a surrogate key would permit a second.

`grammar_usage` exists because of **P3**. A learner reaches a zero error rate by only ever
using the present simple; measuring errors alone rewards avoidance. Counting which forms
were *used* is what makes a narrowing repertoire visible as the regression it is.

`language_errors.detector` (`'llm'` or `'rule'`) is the one place an LLM's output is
recorded, and it is labelled as such. That is what lets the error-precision suite report
the model's precision and the rule layer's separately instead of asserting either. A model
proposal a rule had already made is not stored twice: it goes onto `turns.analysis_rejects`
with the reason `superseded_by_rule`, and is not counted as a refusal.

`language_errors.form` and `corrected_form` (revision `0005`) join a correction to the
grammar the parser counts: the verb form the corrected words were said in, and the one
the correction puts there, both in `grammar_usage`'s vocabulary. They are what accuracy
per form is computed from — right is a form's `grammar_usage` count less the corrections
said in it, over that count plus the corrections that needed it. Either can be NULL, and
NULL is a finding: `She going` said no finite form, and a preposition error is not a
correction of a verb. They are derived from the transcript and the correction, so `make
reparse` recomputes them — and `grammar_usage` — without asking the model anything again.

`scenarios.target_errors` (revision `0006`) is the second thing a scenario declares: the
error categories it is built to draw out, in `language_errors.category`'s vocabulary.
`target_grammar` is in the parser's vocabulary, which has no word for an article, a
preposition or a false friend — those exist only as the categories corrections are filed
under. It is how a learner corrected on prepositions is pointed at a scenario written to
draw them out. The seed loader rejects a name the taxonomy does not have.

`progress_snapshots` is the only table nothing writes per turn: one row per user per
period, at day and week granularity, rewritten from the rows underneath whenever they
change. `updated_at` (revision `0004`) is what makes "is this row still current?" a
question with an answer — the turns and attempts underneath carry their own timestamps, so
a snapshot older than its inputs is stale by arithmetic rather than by guess. Weekly rows
are computed from turns and never from seven daily rows, because averaging averages weights
a quiet Tuesday the same as a long Sunday. `cefr_estimate` is the one column in this schema
that nothing writes at all: a band assigned from a handful of turns would be a confident
answer to a question the data cannot settle.

`phoneme_scores` carries both `canonical_phone` and `recognized_phone`, and the pair is
the point:

```
GOP(p) = log P(p | O_segment) − max over q of log P(q | O_segment)
```

GOP alone says *"your /θ/ is weak"*. The phone that actually won the posterior says
*"you are producing /s/ where English wants /θ/"*, which is the difference between a grade
and an instruction. `recognized_phone` is nullable because the aligner can report a
segment with no clear winner, and inventing a substitution the acoustic model did not
assert is exactly what invariant I2 forbids.

---

## 2. Enums, checks, and where the vocabulary lives

Three native Postgres enum types:

```
session_mode     conversation | read_aloud
session_status   active | completed | abandoned
attempt_status   pending | scoring | scored | failed
```

Native types rather than TEXT because a typo in a string literal writes a row nobody
queries for again; as a type, `'compelted'` is rejected on the way in.

Three CHECK constraints instead, where the vocabulary has two members or is expected to
change: `turns.role`, `language_errors.detector`, `progress_snapshots.period`.

`language_errors.category` has neither. The taxonomy *is* closed — invariant I3 — but it
is enforced in the application layer at m9, because it will be revised once real
transcripts have been read, and a revision should be a code change with a test rather
than an `ALTER TYPE` that cannot run inside a transaction.

`cefr_band` is TEXT in the database and a closed enum at the API edge
(`api/models/common.py`), which is what makes `?band=B7` a 422 rather than an empty list.

---

## 3. Why JSONB, five times

`scenarios.target_grammar`, `scenarios.target_functions`, `scenarios.target_errors`,
`scenarios.rubric`, `passages.phoneme_focus`, `turns.words`, `sessions.report`, and the
five families on `progress_snapshots`.

Two different reasons, worth keeping apart:

- **Lists that are filtered by containment** — `target_grammar`, `target_errors`,
  `phoneme_focus`. The query is `@>`, one indexable predicate, and GIN indexes it when the
  seed set outgrows a sequential scan over a dozen rows.
- **Documents read whole for one screen** — `rubric`, `words`, `report`, and the progress
  families. Nothing queries inside them across rows. The set of fluency measures is still
  moving, and a schema migration per metric added is a tax on exactly the experimentation
  this project exists for — the progress rollup added three keys to `sample_counts` without
  touching the schema.

The counter-example is the rule: `language_errors` and `phoneme_scores` are tables, not
JSON columns, precisely because they *are* aggregated across rows — by category, by phone,
over time.

---

## 4. Indexes

Four, each for a query that exists:

| Index | The question |
|---|---|
| `ix_sessions_user_id_started_at` | This user's history, newest first |
| `ix_language_errors_turn_id_category` | Errors on a turn; errors by category over a window |
| `ix_phoneme_scores_attempt_id` | Everything about one reading — the result screen |
| `ix_phoneme_scores_canonical_phone` | One phone's history — the trend under the result |

Plan §5 writes the sessions index as `(user_id, started_at DESC)`. It is ascending here:
Postgres scans a btree in either direction, so for a single sort column the `DESC` buys
nothing, and it would cost the ORM-versus-migration comparison in `test_migrations.py`
the ability to see this index at all — a `DESC` index is an expression index, which
`compare_metadata` cannot diff.

---

## 5. Migrations

Alembic owns the schema. There is no `init.sql` and no `Base.metadata.create_all`
anywhere in the repository, **including in the test suite**. Two ways to build a schema
is two sources of truth, and they diverge the first time a migration is added and only
one path is updated. The tests migrate a scratch database with Alembic for that reason,
and pay about a second per run for it.

```bash
make migrate          # alembic upgrade head
make migrate-status   # current revision, and the history
make migrate-down     # one revision back — read the downgrade first
```

Every constraint and index is named explicitly, following the convention in
`api/db_models/base.py`. Postgres will name a constraint for you and SQLAlchemy will name
it differently, and then `alembic revision --autogenerate` emits a drop-and-recreate for
something that never changed. `test_migrations.py` asserts the two agree by running
Alembic's own `compare_metadata` against a migrated database and requiring an **empty**
diff — which is also what catches a column added to a model and never migrated.

The downgrade drops the enum types as well as the tables. A downgrade that leaves a type
behind fails on the *next* upgrade, as `type "session_mode" already exists`, minutes after
the mistake was made; up, down and up again is one of the tests.

---

## 6. Seeds

```bash
make seed             # idempotent — the second run inserts nothing
```

Scenarios and passages are **seeded data, not fixtures**: real rows, versioned as JSON in
`api/seeds/`, so a content edit is a reviewable diff. The loader keys on `slug` and
reports three outcomes separately — inserted, updated, unchanged — because only the third
makes a second run a no-op, and a script that printed "8 scenarios loaded" both times
would be telling the truth in a way that hides the thing worth knowing.

Every record is validated through the same Pydantic models the API serves before anything
touches the database, so a typo fails the load, naming the field and the record, rather
than surfacing as a 500 a week later. `passages.word_count` is *derived* from the body
rather than stated in the file, so the file cannot disagree with itself.

`phoneme_focus` is validated against the 39 ARPAbet symbols in `api/models/common.py`.
That tuple and m8's `phone_map.py` are two copies of one phone set, and m8 must assert
they are equal: a phone missing from one of them is a pronunciation error that is never
scored and never reported as unscored.

---

## 7. What is not here yet

`users` exists and nothing writes to it — accounts are m3. Every table from `sessions`
downward is empty until the milestone that fills it: m6 for sessions and turns, m8 for
attempts and phoneme scores, m9 for errors and grammar usage, m10 for snapshots.

That is deliberate. The plan puts the whole schema in one revision because everything
downstream writes to these tables, and getting the shape right once is cheaper than
eleven migrations that reshape it.
