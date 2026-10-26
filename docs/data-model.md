# Data model

Twenty-two tables, four enum types, nine Alembic revisions. This document explains the
shape; `api/alembic/versions/` is what actually builds it, starting from
`0001_initial_schema.py`, and `api/db_models/` is what reads and writes it.

The organising idea is in PRD principle **P1**: *deterministic metrics for trends, the
LLM only for explanation*. Every table below either stores something measured from a
waveform or a transcript by code that produces the same number twice, or stores content
a human wrote. Two tables record what an LLM proposed — a mistake in speech, and one in
what the person wrote — and each records which layer proposed it.

---

## 1. The tables

### Content — written by a person, loaded from `api/seeds/`

| Table | Holds |
|---|---|
| `scenarios` | Persona, goal, target grammar, functions and kinds of mistake, band, rubric |
| `passages` | Reference text, band, phoneme focus, word count |
| `answer_prompts` | A work question to answer out loud: its kind, band and time limit |

All three are keyed by `slug`, which is the seed key, the URL segment, and what history
points at across a content edit. All three carry `is_active`: content is retired by
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

The file is always at `<user_id>/<sha256>` under the audio root, and that is how it is
found: `audio_assets.path` records the root it was first written under, which is another
folder once a database is restored somewhere new or Compose's history is moved into the
desktop app, so it is never read to serve a recording.

### Practice

| Table | Holds |
|---|---|
| `sessions` | One sitting: user, scenario or none, mode, status, timing, end report |
| `turns` | One utterance: transcript, word timings, ASR confidence and model |
| `attempts` | One read-aloud reading: passage, audio, transcript, WER, scoring status |
| `answers` | One spoken answer to a prompt: transcript, word timings, what was counted, the model's feedback |
| `presentations` | One script the learner pasted, kept whole, with the listener's brief when one has been written |
| `presentation_sections` | One rehearsable piece of it: the text, its word count, the time it is meant to take, and the words that cannot be turned into phones |
| `rehearsals` | One take of one section: transcript, word timings, the alignment against the section, the delivery counts, and the state of its sound scoring |
| `rehearsal_phones` | One scored phone of one take — the columns `phoneme_scores` holds for a reading |

`answers` is not a kind of session. A session is a conversation, and an answer written as
one would be analysed like a turn and counted into the weekly figures built from turns, so
a prepared monologue would move the conversation's speech rate. It keeps `delivery` (the
fluency numbers), `structure` (signposts, sentences, repeats, restarts — every count,
including the ones no page shows yet) and `feedback` (the model's, with its check and
status) as JSONB, read whole; `again_of` points at the answer a second attempt says again.
The recording is never kept.

A script is kept whole as well as split, so the split can be redone without asking for
the text again, and `rehearsals.audio_asset_id` is nullable where `attempts.audio_asset_id`
is not: a reading can be scored again later and needs its waveform, while a take is scored
once, as it arrives, and an account that keeps no recordings loses only the replay.
`rehearsal_phones` is a table of its own rather than a nullable column beside
`phoneme_scores`, because the phone trends are built from passages every speaker reads —
mixing in text a learner chose would let them move their own baseline by choosing what to
write.

`turns.words` is JSONB — `[{w, start_ms, end_ms, logprob}]` straight off the recogniser.
It is read whole, for one purpose (the §7.1 fluency metrics), and never queried across
rows. A `words` table would add roughly 150 rows per turn and buy nothing.

`turns.asr_confidence` is the gate. A turn the recogniser was unsure of must not feed an
accuracy trend: an ASR error scored as a grammar error is a correction the user cannot
act on, and a trend line that moves for the wrong reason.

`attempts.status` is a lifecycle, not a flag, because scoring is asynchronous — ffmpeg,
faster-whisper, G2P, wav2vec2 and forced alignment is seconds of work. `error_message` is
FR-16: a failure has to be able to say why, or it cannot be retried meaningfully.

### Writing — Say it in English

| Table | Holds |
|---|---|
| `captures` | One time English was asked for: what was said, typed or copied, where, the versions, a check's fixes, what each version dropped, the timings, the practice box |
| `capture_attempts` | One time the person wrote it in English themselves |
| `written_errors` | One mistake in what they wrote: span, category, original, fix, and who found it |
| `capture_phrases` | One phrase worth keeping: the words said and the English for them |

A capture keeps text only, whatever `retain_audio` says, as an answer does: the recording
is heard, written in English and dropped. `mode` is `translate` or `check`, `via` is
`voice`, `typed` or `copied`, and `chosen` names the version that went on the clipboard —
`direct`, `organized`, `corrected` or `polished`, each a column of its own, or `rough`, the
recogniser's own English, kept when the model did not answer. `app_name` is the app that
was in front, as macOS names it. `dropped` is what the keep check found missing from each
version, and it is recomputed whenever a capture is read, so a name the account's later
captures teach is checked in an earlier one too. `fixes` is a check's list as the panel
showed it, a spoken check's included. `box` and `due_at` are the spacing of practice: 1,
3, 7, 14 and 30 days, back to the first after any counted mistake.

`written_errors` has the columns of `language_errors`, with `attempt_id` in place of
`turn_id` and no `asr_suspect`: no recogniser stood between the person and what they
typed. It is a table of its own so that a written mistake can never move a spoken figure.
Its `detector` is `llm`, `rule` or `dictionary`, and its category is one of the closed
taxonomy's or `SPELLING`, the one category written text can have and speech never does. A
typed or copied check stores the person's own text as the capture's first attempt, so its
mistakes count as writing; a spoken check stores none.

`capture_phrases` keeps only pairs found word for word in both texts. The model picks
them, and a pair it rephrased rather than copied is dropped.

While saving is paused none of these is written, and deleting a capture deletes its
attempts, their mistakes and its phrases.

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

CHECK constraints instead, where the vocabulary has two or three members or is expected
to change: `turns.role`, `language_errors.detector`, `progress_snapshots.period`, a
capture's `mode`, `via` and `chosen`, and `written_errors.detector`.

`language_errors.category` and `written_errors.category` have neither. The taxonomy *is* closed, but it is enforced in the
application layer, because it is revised as real transcripts are read, and a revision
should be a code change with a test rather than an `ALTER TYPE` that cannot run inside a
transaction.

`cefr_band` is TEXT in the database and a closed enum at the API edge
(`api/models/common.py`), which is what makes `?band=B7` a 422 rather than an empty list.

---

## 3. Why JSONB, five times

`scenarios.target_grammar`, `scenarios.target_functions`, `scenarios.target_errors`,
`scenarios.rubric`, `passages.phoneme_focus`, `turns.words`, `sessions.report`,
`presentation_sections.unscorable_words`, `rehearsals.words`, `rehearsals.alignment`,
`rehearsals.delivery`, `rehearsals.pron_summary`, a capture's `fixes`, `dropped` and
`timings`, an attempt's `forms` and `rejects`, and the five families on
`progress_snapshots`.

Two different reasons, worth keeping apart:

- **Lists that are filtered by containment** — `target_grammar`, `target_errors`,
  `phoneme_focus`. The query is `@>`, one indexable predicate, and GIN indexes it when the
  seed set outgrows a sequential scan over a dozen rows.
- **Documents read whole for one screen** — `rubric`, `words`, `report`, a take's
  `alignment`, `delivery` and `pron_summary`, a capture's fixes and what it dropped, and
  the progress families. Nothing queries inside them across rows. The set of fluency measures is still
  moving, and a schema migration per metric added is a tax on exactly the experimentation
  this project exists for — the progress rollup added three keys to `sample_counts` without
  touching the schema.

The counter-example is the rule: `language_errors` and `phoneme_scores` are tables, not
JSON columns, precisely because they *are* aggregated across rows — by category, by phone,
over time.

---

## 4. Indexes

Each for a query that exists:

| Index | The question |
|---|---|
| `ix_sessions_user_id_started_at` | This user's history, newest first |
| `ix_language_errors_turn_id_category` | Errors on a turn; errors by category over a window |
| `ix_phoneme_scores_attempt_id` | Everything about one reading — the result screen |
| `ix_phoneme_scores_canonical_phone` | One phone's history — the trend under the result |
| `ix_captures_user_id_created_at` | The Notebook, newest first, by day |
| `ix_capture_attempts_capture_id_created_at` | Everything written for one capture, in order |
| `ix_written_errors_attempt_id` | The mistakes in one attempt |
| `ix_capture_phrases_capture_id` | One capture's phrases |

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

`0008` is the one revision that creates tables using an enum it does not own:
`rehearsals.pron_status` reuses `attempt_status`, declared with `create_type=False`, and
the revision neither creates nor drops it. Two enums with the same four values would be two
vocabularies to keep in step.

The downgrade drops the enum types as well as the tables. A downgrade that leaves a type
behind fails on the *next* upgrade, as `type "session_mode" already exists`, minutes after
the mistake was made; up, down and up again is one of the tests.

---

## 6. Seeds

```bash
make seed             # idempotent — the second run inserts nothing
```

Scenarios, passages and answer prompts are **seeded data, not fixtures**: real rows,
versioned as JSON in `api/seeds/`, so a content edit is a reviewable diff. A prompt's
kind is one of four and its time limit between 60 and 120 seconds, checked on load. The loader keys on `slug` and
reports three outcomes separately — inserted, updated, unchanged — because only the third
makes a second run a no-op, and a script that printed "8 scenarios loaded" both times
would be telling the truth in a way that hides the thing worth knowing.

Every record is validated through the same Pydantic models the API serves before anything
touches the database, so a typo fails the load, naming the field and the record, rather
than surfacing as a 500 a week later. `passages.word_count` is *derived* from the body
rather than stated in the file, so the file cannot disagree with itself.

`phoneme_focus` is validated against the 39 ARPAbet symbols in `api/models/common.py`.
That tuple and the pronunciation service's `phone_map.py` are two copies of one phone set,
and `tests/test_phone_map.py` asserts they are equal: a phone missing from one of them is a
pronunciation error that is never scored and never reported as unscored.

---

## 7. What is not here yet

Two columns exist that nothing writes. `audio_assets.device_hint` is there so a chart can
mark the day the microphone changed, and nothing fills it in. `progress_snapshots.cefr_estimate`
is there so an estimated band would be recorded once rather than recomputed by each screen
that shows it, and nothing writes one: a band assigned from a handful of turns would be a
confident answer to a question this data cannot settle.

There is no way to delete an account, or an answer. A session can be deleted, and takes
its turns, their measurements and any recording left with nothing pointing at it; a
capture can be deleted, or every one of them at once, and takes what was written for it. What an
account holds can be taken away whole, as one JSON document: `GET /progress/export`.
