# 0007 — Progress: rollups, gates and recommendations

Status: accepted · §5's limit on accuracy per form superseded by [0015](0015-accuracy-per-form.md)

Read this before changing what the progress page draws, what it refuses to draw, or how
anything on it is ranked. The arithmetic is simple; almost every decision here is about
what *not* to say.

---

## What was decided

1. **Snapshots are materialised, and the page computes nothing.** `GET /progress` reads
   `progress_snapshots` and assembles series. Aggregating raw turns on page load gets
   slower every week somebody practises, which is backwards.
2. **The sample gate is the feature.** A period below the floor is a **hole with a reason
   on screen**, not an omitted point, and a series with no periods above the floor comes
   back suppressed saying what it is waiting for.
3. **A number is drawn; a verdict is earned.** A direction is claimed only for a metric
   with a defensibly better end *and* at least three measured points. Most fluency
   measures have no better end at all and are reported without one, for ever.
4. **Pronunciation is z-scored against the speaker's own readings**, per sound, with the
   *reading* as the sampling unit — never against other people, and never as a raw score
   compared across weeks.
5. **Recommendations are a transparent weighted score** over three stored sources, with
   the measurement printed under every entry, and a stated confidence that comes from the
   same sample counts the charts are gated on.
6. **Criterion S7 cannot be met on the corpus this was measured against.** It asks for
   30-day trends across four families from ≥ 20 real sessions; the corpus held **2**
   conversation sessions and **2** scored readings, on one calendar day, for one account.
7. **Migration `0004` adds one column and no tables.** `progress_snapshots` is created
   complete by `0001`; `updated_at` is what `0004` adds.

---

## 1. Why materialise at all

The progress page reads one row per period and nothing else. The alternative — computing a
month of trends from raw turns on each request — is fine for the first month and degrades
continuously after it, and it degrades *fastest for the people with the most to look at*,
which is precisely backwards for a feature about long-term practice.

Measured on this machine, on the stored corpus (7 analysed turns, 2 scored readings, one
account):

| | |
|---|---|
| Read the page from snapshots | **7 ms** |
| Rollup with nothing to do | **7 ms** |
| Forced rebuild of both snapshots | **17 ms** |
| Load the corpus a rebuild reads | **57 ms** |

Those numbers are too small to prove anything about scale and are recorded for what they
say about *shape*: the page read is a function of how many periods are in the window, and
the rollup is a function of how much has been practised. Only one of the two grows.

**When the rollup runs.** Ending a session rolls that account up, because that is the
moment its numbers stop changing. Read-aloud scoring finishes after the request that
started it and belongs to a session nobody ever "ends", so `POST /progress/refresh` and
`make rollup` exist as well. `GET /progress` reports `stale` — three aggregate queries, no
scan — so the page can offer a rebuild instead of paying for one on every visit.

**Ending a session commits before it rolls up**, and that ordering is load-bearing. The
report is flushed but not committed at that point; a broken rollup rolled back would take
the report with it, and a session would end without one. A chart that is a day behind is
the cheaper failure by a long way.

---

## 2. The gate, and the numbers behind it

How many read-aloud attempts should be behind a phoneme trend before it is shown? Five —
and every family needs a floor, not the same floor, because they are not the same
measurement.

| Gate | Value | What it protects |
|---|---|---|
| `PROGRESS_MIN_WORDS` | 50 words per period | Fluency and accuracy are rates *per unit of speech*. One filler in an eleven-word answer is 9 per 100 words, a spike the speaker cannot see in themselves and cannot act on |
| `PROGRESS_MIN_ATTEMPTS` | 5 scored readings | Pronunciation scores move with the microphone, the room and the distance from it. The first few readings describe the setup as much as the speaker |
| `PROGRESS_MIN_PHONE_SAMPLES` | 5 instances of one sound | A passage engineered around one sound yields it thirty times; a sound that turned up twice is a sample of two, whatever the reading around it was worth |
| `PROGRESS_MIN_POINTS` | 3 measured points | A line through two points is a line through noise, and "improving" is the sentence a learner would act on |

**A gated period is drawn as a hole, not dropped.** This is the decision most likely to be
undone by somebody tidying a chart. A series drawn only from the periods that cleared the
floor compresses a thin fortnight into the space between two adjacent points — silence
rendered as continuous practice, which is the most flattering lie this page could tell. So
the point stays in the array with `value: null` and a `withheld` string, the line breaks
there, and the component draws two polylines rather than one.

**Every suppression is a sentence, not an absence.** `Gate` carries `reason`, `have` and
`need`. "2 scored readings so far. Per-sound trends start at 5, because the first few
readings describe your microphone as much as your mouth" is an instruction; an empty panel
is a bug report.

---

## 3. A number is drawn; a verdict is earned

Each metric declares which end of its scale is better, and most of them declare nothing.

| Family | Metric | Better | Why |
|---|---|---|---|
| fluency | speech rate, articulation rate, pause ratio, words between pauses | **none** | Faster is nerves as often as it is fluency; less pausing is rushing as often as it is ease. Both directions have an innocent and a worrying reading |
| fluency | fillers per 100 words | lower | The one fluency measure with a goal every speaker recognises, and unlike speed it does not trade off against care |
| accuracy | errors per 100 words | lower | |
| complexity | different forms used, clauses inside clauses | higher | Breadth is the thing a shrinking repertoire hides |
| complexity | form instances | none | It grows with how much was said |
| pronunciation | against your own baseline | higher | |
| pronunciation | raw score | none | It moves with the hardware |

A series with no `better` gets `direction: null` from the API and the component renders no
badge. It is not a gap waiting to be filled: *"your speech rate is improving"* is the
easiest sentence on this page to write and the least defensible one on it.

---

## 4. Pronunciation: a distance, not a score

Raw goodness-of-pronunciation is partly a measurement of a microphone. Comparing it across
weeks compares equipment; comparing it across people compares rooms. So what is plotted is
a z-score against the same speaker's own recent readings.

**The sampling unit is the reading, not the phone instance.** The forty instances of one
sound inside a single reading were produced in one room, at one distance from one
microphone, in one sitting. Treating them as forty independent samples would make every
baseline look far tighter than it is, and every later reading would then appear to be a
dramatic change. So a baseline is the distribution of *per-reading means* for that sound,
over readings strictly before the period, within `PROGRESS_BASELINE_DAYS`.

**It refuses more often than it answers, and that is correct.** Fewer than two prior
readings, or a spread of zero, and the z-score is `null` rather than `0.0` — zero would
draw a speaker sitting exactly on a baseline that does not exist. In a first month that is
every sound, and the panel says so per row.

**Stress is folded away before anything is counted.** The aligner scores `AH0`, `AH1` and
`AH2` separately; a learner is told to work on a *sound*. Leaving the digits on would split
one phone's history into three series, each thin enough to be suppressed by its own sample
gate — so the trend would disappear for exactly the vowels that occur most.

**There is no pass mark, and this page does not invent one.** The method for a threshold is
settled and the numbers need recordings from more than one speaker
([0005](0005-gop-pipeline.md) §7). Everything here therefore ranks sounds against each other
and against their own history, and never says a sound is wrong.

**The device annotation is computed and inert.** `audio_assets.device_hint` exists,
`sample_counts.devices` records the distinct hints a period's readings used, and nothing
populates the column — so the list is empty and no chart is ever annotated. It exists so
that the day something populates it, the annotation is already there rather than needing a
migration of history.

---

## 5. Breadth beside accuracy, and the one warning

A learner who retreats to the present simple produces fewer errors. An accuracy chart on
its own calls that improvement, and it is the specific failure this product exists to be
able to avoid — so the repertoire is rendered next to it, and one combination gets a
sentence rather than a line: **fewer distinct forms *and* a lower error rate than the
previous period.**

Every other combination is left to the numbers. A narrowing repertoire with a *rising*
error rate is a bad week and already looks like one; a warning there would be noise.

**Accuracy per form is [0015](0015-accuracy-per-form.md)'s.** A correction is applied, the
corrected text is parsed, and the verb phrases before and after are compared, so each
correction carries the form it was said in and the form it needs — as right as the
corrections it is given.

---

## 6. Recommendations: a weighted score, and no model

Three sources, each normalised within itself, weighted, and decayed by how old the evidence
is:

| Source | Weight | Severity |
|---|---|---|
| Error categories | 1.0 | The category's rate per 100 words, relative to the largest |
| Weak sounds | 0.9 | Distance below the speaker's own baseline, or the raw score where there is no baseline |
| Unused forms | 0.8 | How far below `FORM_FAMILIARITY` (5) the form's usage sits |

Errors lead because a correction is the most concrete thing this system knows about a
speaker. Sounds come next: a phone score rests on a model that heard the waveform, which is
a stronger claim than anything read off a transcript. Unused forms come last because "you
have not said this" is an absence, and an absence has more innocent explanations — nobody
asked, it did not come up.

**Recency is a multiplier, not a filter.** Evidence from this week counts fully and evidence
at the far edge of the window counts half, never zero: a weakness measured a month ago is
still the best guess available about somebody who has not practised since.

**Why not something learned.** A ranker would need training data this project does not have
and could not explain itself if it had it. The entire value of a recommendation here is
that a learner can check it — *"two corrections in 272 words"* is a claim they can go and
look at. It is also, deliberately, the one place on this page where a language model would
have been easiest to reach for.

**The candidate pool for forms is what the catalogue declares**, not the parser's 27-name
vocabulary. Recommending a form nothing is built to elicit would be advice with nowhere to
act on it.

**Confidence is stated.** `none` / `low` / `moderate` / `good`, computed from the same word
and reading counts the charts are gated on. The stored corpus returns **low**, and the
detail string says why in the learner's own units.

**Two small things real data changed.** Two categories tied at two corrections each would
*both* say "your most frequent category" — so that clause is used only when one category
uniquely is. And a sound with no baseline is not described as "mean score −7.1", as though
−7.1 meant something to a reader; it is described as among the weakest in the learner's own
readings, with no pass mark calibrated.

---

## 7. Criterion S7 is not met, and it is not close

> **S7** — The progress page renders 30-day trends for all four metric families from ≥ 20
> real sessions.

What the database held for the only account with practice on it, when this was measured:

| | |
|---|---|
| Conversation sessions | **2** |
| Analysed user turns | **7** |
| Words | **272** |
| Scored readings | **2** |
| Phone instances | **450** |
| Calendar days with practice | **1** |
| Weeks with practice | **1** |

So three of the four families draw a single point, and the fourth is gated off entirely at
2 readings against a floor of 5. No direction is claimed anywhere on the page, because no
series has three points. That is the page working correctly, and it is worth being precise
about what has and has not been demonstrated:

- **Demonstrated:** the arithmetic, on real stored rows, cross-checked against the error
  analysis's independently reported figures ([0006](0006-error-taxonomy.md)) — 272 words and
  11 distinct forms match exactly, and the error rate of 2.57 per 100 words is the 7 counted
  errors of 12 that its confidence gate left standing.
- **Demonstrated:** every gate, every suppression message, and the hole-not-omission
  rendering, against fixtures.
- **Not demonstrated:** that a trend over many weeks reads correctly, that the z-score is
  informative on real baselines, or that the recommendations pick well. All three need
  somebody to practise more than once.

S4, S5 and S7 are measured and missed rather than dropped, and the pattern is worth naming:
the criteria that fail are the ones that need *use*.

---

## 8. What is stored, and where

Nothing new is stored per turn. One row per user per period, at two granularities:

| Column | Holds |
|---|---|
| `fluency` | Word-weighted speech rate, articulation rate, pause ratio, words between pauses, fillers |
| `accuracy` | Errors per 100 words, by category, and the two exclusions reported separately |
| `complexity` | Distinct forms, instances, per-form counts, subordination index |
| `pronunciation` | Per-sound mean and z, with the baseline it was scored against |
| `sample_counts` | Turns, words, sessions, readings, phone instances per sound, counted and excluded errors, devices |
| `cefr_estimate` | **Nothing writes it.** A band assigned from seven turns would be a confident answer to a question this data cannot settle |
| `updated_at` | Added by `0004`. What makes "is this snapshot current?" answerable at all |

**Weekly snapshots are computed from turns, not from seven daily snapshots.** Averaging
averages would weight a quiet Tuesday the same as a long Sunday.

**Periods are UTC days.** A local day needs a time zone this system does not ask for and
would reshuffle history the first time somebody travelled. A late-evening session west of
Greenwich lands on the next day's row; the weekly granularity the trend actually uses
absorbs it.

**The rollup replaces rather than merges**, so a deleted session takes its contribution off
the chart, and a snapshot whose period no longer has any data is deleted rather than left
behind as a point with nothing underneath it.

---

## 9. What ships

Three operations:

| | |
|---|---|
| `GET /progress` | Series, gates, sounds, repertoire, totals, staleness |
| `GET /progress/recommendations` | Ranked suggestions with reasons and confidence |
| `POST /progress/refresh` | Rebuild this account's snapshots, then return the page |

None takes a user id. There is no shape of this API in which one account reads another's
trends, and the ownership inventory test names all three.

**The charts are hand-drawn SVG and there is no charting library.** What this page needs is
a polyline through at most a few dozen points, and every library draws a *continuous* line
through whatever it is given — making one render absence correctly is more work than not
using one. It also keeps the frontend's dependency list unchanged.

---

## 10. What is not settled

- **S7, above.** It needs use, not code.
- **The direction rule is a first pass.** First measured point to last, over at least
  three. It is not a regression, it has no confidence interval, and on a noisy series it
  will call a direction that a fitted slope would not. It is honest about being a
  comparison of two endpoints and nothing more.
- **`PROGRESS_MIN_WORDS = 50` is reasoned, not measured.** So is the baseline window. All
  of them are the kind of number that should be revisited against a corpus with months in
  it, and none can be until there is one.
- **The accuracy family carries a 0.50-precision caveat on screen.** That is the honest
  rendering of what [0006](0006-error-taxonomy.md) measures; raising it is the rule layer's
  job ([0014](0014-the-rule-layer.md)), not this page's.
- **CEFR is a column nothing fills.** Whether this product should estimate a band at all is
  a product question, and estimating one from a handful of turns is not the way to answer
  it.
