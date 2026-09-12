# How it works

One rule shapes every part of SpeakLab: **anything that moves on a chart is counted by code
from what you said, and a language model explains the numbers without ever producing
one.** Each section below says what a part does, how, what it refuses to do, and how well it
is measured to work. How the services are wired is in [architecture.md](architecture.md);
every figure, with its source, is in [measurements.md](measurements.md); what does not
exist yet is in [limitations.md](limitations.md).

- [The conversation](#the-conversation)
- [Corrections and grammar](#corrections-and-grammar)
- [Read aloud](#read-aloud)
- [Make your point](#make-your-point)
- [Progress](#progress)
- [The evaluation harness](#the-evaluation-harness)

## The conversation

**Talk to a persona who answers out loud.** Eleven scenarios, each a persona with a brief,
a goal and a level, and a declared set of grammar forms and kinds of mistake it is written
to draw out. Hold the button to speak and release it: the recording is transcribed by
Whisper with a timing and a confidence for every word, answered in character by
`gemma3:4b`, and spoken by Piper — one request, stored whole or not at all. Ending the
session writes the report.

**The persona stays a persona.** It is given its full brief at the front of the prompt and a
short reminder immediately before the speaker's latest words, and the speaker's words go
in as quoted speech: anything in a speaker turn is something a person said out loud inside
the scene, never an instruction. Five rules are checked by code, with no model involved —
the reply's sentence cap, placeholder names, commentary on the speaker's English, stepping
out of the role, and quoting its own brief — and a model judge, itself scored against
labelled replies, says whether a reply stayed in character. Corrections wait for the
report: a practice partner that corrects every sentence is not a conversation.

**Measured.** A whole turn — recognition, reply and voice — takes 2684 ms at p95 on a quiet
machine, against 3 s. Between 6 and 8 of 9 probe replies break none of the five rules, and
what fails is the sentence cap the persona itself states; the judge agrees with the labels
on 8 of 10 and misses the same two every time. Asked to step outside the scene, the persona
gives its instructions away 16 times in 200 across ten phrasings, against 59 before the
speaker's words were quoted. That breaks the exercise rather than disclosing anything:
every brief ships in `api/seeds/`. See
[decision 0013](decisions/0013-an-instruction-spoken-in-the-scene.md).

## Corrections and grammar

**Two detectors, and the split is the whole design.** A dependency parse counts which
grammatical forms you actually produced — twenty-eight closed feature names, deterministic,
the same counts on every rebuild. A language model proposes corrections, which is a
judgement no rule set makes well. Only the first is ever plotted.

A learner reaches a zero error rate by only ever using the present simple. Counting only
errors calls that improvement; counting forms shows it for what it is. And because
scenarios declare the forms they were built to draw out **in the same vocabulary the
parser counts in**, "the scenario asked for comparatives and you did not use any" is a set
difference rather than an opinion.

**Every model proposal has to survive a gate**, and the refusals are counted rather than
dropped. The category must be in a closed list of nine; the words must be findable in your
own transcript — the model quotes, the system locates, so a correction cannot point at
something you did not say; a "correction" that only moves a comma is refused, because the
recogniser wrote the punctuation and you did not. A quarter of proposals are refused, and
that rate is the measurement that says whether the model behind this is good enough.

**Two errors are decided by rules instead of the model.** Subject–verb agreement — *she
work*, *the people is*, *there are a problem* — and a missing article after *be* or a role
after *as* — *I am engineer*, *it is very good apartment* — are read straight off the parse
and proposed with a confidence of 1.0. The rules are narrow on purpose: silent on a
collective, a quantity, a subjunctive, an uncountable noun, and on a bare verb in a past
context, where the mistake is the tense rather than the agreement. When the model proposes
the same correction it is not stored twice, and every correction says which detector found
it. See [decision 0014](decisions/0014-the-rule-layer.md).

**An error on a word the recogniser was unsure of is shown and marked, and counts towards
nothing.** The gate is per word, not per turn, and real speech shows why: a stored turn
scored 0.899 overall while containing "department" where the speaker said "the apartment"
— that word alone scored 0.41, and the turn score is the *mean*, so no turn-level threshold
could reach it. See [decision 0006 §4](decisions/0006-error-taxonomy.md).

**A correction to a verb knows which form it was made in.** The correction is applied, the
corrected sentence is parsed, and the verb phrases before and after are compared: *I never
went to London* corrected to *I have never been* was said in the past simple and needed the
present perfect. Both sides are kept, because either alone misleads — counting only what
was said never shows a learner who avoids the present perfect that they avoid it. So each
tense and modal carries *right 9 of 13* — its uses, and the times it was needed and
something else was said — and *needed 2, never said* for a form you should have reached for
and did not. A count, never a percentage: a floor on the sample does nothing about the
corrections underneath, which are the larger error. See
[decision 0015](decisions/0015-accuracy-per-form.md).

**Once a session has been ended, the transcript marks each accepted correction on the
words it quotes** — a superscript number on the words, and a numbered row under the turn
with the replacement, the category and the explanation. A correction on words the
recogniser was unsure of is drawn dotted and says it may be a mishearing; one whose offsets
do not hold its words is listed and never underlined. Ending waits for the analysis of what
you said last, and a report written short is finished when the session is next opened.

**The grammar page puts your own sentences in front of you.** Every correction, grouped by
kind, in the sentence you said it in, with what was proposed instead and a link to the
conversation; every verb form with its counts and the corrections behind them. One form is
named for practice — the one right least often, with a scenario at your level that asks for
it — but only once it has come up ten times and been corrected five, because many of the
model's corrections are wrong. Until then the page says how near the nearest form is. It
leads with evidence because nothing on it was checked by a person, and a learner can
disagree with a sentence but not with a percentage. Each kind of correction links to a
scenario written to draw it out — including three for articles, prepositions and the
words with a Spanish look-alike that means something else. See
[decision 0016](decisions/0016-the-grammar-page.md).

**Any of those sentences can be said again.** *Say it again* opens the sentence as you said
it, with the correction in it — and any other correction the sentence held, since saying it
with one fixed would practise the rest — shown first, so one you disagree with can be
skipped. Hold the button, say it, and the page shows what the recogniser heard where each
correction belongs: the correction, the words as you first said them, something else, or
nothing. There is no pass mark and nothing is stored, and no model is asked anything. See
[decision 0017](decisions/0017-the-spoken-drill.md).

**Measured.** Detection precision is 0.500 over six scored proposals against a 0.70 bar —
too few to decide either way; the model finds roughly the right words and files them under
the wrong category. On errors planted in native English the rules catch 130 of 172
agreement errors and 2 of 129 missing articles, with no wrong fix. The form join is right on
32 of 34 held-out corrections and puts none under a wrong form. Said aloud by a clear
synthetic voice, a mistake comes back as its correction 1 to 3 times in 89, and a corrected
sentence never comes back as the mistake. Of twenty planted mistakes per kind, the detectors
file 12 prepositions, 6 articles and 6 false friends under their own kind.

## Read aloud

**Read a passage and see it scored sound by sound.** Twelve passages. The recording goes to
`asr` for a transcript, and the transcript with a canonical phoneme sequence from G2P goes
to `pron`, which force-aligns the audio and returns the Goodness of Pronunciation of every
phone: how much less likely the acoustic model found the sound you were meant to make than
the likeliest one, and which sound that was. The page shows every sound in the passage,
shaded relative to the reading.

**No pronunciation claim comes from something that did not hear you.** GOP is computed by
an acoustic model on the waveform; a language model reading a transcript would be
inventing. Synthetic speech is outside what that model was trained on, so every
pronunciation fixture is a human recording.

**Without `pron`, a reading still works.** It comes back with its transcript and its word
error rate, and says in words that the phone scores are missing and how to get them;
`make pron-up` starts the service, and readings taken without it can be scored afterwards
without being read again.

**Measured.** With a phone the speaker did not produce written into the reference, GOP
falls by a mean of 8.14 nats against a threshold at the 5th percentile of correctly
produced sounds: 9 of 10 planted errors detected, and the competing sound named in 10 of 10,
the same on every run. A 34-second reading — 250 sounds — is scored in 7.5 s, against 10 s.
The method is cheap and the CPU allocation is not: the same scoring takes about 100 ms an
attempt with eight torch threads on the host and about 820 ms in its container. See
[decision 0005](decisions/0005-gop-pipeline.md).

## Make your point

**Answer a work question out loud, in one go, and see how the answer was built.** Thirteen
prompts, in four kinds — explain what happened, justify a choice, walk someone through it,
recommend something — from A2 to C1, each with a limit of one to two minutes. Press to
start, press to stop; the limit stops it for you. The recording is transcribed and dropped.
What comes back is counted, not judged: how you said it, with the arithmetic a
conversation turn gets, and how you built it — the reasons, examples, steps, contrasts and
summing up, each marked on your words, the sentences as the recogniser punctuated them, and
the words you said twice.

**A measure is shown only if it was right often enough on answers it was not built
against.** Sixteen labelled answers are held out from the counter, and a measure is shown
only at 0.90 precision and 0.75 recall on them. Every kind of signpost and the repeats
clear it; a phrase started again does not — 0.636 both ways — so it is counted and stored
and never shown. *Like* is never counted as an example: no parse separates "tools like
Jira" from "it looks like rain" reliably enough. And more signposts is not a better answer —
counting *because* would reward saying it — so nothing on the page or over time calls a
higher count better.

**A language model's feedback sits beside the counts**: the point to say first, the points
made without a reason or an example, and your answer said again in fewer sentences. That
shorter version is checked for content words you never said, and withheld — with the words
that withheld it — if it brings in more than two: a rewrite that improves your answer by
adding a figure you never gave puts words in your mouth. The model did not hear you, so a
note about how you sounded is dropped. Then *Say it again, tighter*, and the two answers
side by side on the same counts, with no pass mark. See
[decision 0019](decisions/0019-make-your-point.md).

**Measured.** Said by a synthetic voice, 21–23 of 24 fillers, 12–13 of 13 words said twice
and every signpost reach the transcript. `gemma3:4b`'s shorter version is withheld for 9 of
40 labelled answers — 2 of 16 held out — and the check withholds 6 of 6 rewrites written to
add a fact while letting 6 of 6 faithful ones through.

## Progress

Everything analysed is collapsed into one row per week, and the progress page reads those
rows and nothing else — in 7 ms. Aggregating raw turns on page load would get slower every
week you practised, which is backwards for a feature about practising over months.

**Most of this page is refusals, and they are the part worth reading.** A week with too
little speech in it is drawn as a **hole with a reason**, not left out — leaving it out
would compress a thin fortnight into the space between two points, which reads as
continuous practice. A per-sound trend stays closed until five readings are behind it,
because the first few describe your microphone as much as your mouth. And a direction is
claimed only where one end of the scale is defensibly better: **speech rate is drawn and
never judged**, because faster is nerves as often as it is fluency.

**Pronunciation is expressed as a distance from your own recent readings**, per sound, in
standard deviations — never as a raw score compared across weeks, and never against another
person. The sampling unit is the *reading*: forty instances of one sound inside a single
recording are one observation of one microphone in one room, and treating them as forty
independent samples would make every baseline look far tighter than it is.

**Recommendations are a weighted score with no model in it.** Corrected categories, forms
you have not reached for, sounds scoring worst, each decayed by how old the evidence is.
Every entry prints the measurement that chose it — *"2 corrections in 272 words"* — because
a suggestion you cannot check is indistinguishable from a guess. The response also states
how much it rests on, and on a small corpus it says **thin evidence**.

**The accuracy chart carries the detectors' measured quality on the screen.** The rate is
an exact count of stored rows; the rows come from grammar rules for two categories and from
a model for the rest, and half of the model's proposals land on a real mistake, usually
under the wrong category. That belongs next to the chart somebody would act on, not in a
document they will not open. [Decision 0007](decisions/0007-progress-metrics.md) has the
gates and the weights.

## The evaluation harness

`make eval` runs five measurement suites — speech recognition, pronunciation, error
detection, persona adherence and spoken answers — and a census of the stored practice, and
writes [evaluation.md](evaluation.md) with the date and the revision it was taken at.
Nothing in that file is written by hand. It settles four of the ten success criteria, S4 to
S7, and names where each of the other six is measured.

Three rules make it worth reading:

- **A suite that did not run is reported as not run.** No figure, and nothing carried
  forward from a previous run. Every suite skips when its service, model or golden set is
  absent, so the code that would produce a figure never runs.
- **Below twenty trials nothing decides a criterion**, in either direction. A precision of
  1.000 over three proposals is three proposals, and the report says *undecidable* rather
  than met.
- **The one language-model judge is itself scored on every run**, against ten replies
  labelled before it existed, and its agreement is printed beside its verdicts.

**Some figures move from run to run on the same code.** Synthesis samples, so the same
sentence is never the same audio twice, and the persona's replies are sampled too. These
documents give such a figure as the range across the runs recorded; each run's full report
is in the history of `evaluation.md`.
