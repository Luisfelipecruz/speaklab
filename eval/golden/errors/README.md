# Error golden set

Real learner turns, labelled by hand, used to measure how well error detection works.

`labels.json` is the hand-written part and the only part worth reading closely.
`manifest.json` is generated from it and from the stored turns, and carries the
transcripts and word timings so the measurement runs from a clone with no database.

```bash
make error-precision                          # score the live model against it
python3 eval/golden/errors/build.py           # rebuild it after recording more
```

## What is in it

**Four turns, 123 words, five labelled learner errors.** They are one side of a real
conversation with the `apartment-viewing` persona — a person asking about amenities, the
lease and whether they can keep a pet — plus one closing line. Spanish first language, a
laptop microphone, a room.

Every label carries a `kind`, and the three are the reason this set is usable at all:

| kind | what it means | how it scores |
|---|---|---|
| `error` | A learner error. | Counted. |
| `asr_artifact` | The text is wrong but the speaker probably is not. | Neither credited nor penalised. |
| `borderline` | Defensible either way, or too garbled to grade. | Neither credited nor penalised. |

Nine of the twenty labels are one of the last two, which is the honest shape of real
speech recognition output. A detector that proposes a correction inside "The term some
conditions" has found something wrong with the *transcript*; whether the speaker made a
mistake there is not knowable from the recording, so scoring it either way would be
inventing an answer. The same rule the product applies to its own trends, applied to its
own evaluation.

## What is not in it, and why

**Three more turns exist and are not in this repository.** They are the same speaker's
standup at work, and they name a real team, a real certificate and real ticket numbers.
The labels for them live in `labels.local.json`, which is gitignored; `build.py` writes
`manifest.local.json` when that file is there, and the measurement suite prefers it and
prints which set it read.

So there are two numbers, over four turns and over seven. Neither is large. The report
names its source for exactly that reason.

## How the labels are built

**Quotes, not offsets.** A label says *"appreciate to be here"*, and `build.py` finds
that phrase in the stored transcript. A quote is something a reader can check; a
character offset is not. If a quote is missing from its turn, or appears in it twice, the
build fails and says so — a gold label that silently attached itself to the wrong
occurrence would make every figure measured against it meaningless.

**Written before any detector existed.** The labels were produced by reading the seven
transcripts, in one pass, before a prompt had been written or a model had been asked
anything. That ordering is the only thing that keeps them from being a description of
what the detector already does.

## What it cannot tell you

**It is too small to place a precision figure.** Five labelled errors in the published
half, and a run scores a handful of proposals. A precision computed over four or six
trials carries a 95 % interval roughly half the width of the scale, so the measurement
suite prints its numbers and asserts none of them. What it does assert is the machinery:
every accepted error points at text that is really in the transcript, every rejection
carries a reason from the closed list, and a turn with nothing wrong in it produces
nothing.

**The labels are not independent.** They were written by the same agent that wrote the
detector's prompt. A second annotator disagreeing with them is the missing piece, and
until there is one, "precision against this set" means "agreement with one reading of
seven transcripts".

**It grows the only way it can.** By somebody holding a conversation with the product and
the corpus getting bigger. `build.py` picks up every user turn in the database; adding
labels for the new ones is the whole of the work.
