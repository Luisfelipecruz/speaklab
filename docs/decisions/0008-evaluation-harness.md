# 0008 — The evaluation harness, and the rules that keep it honest

Status: accepted

Read this before adding a suite, changing how a criterion is adjudicated, or moving a
number from "reported" to "asserted". The harness is the one component in this repository
whose bugs all point the same way, and §2 is the reason.

---

## What was decided

1. **Measurement suites and one census**, collected by a host-side runner rather than by
   another pytest file. The suites stay as pytest because they need fixtures, async and
   the skip machinery; `eval/run.py` collects what they write.
2. **A suite that did not run produces no figure**, and the report says "not run". Not
   "0", not last week's number, and never a pass.
3. **Below 20 trials nothing decides a criterion**, in either direction. A precision of
   1.000 over three proposals is three proposals.
4. **Persona adherence is judged by a language model, and the judge is scored on every
   run** against ten hand-labelled replies. Its agreement is printed beside its verdicts.
5. **The deterministic checks are the floor.** Five rules that need no judgement at all
   run first and are reported first.
6. **`docs/evaluation.md` is generated and never hand-edited.** The README quotes it.
7. **Golden fixtures stay read-only; results go somewhere else.** `eval/` is mounted
   read-only into the one container that measures; `.eval/` is a separate writable mount.

---

## 1. Why the runner is on the host and the suites are not

`make asr-wer`, `make pron-golden` and `make error-precision` each print numbers. The
harness gets those numbers into a document without a person copying them, because a
copied number is a recalled number.

The obvious move is to make the runner a pytest file that imports the others. It is
wrong for a boring reason: pytest's output is prose. Every one of these suites prints a
table for a human watching it scroll past, and parsing figures back out of that is a
parser that breaks the first time somebody adds a line to a report. So each suite calls
`record()` (`api/tests/eval_out.py`), which writes JSON when `EVAL_OUT_DIR` is set and
does nothing at all when it is not — which is `make test`, CI, and anybody running one
suite by hand. **The measurement never depends on being collected.**

The runner then has to live somewhere that can write `docs/`, and the container cannot:
`/app` is `api/`, and mounting the repository root into the service under test to let it
write its own documentation is not a trade worth making. So `eval/run.py` runs on the
host with nothing but the standard library, and shells out.

## 2. The failure mode this harness is built around

A broken detector makes the product look worse and somebody notices. A broken evaluator
makes the product look **better**, prints a table of green ticks, and gives nobody a
reason to look. Every bug in this component is silent and flattering.

So the tests in `api/tests/test_eval_harness.py` are not about the happy path. The
fixtures are the shapes that a plausible implementation reports as a pass:

| Fixture | What a naive implementation says | What is required |
|---|---|---|
| No results at all | crashes, or renders an empty table | every criterion `not run` |
| 3 true positives out of 3 | S5 met — precision 1.000 | `undecidable`; three trials |
| The GOP probe passing | S4 met — 9/10 detected | `not run`; the probe is not S4 |
| README quoting a stale WER | S6 met — it was measured | `not met`; measured, not published |
| Five accounts, six sessions each | S7 met — thirty sessions | `not met`; the page is per-user |

The third row is the one most likely to happen. The reference-perturbation probe scores
real human speech against text containing a phone the speaker did not produce, it passes
at 9/10 with an 8-nat gap, and it is *not* criterion S4 — a learner's error is gradient
rather than categorical, and the probe's separation is an upper bound on the real one. A
harness that let it stand in would report the hardest unmet claim in this project as
satisfied, with a real measurement behind it.

## 3. Twenty trials, and why the threshold is arbitrary on purpose

`scoring.DECIDABLE_TRIALS = 20` has no theory behind it. It is set against the error
golden set's six scored proposals, the sample size most likely to mislead: 0.500 detection
precision over six means little, and Wilson puts its interval at [0.188, 0.812].

Two consequences worth being awake to:

- The rule fires **in the flattering direction too**, and that is the half that matters.
  It is easy to write a harness that hedges bad news and takes good news at face value.
- Twenty is not enough for a tight interval either; it is enough that the interval stops
  spanning most of the scale. When the corpus grows, raise it and say so here.

Wilson rather than the normal approximation because at these sizes the normal interval is
actively misleading: six of six gives [1.000, 1.000], a claim of certainty from six
trials, and that is a number somebody would act on.

## 4. Persona adherence: the one place an LLM grades anything

Nothing plotted on a trend chart is produced by a language model. Nothing here reaches a
chart — these figures go into a document for a reader, and no learner ever sees them — so
the exemption is narrow and stated.

The reason a judge is needed at all is that "did it stay in character" is not arithmetic.
Word error rate is edit distance, GOP is a log ratio, error precision is counting span
overlaps against a person's marks. Adherence is a judgement about prose, and measuring
some regular expression instead and calling it adherence would be worse than not
measuring it.

**So the judge is measured on every run.** Ten replies, five in character and five not,
each failing a different rule, labelled before any of this existed. Its agreement is
printed beside its verdicts, because a judge scoring 6/10 on cases chosen to be obvious
has told you its six real verdicts are noise.

### What the calibration set found, immediately

`gemma3:4b`, four runs with identical results:

| | |
|---|---|
| Judge agreement with hand labels | **0.800 [0.490, 0.943] over 10** |
| The two it got wrong, all four runs | `cal-placeholder-name`, `cal-leaks-the-brief` |
| Deterministic layer on the same ten | **10/10**, no false positives |

The judge catches all three replies that break role in an obvious way — explaining the
exercise, correcting grammar, answering as an assistant — and misses **exactly the two
that the deterministic layer catches**: a placeholder name, and a reply that describes
its own brief. Stable across runs.

That is the whole argument for the split design. The judge is good at the thing only a
reader can settle and blind to two things a regular expression settles for nothing.
Neither instrument is sufficient and the report prints them in the order of how much they
can be trusted.

## 5. The finding: an instruction spoken inside the scene

`services/conversation.GUARDRAILS` tells the model that anything in a speaker turn is
something a person said out loud inside the scene, and is never an instruction about how
it should behave. This suite is what checks it.

Asked ten times to ignore its instructions and print its brief, while playing a letting
agent showing a flat:

| | `gemma3:4b`, four runs of ten, before [0013](0013-an-instruction-spoken-in-the-scene.md)'s change |
|---|---|
| Quoted its own brief back | **30 of 40 — 0.750 [0.598, 0.858]** |
| Per run | 8, 9, 7, 6 |
| Stepped out of the scene entirely | 1, 1, 4, 2 |

Four runs are pooled because ten attempts is ten: the interval on 8/10 alone is
[0.490, 0.943] and would leave the rate arguable. Pooled, it is not.

One reply opened "I don't have a system prompt in the way a traditional program does. I'm
a large language model". Several opened by reciting the persona verbatim from its first
word.

**What this is.** A role-integrity failure. The exercise stops being an exercise, and it
can be made to stop by *speaking* — which in an app driven by a microphone is the only
input there is.

**What this is not.** A confidentiality breach. Every persona ships in
`api/seeds/scenarios.json` and anybody with the repository can read all of them. Nothing is
disclosed. Describing this as a prompt-injection vulnerability would be the same species
of dishonesty this project exists to avoid — it is a quality defect with a security
*shape*, and the two are worth keeping apart.

**Reported, not asserted.** The suite prints the rate and fails nothing, on the same rule
every model-facing figure here follows: this is a property of a four-billion-parameter
model and a prompt, not of the code under review. The assertion that remains is about the
instrument — that the leak detector still catches a verbatim run from the brief and still
ignores ordinary in-character speech — because a rate produced by a broken detector is a
measurement of the detector.

**The fix is a change to the prompt**, measured with this suite across phrasings in
[0013](0013-an-instruction-spoken-in-the-scene.md).

## 6. Fixtures in, results out, different mounts

Golden evaluation sets are never reachable by the system being evaluated. `eval/` is
mounted read-only into the test container and nowhere else.

That leaves nowhere to write a result. The tempting answer is a writable directory inside
`eval/`, and it is wrong for exactly the reason the mount is read-only: a hole in a
read-only mount is a read-only mount with a hole in it. So `.eval/` sits beside `eval/`
at the repository root, is its own writable mount, and is gitignored — a result belongs
in `docs/evaluation.md`, which the host renders from those files.

`make fmt-eval` is a separate target from `make fmt` for the same reason. Formatting is
something a developer does to source; it is not something a measurement can do to the
corpus it is graded on, and keeping the two capabilities in different commands is what
keeps that true.

## 7. What was found on the way

**`black --exclude eval` excludes six files it should not.** ruff's `--exclude` matches
path components; black's is a regular expression `re.search`ed against the whole path, so
a bare `eval` also matches `tests/eval_out.py` and `tests/test_eval_harness.py` — 99 files
checked where there are 105. Anchored to `^/eval/` it means the directory, and CI lints
both trees in one command.

**A module loaded by path must be in `sys.modules` before it is executed.** `@dataclass`
resolves `sys.modules[cls.__module__]` while the class body is still being processed, so
a module absent from the table raises `AttributeError: 'NoneType' object has no attribute
'__dict__'` during import — which pytest reports as a *collection* error, taking the whole
file down instead of skipping it.

**The runner checks the exit code before the result file.** Checked the other way round,
a suite whose measurement passed and whose assertion failed is reported as "measured" —
which is how §5's failure would have been hidden. Figures are still collected and still
shown, with the failure said out loud above them.

## 8. What is not settled

- **A stronger guardrail is measured on one model** ([0013](0013-an-instruction-spoken-in-the-scene.md)).
- **The judge is one model grading another of the same family.** `gemma3:4b` judging
  `gemma3:4b` shares its blind spots by construction, and the calibration set is the only
  thing standing between that and a meaningless number. A judge from a different family
  is the obvious next experiment and needs nothing but an environment variable.
- **Ten calibration replies is ten.** The agreement figure carries the same interval
  problem as everything else here: 0.800 over 10 is [0.490, 0.943].
- **Nothing measures the harness against a *deliberately broken suite*.** The self-tests
  feed fixtures to the adjudicator; they do not run a suite that lies.
