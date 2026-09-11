# 0006 — Grammar analysis and the closed error taxonomy

**Status:** accepted · **Date:** 2026-09-05 · **Milestone:** m9

Read this before changing the taxonomy, the labelling prompt, the confidence gate, or
anything that turns a model's opinion into a row a learner is shown.

---

## What was decided

1. **Two detectors, and they are not alternatives.** A dependency parse counts which
   forms were *used*; a language model proposes *errors*. The first is what gets plotted,
   the second is what gets read.
2. **Every model proposal passes a gate before it becomes a row**, and the refusals are
   counted rather than dropped. The rejection *rate* is the measurement that answers
   whether the model is strong enough (Q4).
3. **The model quotes; this system locates.** A proposal names the words it thinks are
   wrong and the transcript is searched for them. It never supplies an offset.
4. **The confidence gate is per word, not per turn** — Q11, and it is resolved against
   real speech rather than reasoned about.
5. **Labelling runs at temperature 0.** It is a measurement, and a measurement that
   answers differently on a second run cannot be re-derived.
6. **Analysis is a background job** (Q3, confirmed), and ending a session waits for its
   own turns.
7. **Criterion S5 is not met, and on this corpus it is not decidable.** Detection
   precision measures **0.500**; the bar is 0.70; the sample is six scored proposals.
8. **Q4 is answered: `gemma3:4b` is not strong enough for this**, and a 7B alternative
   measured worse rather than better.

---

## 1. Two detectors, deliberately

`services/grammar.py` is spaCy morphology and dependencies. It counts twenty-seven closed
feature names — nine tense/aspect combinations, six modal groups, clause structure, the
three conditionals, passive, comparison, reported speech, duration, polite requests. It
is deterministic: the same transcript gives the same counts on every rebuild, which is
what makes it safe to plot over months.

`services/errors.py` is a call to `gemma3:4b`. It proposes corrections, which is a
judgement no rule set makes well.

**The split is not about accuracy, it is about what may move a chart.** A learner reaches
a zero error rate by only ever using the present simple, and counting only errors reports
that retreat as improvement. Counting which forms were *used* is what makes it visible —
and that count has to come from code, because a trend line drawn by prompt drift is worse
than no trend line at all.

**The feature vocabulary is closed for a second reason.** Scenarios declare the forms they
are built to elicit, in these exact names. `apartment-viewing` declares
`present_simple, comparatives, modal_can, going_to_future`. So "the scenario asked for
comparatives and none were produced" is a set difference, not an opinion — and a detector
that invented its own names would break that comparison silently: the form would be
counted, the scenario would still report it missing, and nothing would look wrong.
`test_grammar.py` asserts that every form any seeded scenario declares has a detector.

### What the parser gets wrong, and what was done about it

Four rules were changed after running against the real corpus rather than against
fixtures, and each was a wrong answer that looked right:

- **`going to` was invisible** because the pipeline was loaded with the lemmatizer
  excluded to save parse time. Without it, `going` never reaches `go`, and every rule that
  names a verb silently stops firing. `I'm going to work in the 565` was being counted as
  a present continuous. The lemmatizer stays; only the entity recogniser is excluded.
- **`more` was counted as a comparative** in *"I want to know more about the price"*. It
  carries `Degree=Cmp` and compares nothing. Comparatives now require the token to be
  modifying something.
- **`at least` was counted as a superlative.** `least` is `JJS`. It is a fixed phrase.
- **Every `to`-infinitive was counted as a subordinate clause.** The subordination index
  is a ratio, and both halves have to mean the same thing, so a clause here is a verb
  phrase that carries tense. *"It is difficult to have a really good unit"* is one clause.

The two features that are about intent rather than form — a polite request, and duration
with `for`/`since` — are deliberately narrow. They fire on a specific shape and miss the
rest. Undercounting a form leaves a gap in a chart; overcounting it tells a learner they
practised something they did not.

---

## 2. The gate, and why refusals are the interesting half

`services/taxonomy.py` holds the nine categories and their subcategories, and refuses a
proposal for one of eleven reasons. Four of them earn their place on real output:

| reason | what the model did |
|---|---|
| `unknown_category` | invented a label — `SPELLING` |
| `wrong_category_for_subcategory` | used a real subcategory under the wrong heading |
| `original_not_in_transcript` | quoted words nobody said |
| `punctuation_only` | "corrected" `also?` to `also,` |

**`punctuation_only` exists because of what the model actually did.** The transcript is
speech recognition output: the speaker never produced a capital letter or a comma. A first
run against real turns produced *"Add a comma after 'also' for clarity"*, filed under
`PREPOSITION / missing`. That is a correction of the recogniser, delivered to somebody who
cannot act on it. The rule is now deterministic: strip everything but letters and digits
from both sides, and if they match, refuse.

**A refusal is counted, not dropped.** It goes onto `turns.analysis_rejects` with its
reason and the text the model wanted to use. The reason answers *how often*, which is the
model's quality; the text answers *what did it want to say*, which is whether the taxonomy
is missing a category. Two different problems with two different fixes, and neither is
recoverable afterwards from the proposals that passed.

### One subcategory was added

`VERB_TENSE / non_finite_complement`, for *"I appreciate to be here"*. The requirements
call their subcategory lists "representative", and this is a verb-form error with nowhere
else to go: the governing verb decides whether its complement is a gerund or an
infinitive, and Spanish makes the opposite choice often enough that it is a recurring
first-language signal rather than a one-off. Categories stay closed; a subcategory is
added by changing that file, with a test.

---

## 3. The model never supplies a location

Asking a 4B model for character offsets and trusting them is the same bug as trusting its
labels, with an arithmetic step in front of it. So a proposal quotes the text and
`locate()` finds it: case-insensitively, matching any run of whitespace, bounded by word
edges so a quote of `go` cannot underline three letters inside `goes`.

A quote that appears **twice** is refused rather than attached to the first occurrence. An
error on the wrong occurrence underlines words the speaker got right, and there is no way
to tell which was meant.

The stored `original` is then taken from the transcript at that offset, not from the
model — so a model that changed the capitalisation while quoting cannot make the row and
the transcript disagree.

**A quote longer than twelve words is refused too.** A model asked to point at a mistake
will quote the whole sentence, and a whole-sentence quote is three problems at once: an
underline nobody can read, a span that collides with every other error in the turn, and —
covering more words — one far likelier to touch a word the recogniser was unsure of and be
kept out of the trend it belonged in. The limit costs recall, visibly: it accounts for two
of the four refusals in the run below.

---

## 4. The confidence gate is per word (Q11)

The turn-level gate was aimed at the wrong number, and one stored turn settles it.

Session 3, turn 6, `asr_confidence` **0.899** — comfortably above the 0.60 floor:

> *"yes looks amazing I appreciate to be here and let's look **department** I know it's a
> very popular area..."*

"department" is *"the apartment"*, misheard. Its own probability is **0.41**; "yes" is
0.31; **28 of the other 30 words are above 0.69**. The turn score *is* the mean of the
per-word scores, so a locally wrong word is averaged away by its confident neighbours and
**no turn-level threshold can reach it**.

So the gate reads `turns.words`, which has stored the log-probabilities since m4. An error
whose span overlaps a word below the floor is stored, shown, and marked `asr_suspect` —
and excluded from every rate. Deleting it would leave the transcript with a hole in it;
counting it would let a mishearing move a number about the speaker.

**A property that made this exact:** for all seven stored turns, joining `words` with
single spaces reproduces `transcript` character for character. The implementation does not
rely on it — it searches forward for each token, so a recogniser that stops holding that
property costs a missed marker rather than a set of spans silently off by one word.

**0.60 is still a placeholder and now there is a number for how wide a net it is.** Across
the whole stored corpus it marks **28 of 272 words, 10.3 %**, and most of those are
transcribed correctly. Q11's original note — that it "flags exactly the two suspect words
and nothing else" — held for one turn and does not hold for the corpus. Calibrating it
needs learner speech with a reference transcript, which this project still does not have.

The cost is real and visible: two of the eleven labelled gold errors sit under flagged
words. *"or is not possible"* is a genuine omitted subject and `is` scores 0.59; *"any
blocker"* is a genuine plural error and `blocker` scores 0.51.

---

## 5. Temperature 0

The provider gained a `temperature` argument, passed through only when a caller sets one,
so conversation keeps Ollama's default where variety is the point.

Labelling sets it to zero, and not as tuning. **A backfill re-run must not rewrite a
learner's history.** At Ollama's default of 0.8 the same turn produced different errors on
consecutive runs, and one turn came back as unparseable JSON on one run and valid on the
next. Two runs of the measurement suite at temperature 0 produce identical output.

---

## 6. The measurement

`make error-precision`. Four real turns in a clone, seven here (§8). The published set is
four turns, 123 words, five labelled learner errors.

**`gemma3:4b`, seven turns, temperature 0:**

```
proposals                 16
rejected by the taxonomy  4 (25.0 %)
  reasons                 correction_equals_original 1, span_too_long 2,
                          punctuation_only 1
scored                    6      (excluded as unknowable: 6)
  true positives          0
  right span, wrong label 3
  false positives         3
detection precision       0.500
labelling precision       0.000
detection recall          0.333
```

**Span detection is mediocre; category labelling is worse than mediocre.** Three of the
six scored proposals landed on a real error and named the wrong category for it:

| the model said | the error actually is |
|---|---|
| `PREPOSITION / wrong` on *"I appreciate to be here"* | `VERB_TENSE / non_finite_complement` |
| `WORD_ORDER / adjective_order` on *"I'm going to work in the 565"* | `PREPOSITION / wrong` |
| `PREPOSITION / wrong` on *"we request to the DevOps team"* | `VERB_TENSE / missing_past_marker` |

The corrections in all three are right. It is the filing that is wrong, and `WORD_ORDER`
is being used as a catch-all — which matters, because the categories are what a trend is
grouped by.

**Criterion S5 is not met.** It is also not *decidable* on this corpus: six scored
proposals put a 95 % interval on 0.500 roughly half the width of the scale. The
measurement suite therefore prints its figures and asserts none of them. What it asserts
is the machinery — every accepted error points at text really in the transcript, every
rejection carries a reason from the closed list, and the one turn with nothing wrong in it
produces nothing.

### Comparison arms (Q4)

Same prompt, same gate, same golden set.

| model | detection precision | labelling precision | recall | rejection rate | seven turns |
|---|---|---|---|---|---|
| `gemma3:4b` | **0.500** | 0.000 | 0.333 | 25 % | 48 s |
| `mistral:7b` | 0.333 | 0.000 | 0.444 | **47 %** | 165 s |
| `gpt-oss:20b` | — | — | — | — | 207 s |

**`mistral:7b` is worse, not better.** It proposes twice as much and half of it is
refused; it produced *"Thank you"* → *"Thanked you"* on the one turn with nothing wrong in
it. So the answer to Q4 is not "use a bigger model" in the general case — it is that this
task is hard for a local instruct model of this size, and a 7B one is not the fix.

**`gpt-oss:20b` could not be measured at all, for a reason worth recording.** It returned
`message.content` as the empty string with all 800 completion tokens spent: it is a
reasoning model and Ollama puts its answer in `message.thinking`. `services/llm/ollama.py`
reads `message.content` and nothing else, so **this system cannot currently use a
reasoning model as a provider**. That is a real limitation with a small fix, and it is not
a statement about the model's ability.

---

## 7. What is stored, and where

Migration `0003` adds five columns and one enum type. **No tables** — `fluency_metrics`,
`grammar_usage` and `language_errors` were created complete by `0001`.

- `turns.analysis_status` — `pending | analyzing | analyzed | failed`, **nullable**, and
  NULL is a fact: only user turns are analysed. It separates "analysed, and there were no
  mistakes" from "not analysed yet", which are otherwise the same empty result set and
  mean opposite things to a report. `analyzing` is a claim, and it is what stops a live
  job and a backfill both writing rows for one turn.
- `turns.analyzed_at`, `turns.analysis_error` — the same pair as `attempts.scored_at` and
  `error_message`, for the same reason: a retry needs a reason to mean anything.
- `turns.analysis_rejects` — the refusals, with reasons.
- `language_errors.asr_suspect` — §4.

**A turn whose labelling model was down is still `analyzed`.** Fluency and the parse are
arithmetic; they succeed whether or not Ollama is running, and they are written either
way, with the reason in `analysis_error`. Calling the whole turn `failed` would hide work
that had already succeeded and invite a retry that recomputes it. `failed` is reserved for
a turn with nothing on it.

**Ending a session waits for its own analysis** (Q3, confirmed as background). Analysis
runs behind each turn, so the only one usually outstanding when somebody stops talking is
the last thing they said. It is waited for because the report is stored once: written a
turn early, it would be missing that turn for ever. The wait is bounded — 60 s by default,
against a measured median of **4.9 s per turn** — and a report written short says how many
turns it is missing. Opening the session again finishes them and rebuilds the counts,
keeping the stored prose.

> **Corrected later.** As built here, ending skipped a turn the live job had already
> claimed — the usual state of the last one — and opening a session only read it back, so
> neither sentence above was true. Both are now: ending waits for a claimed turn, and the
> session page finishes a short report when it is opened. `0014` §7 records how it was
> found, and the changelog how it was measured.

---

## 8. What ships, and what does not

The golden set is real recorded speech, and three of its seven turns are the speaker's
standup at work: a real team, a real certificate, real ticket numbers. This repository is
public.

So the set is split. `labels.json` and `manifest.json` carry the `apartment-viewing`
role-play and one closing line — four turns, 123 words, five labelled errors.
`labels.local.json` and `manifest.local.json` carry the rest and are gitignored;
`build.py` writes them when the labels are there, and the measurement suite prefers them
and prints which set it read. Both numbers are in §6; the seven-turn one is the one this
document quotes, and a clone reproduces the four-turn one.

---

## 9. The cost of the parse

**The API image went from 425 MB to 811 MB.** In `site-packages`: spaCy 134 MB, numpy
68 MB, thinc 16 MB, `en_core_web_sm` 15 MB, blis 10 MB.

That is a lot for a 12 MB model, and it nearly doubles the image that is meant to start
fastest. Two alternatives were weighed. A fourth service holding the parser keeps the API
small and adds a container and an HTTP hop for a dependency parse that takes 40 ms. Hand-
rolled morphology over the tag set avoids the dependency and cannot do clause structure at
all, which is half of what the requirement asks for.

The image still contains **no torch and no speech model weights**, which is the property
the health suite asserts. It is now the only image in the system carrying a statistical
model that is not a speech model, and that is worth revisiting if start-up time ever
becomes the constraint.

---

## 10. What is not settled

- **S5, still.** The instrument exists and runs; the corpus does not support a
  conclusion. It grows by somebody using the product.
- **The golden labels are not independent.** They were written by the same agent that
  wrote the detector's prompt, in one pass, before any detector existed — that ordering is
  the only thing keeping them from being a description of what the detector does. A second
  annotator is the missing piece.
- **`ASR_CONFIDENCE_FLOOR = 0.60` is uncalibrated**, and §4 now says how wide a net it is.
- **`ERROR_CONFIDENCE_FLOOR = 0.50` is uncalibrated too**, and the model's self-reported
  confidence did not discriminate on this corpus: it answers 0.9 to most things.
- **A rule layer was not built.** `language_errors.detector` allows `'rule'` and every row
  so far is `'llm'`. Subject–verb agreement and article omission are the two categories
  where the parse is reliable enough to propose errors on its own, and they are the
  obvious way to raise precision without a bigger model.
- **Response latency is a floor, not the measurement.** `fluency_metrics.response_latency_ms`
  holds the silence before the first word of the recording. The real measure starts when
  the persona stops speaking, and needs the browser to timestamp the button.
- **Fillers are undercounted twice over.** The recogniser drops most of them before this
  code sees them — the whole corpus contains none — and bare `like` is not counted at all,
  because *"like a dog or a cat"* is an ordinary preposition.
