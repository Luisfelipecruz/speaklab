# The persona golden set

Six probes and ten hand-labelled replies, graded on 2026-09-05 by reading the eight seeded
personas and the `GUARDRAILS` constant in `api/services/conversation.py` — before any reply
had been generated. Nothing here was written after seeing what the model does.

## Why this one has a judge in it when nothing else does

Every other measurement in this repository is arithmetic. Word error rate is edit
distance; goodness of pronunciation is a log ratio; error precision is counting overlaps
against spans a person marked. Persona adherence is not that shape. "Did it stay in
character" is a judgement about prose, and no amount of regular expressions turns it into
one.

So this suite is split, and the split is the point:

- **Deterministic checks** run on every reply and are the floor. Sentence cap, the
  placeholder-name guardrail, no commentary on the speaker's English, and — the one that
  matters most — an instruction inside a speaker turn being treated as something a person
  said out loud rather than as an order. These are counted, not judged.
- **Judged checks** are the two things only a reader can settle: whether the reply is the
  character the persona describes, and whether it invites an answer using the grammar the
  scenario declares.

The judge produces a number that goes in a report. It never produces a number that a
learner sees. That distinction is invariant I1, and it is the whole reason an LLM is
allowed anywhere near this file.

## The calibration set exists because a judge is an instrument

Ten replies, five in character and five not, each with the failure written down. They are
run through the judge on every measurement, and the judge's agreement with those labels is
reported **beside** its verdicts on the real replies.

This is not decoration. A judge that scores 5/10 on replies chosen to be obvious has told
you that its verdicts on the six real probes are noise, and the report says so rather than
quoting a persona-adherence percentage that means nothing. The failure modes were chosen to
be distinct rather than subtle — breaking role to explain the exercise, correcting the
speaker's grammar, answering as a generic assistant, using a placeholder name, reading its
own brief out loud — because an instrument that cannot separate those separates nothing.

## What is in the manifest

Each probe carries the conversation history and the utterance to reply to, plus what was
expected of the reply *before* it existed:

| Field | Holds |
|---|---|
| `scenario` | The seeded slug. Its persona prompt is the brief the reply is judged against |
| `history` | Turns the model sees as the conversation so far. Never stored; assembled in memory |
| `utterance` | What the speaker just said, and the thing the probe is really about |
| `max_sentences` | The cap that persona states in its own words |
| `ends_with_question` | Only where the persona asks for it. Three of the eight do not |
| `elicits_any_of` | A subset of that scenario's own `target_grammar`. Validated against the seeds |
| `why` | What this probe is trying to catch, and what a failure would look like |

`why` is there because a fixture whose purpose is not written down becomes a fixture
nobody dares change.

## Running it

    make persona-adherence

Needs Ollama on the host with the configured model pulled. It skips otherwise, like every
other measurement suite here — `make test` and CI point `OLLAMA_BASE_URL` at a host that
cannot resolve, on purpose.

The suite makes roughly 6 replies + 6 judgements + 10 calibration judgements = 22 model
calls, and takes a couple of minutes.

## What it costs to change this file

Adding a probe is cheap and welcome. Changing an existing one after seeing a result is how
a golden set stops being golden: if a probe turns out to be badly written, say so in the
commit and record what the old one measured, because every earlier number in
`docs/evaluation.md` was produced against it.
