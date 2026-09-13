# 0003 — The conversation loop: context, anchoring, and where a turn's time goes

Status: accepted

---

## What was decided

A thin provider interface over local Ollama; the persona re-anchored twice per turn; the
history bounded in tokens with the overflow summarised into a running digest; and each
finished sentence handed to the voice while the model is still writing the next one.

This record is about what measurement changed in those choices, the question it closes,
and the ways it can be measured wrongly.

**The headline: the turn budget is met.** p95 **2684 ms** against PRD §9.1's 3000 ms, on
a quiet target machine, with `small.en` still in the pipeline. The recogniser does not
have to be downgraded, and [0001](0001-asr-model-choice.md)'s bet holds.

---

## 1. Ollama does not refuse a prompt that does not fit. It deletes half of it.

This is the most expensive fact in the conversation loop, and it is the reason the token
budget in this system is a correctness mechanism rather than a cost control.

Measured against Ollama 0.33.1 and `gemma3:4b`:

| prompt | `num_ctx` | `prompt_eval_count` | outcome |
|---|---|---|---|
| ~2815 tokens | 4096 | 2815 | intact |
| ~3935 tokens | 4096 | 3935 | intact |
| ~4200 tokens | 4096 | **2051** | context shifted; half discarded |
| ~7017 tokens | 4096 | **2051** | same |
| ~7017 tokens | 8192 | 7017 | intact |

The cliff is exactly at `num_ctx`, and going one token past it does not cost you the
oldest turn — it costs you **half the window**, rounded to `num_ctx / 2`. There is no
error, no warning, and no field in the response that records it. The reply comes back
200 and reads perfectly well.

A second probe establishes what gets discarded. With two unique markers, one at the head
of a long prompt and one at the tail, and `num_ctx` set below the prompt size, the model
could report neither: 1027 of 5655 tokens were evaluated and the answer was confident
nonsense. Whatever llama.cpp keeps, it is not the beginning — and the beginning is where
a system message lives.

**So the failure mode is: the persona silently disappears from exactly the long
conversations PRD R7 is about, and the symptom is "it drifts out of character somewhere
after turn twelve".** That is a bug nobody would find by reading logs, because there are
none.

Three things follow.

**`num_ctx` is stated on every request.** Never inherited. An Ollama default large enough
is a property of one version on one host, and `OLLAMA_CONTEXT_LENGTH` is a documented
environment variable that anyone may have set.

**The prompt is sized before it is sent.** There is no Gemma tokenizer in the API image
and there will not be one: it means `transformers`, which means torch, which is precisely
what the API image is built without. So the estimate is characters divided by a constant.

**The estimate is allowed to be wrong by a stated amount.** This is the part worth
copying elsewhere. Characters-per-token is not a property of the language, it is a
property of the text — repeated instructions tokenise near 3.7, ordinary prose nearer
4.6 — so a single constant cannot be accurate. Measured against Ollama's own
`prompt_eval_count`:

| prompt shape | estimated | actual | error |
|---|---|---|---|
| one-line greeting | 18 | 17 | +5.9 % |
| persona-sized instruction block | 293 | 313 | **−6.4 %** |
| thirty turns of history | 1898 | 1788 | +6.2 % |

`LLM_ESTIMATOR_MARGIN` is 1.25, the context window is sized as
`budget × margin + reply_cap` = 5400, and the live suite asserts that the worst
under-count still fits inside the margin. The margin is not a fudge factor; it is what
turns a heuristic into a bound.

The estimate counts a per-request constant of 8 tokens as well as the per-message
template overhead — the BOS token and the `<start_of_turn>model` the template opens for
the reply. Without it the one-line greeting is under-counted by **41 %**: seven tokens,
irrelevant at that size, and a sign that the model of the thing was wrong. With it every
other row improves too.

The estimate only ever decides **what to send**. What is reported is
`turns.prompt_tokens`, which is Ollama's own count. A drifting constant therefore shows up
as a widening gap between two stored numbers rather than as a context that quietly
overflows.

---

## 2. Gemma 3 has no system role, so "anchor the persona in the system message" is not the instruction it looks like

PRD R7 says the persona is re-anchored in the system message every turn. Ollama's template
for `gemma3:4b` says what that means:

```
{{- range $i, $_ := .Messages }}
{{- if or (eq .Role "user") (eq .Role "system") }}<start_of_turn>user
{{ .Content }}<end_of_turn>
```

A `system` message is rendered as an ordinary **user turn**, in whatever position it
occupies. Gemma 3 has no privileged channel at all. So on this model:

- "put the persona in the system message" means "put it in the first user turn";
- rebuilding that message every turn — which is what "re-anchored every turn" naturally
  implies in code — changes nothing at all unless the persona itself has changed, because
  the text lands in the same, distant place;
- and there is no structural boundary between the persona's instructions and the
  speaker's words. The injection boundary is a sentence in the prompt, not a mechanism.

The assembly therefore anchors twice: the full brief at the front, and a ~30-token
reminder of identity and the reply constraints immediately before the latest utterance.

**Whether the second anchor helps is unresolved, and these instruments cannot tell.** It
was measured with two deterministic proxies — never an LLM judging an LLM — chosen
because the seeded personas make them checkable: replies within their sentence cap, and
replies that end with a question.

| arm | ≤ 4 sentences | ends with `?` |
|---|---|---|
| both anchors | 100 % | 100 % |
| front anchor only | 100 % | 100 % |

30 turns of history, n = 25 replies per arm, `gemma3:4b`.

Both proxies saturate. At 30 turns this model holds its format constraints perfectly with
or without the tail anchor, so the measurement distinguishes nothing. A run at n = 10
showed 80 % versus 100 % on the question proxy and would have supported the opposite
conclusion; it was two replies, and it was noise — which is how a fourteen-token
difference becomes a finding in a document.

**The anchor stays**, on the mechanistic argument in the template above rather than on
evidence that it helps, and because 30 tokens against a 1278-token prompt is 2 %. What
these proxies test is *format* compliance, not staying in character — not commenting on
the speaker's English, pushing back on a vague claim, keeping the scene. That is measured
by the evaluation harness's persona suite ([0008](0008-evaluation-harness.md)).

---

## 3. Where a turn's time actually goes

### The measurement

Twenty turns through the real recogniser, the real model and the real voice, against
`POST /sessions/{id}/turns`. Audio is the four shortest clips of the ASR golden set,
4.45 s to 6.82 s, cycled — LibriSpeech read speech rather than conversational speech,
which is a substitution worth naming, but the durations land where §9.1's budget assumes.

Run at **load 1.74 rising to 5.04** on the target machine (M4 Max, 16 cores, 128 GB).

| stage | §9.1 budget | median | p95 | verdict |
|---|---|---|---|---|
| ASR (~5.25 s audio) | 700 ms | 1146 | 1341 | missed, as [0001](0001-asr-model-choice.md) expects |
| generation (~53 tokens) | 1500 ms | 872 | 1249 | **met** |
| synthesis, tail | 400 ms | 235 | 399 | **met** |
| reply (generation + synthesis) | — | 1132 | 1447 | — |
| **whole turn** | **3000 ms** | **2353** | **2684** | **MET** |

Prompt 1258 tokens median (budget 4000), reply 53 tokens median (cap 400), 2 sentences
per reply, zero cold model loads.

**The turn budget is met.** The one stage that misses is ASR, which
[0001](0001-asr-model-choice.md) measures and deliberately does not engineer away — and the
turn absorbs it.

### The same measurement on a contended machine, because that matters too

The same code while the machine also hosts a second Docker VM, an Android emulator and
two other Compose stacks. At load 10–16:

| | quiet (load ~2–5) | contended (load ~10–16) |
|---|---|---|
| whole turn, median | 2353 ms | 6286 ms |
| whole turn, p95 | **2684 ms** | 7283 ms |
| ASR, median | 1146 ms | 2171 ms |
| generation, median | 872 ms | 2148 ms |
| synthesis tail, median | 235 ms | 1526 ms |

**Nearly 3× on the same code.** This is recorded rather than discarded because it is the
honest range a developer will actually see. A latency taken without its load average
beside it is not a measurement.

### PRD §9.1's first fallback, measured against its own control

Streaming the reply into the voice sentence by sentence. The identical 20-turn run with
`LLM_STREAM_TO_TTS` on and off, both on a quiet machine (load 1.74 and 2.22 at start):

| | overlapped | in series |
|---|---|---|
| **synthesis the turn still waited for**, median | **235 ms** | **375 ms** |
| synthesis the turn still waited for, p95 | 399 ms | 554 ms |
| generation, median | 872 ms | 705 ms |
| ASR, median | 1146 ms | 1370 ms |
| whole turn, median | 2353 ms | 2602 ms |
| whole turn, p95 | **2684 ms — met** | **3043 ms — missed by 43 ms** |

**The directly attributable effect is ~140 ms at the median and ~155 ms at p95**, and it
is the synthesis row: that is the quantity the change acts on, and it means the same thing
in both configurations. The turn totals differ by more than that, but they also differ in
ASR by 224 ms and in generation by 167 ms in opposite directions — run-to-run variation
larger than the effect being measured. **Do not read the MET/MISSED line as the fallback's
doing.** It is on the right side of the budget in these two runs, and the honest claim is
that overlapping buys about a twentieth of the turn.

The streaming endpoint of [0002](0002-tts-model-choice.md) is expected to hand back
~242 ms of the recogniser's overspend, which is about right — and about 6 % of a turn. The
ceiling is arithmetic: a two-to-three sentence reply is ~500 ms of synthesis work
(measured directly against the voice: 508 ms as one call, 472 ms as three concurrent
calls, 517 ms as three serial calls, so splitting is cost-neutral at the service), and
overlapping can hide at most all-but-the-last sentence.

**It stays on.** It is free, it is bounded-correct, and it shortens the turn, which is what
the budget measures. It does not bring the first sound forward in the browser: the turn
endpoint returns one concatenated WAV after the whole turn, so the browser's first audio
arrives at turn latency ([0004 §3](0004-browser-recording-and-playback.md)).

### Two measurements of the overlap were wrong before this one, and both are recorded

Both are plausible, and both are wrong.

**The sum of per-sentence latencies.** The sentences are dispatched concurrently and the
tts service serialises them behind its own semaphore, so each sentence's reported latency
includes waiting for the ones before it. Summing them counts the queue once per sentence
and reports 5690 ms of "voice work" for a reply that takes about 500 ms to synthesise.

**The makespan from first dispatch to last completion.** Worse, because it looks right: it
necessarily spans the generation it is overlapping, so on the streaming arm it measures the
overlap window and not the work. It reports "60 % of synthesis hidden inside generation" —
a number that is really a description of when generation finished.

The tail is the only quantity that means the same thing in both configurations, which is
why `synthesis_ms` is what the API reports and why the A/B is the instrument.

---

## 4. The recogniser stays

> Does the measured end-to-end turn latency force the recogniser down to `base.en`?

**No. The turn meets its budget with `small.en` in it.**

p95 is **2684 ms against 3000 ms** on a quiet target machine. ASR is 1146 ms of that — it
misses its own 700 ms stage budget, as [0001](0001-asr-model-choice.md) measures — and the
turn absorbs the overspend because generation comes in at 872 ms against a 1500 ms budget
and synthesis at 235 ms against 400 ms.

Dropping to `base.en` would buy roughly 620 ms and cost **2.6× the word error rate**
([0001](0001-asr-model-choice.md)'s numbers), which is the input to every metric
downstream. There is no reason to pay that: the requirement is a turn at p95 ≤ 3000 ms,
and it is met. [0001](0001-asr-model-choice.md)'s bet — that a stage-level miss is
survivable at the turn level — holds.

Two things worth carrying forward:

- **The margin is 316 ms, which is not much.** The control arm — the same system with
  §9.1's first fallback switched off — comes in at 3043 ms. This budget is met, not met
  comfortably, and anything that lengthens replies will be the first thing to break it.
- **§9.1's fallback order looks wrong for this stack, and nothing is changed on the
  strength of it.** The order is stream TTS (worth ~140 ms), drop ASR (~620 ms, costs
  accuracy), shorten the reply cap (untested, listed last). Reply length drives generation
  *and* synthesis, so it is plausibly the largest lever of the three and it is the one the
  PRD reaches for last. That is a hypothesis with no measurement behind it.

---

## 5. Summarisation, and why the fold happens after the reply

FR-8 requires that turns falling out of the window are summarised rather than dropped. The
implementation choice worth recording is *when*.

Summarising costs a generation call. Doing it inline, on the turn that overflows, adds
several hundred milliseconds to one turn in ten — and p95 over twenty turns is exactly the
statistic that a rare slow turn ruins.

So the fold is triggered at a **high-water mark below the budget** (`LLM_HISTORY_HIGH_WATER`,
0.7) rather than at the budget. At the mark every turn still fits, which means the fold is
preparation for the *next* turn rather than a rescue for this one — and that is what makes
it correct to run it after the reply has been produced. If it fails, the digest does not
advance, the turns are still rows, and the next turn over the mark tries again.

It is awaited rather than fired into a background task. That costs the caller a few hundred
milliseconds on roughly one turn in ten, visibly, in a number the endpoint returns.
`BackgroundTasks` would hide both the cost and the failure, and the analysis job
([0006](0006-error-taxonomy.md)) is this project's one design for background work — two
answers to that question in one codebase is worse than one answer that is honest about its
price.

---

## 6. How much to trust these numbers

- **The context-shift measurements (§1) are solid.** Deterministic, reproduced across four
  `num_ctx` values, and independent of machine speed.
- **The estimator errors (§1) are solid** for the three prompt shapes tested, and those
  shapes are not a random sample of prompts. The margin is what makes that acceptable.
- **The adherence result (§2) is a null result at n = 25**, not evidence of equivalence.
  Both proxies saturate at 100 %, so the experiment had no power to distinguish the arms.
- **The turn latencies (§3) are from a quiet machine and are stated with their load.** The
  same code measured 2.7× slower at load 10–16, and that run is in §3 too so the range is
  visible rather than implied.
- **The A/B (§3) is the trustworthy part of the fallback claim, and only for the synthesis
  row.** Both arms ran on a quiet machine minutes apart, but the ASR and generation medians
  moved between them by more than the effect being measured, so the turn totals are not
  clean. One run of twenty turns per arm resolves ~140 ms on a quantity that size; it does
  not resolve a 50 ms difference in anything else.
- **Everything here is one machine.** M4 Max, 16 cores, 128 GB, host Ollama on Metal. The
  ratios will hold elsewhere; the numbers will not.

---

## 7. Revisit when

- **Replies get longer.** The turn passes at p95 2684 ms with 316 ms of margin, and reply
  length drives both generation and synthesis. It is the most likely thing to break this
  and the least tested lever in §9.1's list.
- **The client streams audio.** Time-to-first-audio becomes the number that matters and
  the overlap in §3 stops being worth 140 ms of turn latency and starts being worth most of
  a second of *perceived* latency — [0002](0002-tts-model-choice.md) measures 78 ms to the
  first sentence against 320 ms for a whole reply.
- **Whether the tail anchor earns its 30 tokens needs an instrument that measures character
  rather than format.** The persona suite ([0008](0008-evaluation-harness.md)) is that
  instrument.
- **A model with a real system role is configured.** Everything in §2 is specific to
  Gemma 3's template. `ChatMessage` already carries the distinction, so the request would
  say what was meant the day it stops being folded into a user turn.
- **`gemma3:4b` is swapped for something larger.** Generation has 628 ms of headroom
  against its stage budget and the turn has 316 ms overall; a 12b model would consume both.
  [0006](0006-error-taxonomy.md) asks the model-size question for error labelling, and the
  two should be decided together.
