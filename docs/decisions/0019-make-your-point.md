# 0019 — Make your point: a spoken answer, counted

Status: accepted · 2026-09-12

The owner asked for training in articulating ideas clearly, and chose both halves when
asked: how an idea is built when it is spoken, and how it is delivered. The plan turned that
into a drill — one spoken answer to a work prompt, no persona — with how the answer is built
and how it was said counted by code, a language model's feedback beside the counts, and a
second attempt to compare. It left four questions open: the feature's name on screen, a
session mode or tables of its own, prompts as a table or as scenarios, and which measures
reach `/progress`.

## What was decided

1. **Named *Make your point* on screen**, at `/answers`, with a rail entry of its own.
   "Articulation rate" already names a speed measure here — words over phonated time — and a
   page that said "articulation" about two different things would be read as one.
2. **Tables of their own, not a session mode.** `answer_prompts` (seeded, 13 prompts) and
   `answers`, migration `0007`. No change to `sessions`.
3. **Two operations**, `GET` and `POST /answers` — 30 of the 30 forecast.
4. **How an answer is built is counted by `services/structure.py`**, and each measure was
   scored against answers labelled by hand and held out from the writing of the code, before
   any screen showed it. **Restarts are counted and stored and not shown**: they fell below
   the bar.
5. **The model's shorter version is checked, not trusted**: one with more than two content
   words the speaker never said is withheld, with the words that withheld it. The model's
   instruction was revised against the development answers, and on the held-out ones the
   withheld rate fell from 13 of 16 to 2 of 16.
6. **Press to start and press to stop, with the prompt's time limit stopping it**, not the
   held button a conversation turn uses.
7. **Over time lives on the answers page, not on `/progress`**, one point per answer; only
   fillers and words said twice are ever called improving.
8. **The recording is not kept**; the transcript, the word timings and the counts are.

---

## 1. The instrument, before any measure

`api/tests/answer_labels.py` was written before the counter. Every answer is something a
learner could say to one of the seeded prompts, written the way the recogniser writes —
sentence case, commas where a voice pauses, digits, a word said twice written twice — with
every signpost marked by what it does, and every repeat and restart marked:

- **24 development answers** (2 115 words) to write the counter against;
- **16 held-out answers** (1 469 words), not read while it was written;
- **37 readings** of the words with a second use — *so*, *since*, *then*, *first*, *but*,
  *while*, *though*, *overall* — each read both ways;
- **12 answers to be said aloud** by the `tts` voice, with fillers, repeats and restarts in
  them.

**The bars were set in the same file, before anything was measured**: a measure is shown
only if, on the held-out answers, its precision is at least 0.90 and its recall at least
0.75 over at least ten marked; repeats and restarts must also reach the transcript at least
half the time; sentences are shown only if the recogniser's count is within one of the
written count in three answers in four. Every kind has 11 to 22 marked instances in the
held-out set.

**What a signpost is.** Five functions: a *reason* (a cause, a purpose, a consequence — *so*
joining a result counts here), an *example*, a *sequence* step, a *contrast*, and a *close*
that sums up. *So* opening an answer is how people start talking and is nothing; *so*
opening the last sentence sums up. *Like* where it means for example is marked, because a
teacher would mark it, and the counter never counts it.

## 2. What reaches the transcript

The fluency code already said the recogniser drops most fillers. Whether it drops a word said
twice, or a phrase begun again, decides whether those can be counted at all, so it was
measured first: the twelve aloud answers spoken by `en_US-lessac-medium`, heard by
`small.en`. Synthesis is not deterministic, so it was measured twice — the second time by
the full evaluation run.

| Written down, of those spoken | Run 1 | Run 2, the evaluation run |
|---|---:|---:|
| Fillers | 21 of 24 | 22 of 24 |
| Words said twice | 12 of 13 | 13 of 13 |
| Phrases started again | 9 of 9 | 8 of 9 |
| Signposts | 52 of 52 | 52 of 52 |
| Sentence count within one of the written | 10 of 12 answers | 11 of 12 answers |

Both recogniser bars are met in both runs. In the first the one repeat lost was *The sprint
is, the sprint is*, heard as *The sprint it is, the sprint is*; in the second the one restart
lost was *we are going to, we are building*. The sentence counts that missed were answers
heard as two long sentences where five and six were written: the recogniser's full stops
are where the voice fell, and a sentence count is a count of those.

**What it is not.** A synthetic voice says *um* as a clear word and a repeat as two clean
copies. This is the recogniser with the clearest version of each, not with a person's
hesitation — which is a sound, and which the fluency code's note is about.

## 3. The counter, and how it scored

`services/structure.py` matches the listed phrases — *for example*, *however*, *to sum up* —
as tokens of the same parse the grammar counter uses, and lets the dependency parse decide
the words with a second use: *so* before an adjective or an inverted verb is not a result,
*since* is a reason only as a subordinator under a main clause that is not a perfect, *then*
answering an *if* is not a step, and an ordinal is a step at the start of a clause or before
*step*, *thing*, *reason* or *point*. A repeat is a run of up to four words said twice in a
row; the same word twice with no pause is left alone where English allows it (*had had*,
*that that*). A restart is a phrase that stops at a pause on a word that cannot end it, or
whose verb comes straight back after the pause.

On the development set every kind scored 0.97 or better both ways except examples (recall
0.750 — the three *like*s) and restarts (recall 0.875). Then the held-out set, once:

| Measure | Precision | Recall | Shown |
|---|---|---|---|
| A reason | 0.957 [0.790, 0.992] over 23 | 1.000 [0.851, 1.000] over 22 | yes |
| An example | 1.000 [0.722, 1.000] over 10 | 0.909 [0.623, 0.984] over 11 | yes |
| A step | 0.933 [0.702, 0.988] over 15 | 1.000 [0.785, 1.000] over 14 | yes |
| A contrast | 1.000 [0.832, 1.000] over 19 | 1.000 [0.832, 1.000] over 19 | yes |
| Summing up | 1.000 [0.758, 1.000] over 12 | 1.000 [0.758, 1.000] over 12 | yes |
| A word said twice | 0.923 [0.667, 0.986] over 13 | 1.000 [0.758, 1.000] over 12 | yes |
| A phrase started again | 0.636 [0.354, 0.848] over 11 | 0.636 [0.354, 0.848] over 11 | **no** |

**The errors, read one by one.** A reason: *since we went fully remote, onboarding takes
twice as long* is a time and a cause at once, and the counter read a cause. A step: *first
thing next sprint* is an idiom. A repeat: *again, again and again*. The example missed is a
*like*. The restarts missed are phrases broken off on a noun or on a verb that does not come
back — *the work, it took five*; *I ask, I tell the author* — and the ones found wrongly are a
preposition at the end of a clause (*what we do,*; *are asking for,*) and *all in all*.

**Restarts are therefore not shown.** They are counted and stored in `answers.structure`, so
they can be shown the day a counter clears the bar, and `structure.SHOWN` is what decides:
`tests/test_answer_measures.py` asserts on every run, in CI, that every measure it names
clears its bar on the held-out answers. The held-out set is unspent — nothing in the counter
was changed after it was scored — and trap 75's rule holds for it: fixing a restart to pass
one of its cases spends it.

**One limit to state.** The same author wrote the labels and the counter. The held-out set
was written before the code and not read while it was written, which is the protection this
project has used before (0015); it is not an independent annotator.

## 4. The drill

**A page per prompt.** `/answers` lists the thirteen prompts by what they ask for — explain
what happened, justify a choice, walk someone through it, recommend something — each with a
band from A2 to C1 and a limit of 60 to 120 seconds. `/answers/{slug}` shows the prompt, one
line on how to answer (the main point first, a reason or an example for each thing said, the
point again at the end), the recorder and the earlier answers.

**Tables, not a session.** A session is a conversation, and written as one an answer would
also be analysed like a turn and counted into the weekly figures built from turns; a prepared
monologue would move the conversation's speech rate without the speaker changing. Prompts are
their own seeded table because a scenario's required columns — a persona, a goal, a rubric,
target forms — mean nothing for one.

**Start and stop.** A turn is held because holding is the one gesture where the person and
the machine agree when speech ended. An answer runs up to two minutes, and the time limit —
which the recorder enforces — is the answer to the microphone left open by a forgotten
second press, the worry that made the held button the choice for turns.

**The answer is stored before the model is asked**, the recogniser running with no database
connection held, as a turn does. A model that is down or slow costs the feedback, and the
feedback says so. The recording is transcribed and dropped.

## 5. The model's feedback, and the check on it

`services/answer_feedback.py` asks once, at temperature zero, for the point to say first, up
to two points made without a reason or an example, and the answer said again in fewer
sentences. It is told it did not hear the answer; any note that talks about pronunciation,
accent or how it sounded is dropped and counted.

**The check.** Every content word of the shorter version — noun, verb, adjective, number,
name — is looked for, by word and by lemma, in the answer and the prompt; stop words and the
words of signposts never count. `tests/rewrite_labels.py` holds 24 rewrites written before
the check, half keeping to the answer and half adding a fact. On the development twelve the
faithful ones added at most one word and the fact-adders at least four, so the limit is two.
On the held-out twelve: **6 of 6 fact-adders withheld, 6 of 6 faithful ones shown**.

**Then the model, on all forty labelled answers.** The first instruction asked it to keep
the speaker's facts and words, and it did not keep the words:

| | Withheld, development | Withheld, held out | With a new content word | Fewer sentences |
|---|---:|---:|---:|---:|
| Before | 21 of 24 | 13 of 16 | 38 of 40 | 40 of 40 |
| After | 7 of 24 | 2 of 16 | 26 of 40 | 40 of 40 |

The words were paraphrase — *caused*, *issue*, *identified*, *ensure* — rather than
invention, and the check cannot tell a reworded point from a new one, so the instruction was
revised against the development answers to build the shorter version from the speaker's own
words, joined with *and*, *so*, *because* or *but*. The held-out answers, which the revision
never saw, carry the figure. No note about sound was dropped in either run.

**What the check cannot catch** is a rewrite that changes what was meant using only words the
speaker said. It is a guard against invented content, not a proof of faithfulness, and the
page labels the rewrite as a language model's.

## 6. Say it again, tighter

After an answer, *Say it again, tighter* opens the recorder again, and the second answer is
stored with `again_of` pointing at the first and shown beside it on the same counts — length,
words, speech rate, time paused, fillers, sentences, words per sentence, words said twice,
each kind of signpost. No arrow, no colour, no pass mark: a shorter answer is not always a
clearer one. An earlier answer can be said again from the prompt's page.

## 7. Over time

One point per answer, oldest first, in the progress page's `Series` shape and by its rule: a
direction only where one end is defensibly better and three points exist. Fewer fillers and
fewer words said twice have a better end. Speech rate, time paused, words per sentence and
signposts do not, and are drawn and never judged — counting *because* would reward saying
it. A rate is withheld for an answer under fifty words.

It stays on the answers page. The progress page is built from weekly snapshots of turns and
readings, and answers are a different task; mixing them in would change what those
families mean. Revisit when there are enough answers to want them in the weekly view.

## 8. Seen end to end

In Chromium with a synthesised answer as the microphone, on a throwaway account: the answers
page at 1440 px in light, *Explain a failed release* answered with a 19-second answer,
then the same answer said again, shorter, at 375 px in dark.

The first answer came back 3.9 s after the recording stopped — transcription, counting and
the model's feedback together — with 55 words, two reasons, two steps, a contrast and a
summing up, each marked on its words, and a shorter version in two sentences that passed
the check. One thing the counts could not see: *we we rolled back*, spoken with the repeat,
came back from the recogniser as *we rerolled back* — the first repeat this project has seen
lost in a live check, one of the kind §2 measured at 12 of 13. The second answer was stored
as saying the first again, and the two were shown side by side: 55 words and 34, 19 seconds
and 13, four sentences and two. No horizontal scroll at either width.

**It found one defect, fixed before this was written.** The history drew each answer with
the progress page's chart, which keys its points by date; two answers on one day share a
date, and React warned eight times. The chart now keys by position, and says "one answer"
rather than "one week" when it is drawing answers. The account and its two answers were
deleted afterwards.

## 9. What is not settled

- **Restarts** (§3): below the bar, counted and not shown. A better counter needs a new
  held-out set written first.
- **A learner's voice** (§2): what survives the recogniser was measured on a synthetic one.
- **One model** (§5): `gemma3:4b` only; another model's paraphrase rate is not measured.
- **Faithfulness** (§5): the check catches new words, not a meaning changed with old ones.
- **Whether practising here makes somebody clearer** needs a person and weeks, as the rest
  of this product's outcomes do.
