# 0025 — Gemma 4 as the conversation and analysis model, with thinking off

Status: accepted

One language model serves the persona and the error detector, and it is `gemma4:latest`
(8B, Q4_K_M, 9.6 GB, Ollama 0.20.0 or later), asked not to think on every request. This
records what the switch was measured against, what it costs, and what turning thinking
off gives up.

## What was decided

1. **Every request to Ollama carries `think`.** Gemma 4 thinks by default: left alone, it
   writes 280–870 characters into `message.thinking` before the first word of a persona
   reply — 146–312 tokens generated for an answer of 55–60 — and the reply arrives
   1.6–3.5 s after the request against 0.7 s without. `services/llm/ollama.py` sends `"think": false` on
   every call, whole or streamed; the setting `LLM_THINK=1` lets the model's own default
   stand. A model without thinking ignores the field — Gemma 3 answers the same either way.
2. **The default model is `gemma4:latest`**, in `api/config.py`, `docker-compose.yml`
   and `.env.example`. A checkout whose `.env` still names `gemma3:4b` keeps it, because
   the file overrides the defaults; `make llm-check` prints the model the API is using.
3. **Thinking stays off for the analysis too.** With it on, the detector files more
   article mistakes under their kind (16 of 20 against 9) and takes 971 s over the sixty
   labelled sentences against 283 s — about eight seconds a call, on a job that a session's
   report waits for. One setting serves both callers; a per-call choice is not built until
   a measurement says the report can afford it.
4. **The model's markdown does not reach the screen or the voice.** A persona that
   emphasises with asterisks or quotes with backticks had both reaching the transcript as
   characters and Piper as words. Each sentence is stripped of paired and stray emphasis
   marks, heading and list marks before it is spoken, and the stored text is the same
   plain text; a fragment that was only marks is not spoken.

## Measured

The sixty hand-labelled sentences, one mistake in each and nothing else wrong, through
both detectors, twice per model with identical results:

| | Gemma 3 | Gemma 4, thinking on | **Gemma 4, thinking off** |
|---|---|---|---|
| Articles found and filed under their kind | 6 of 20 | 16 of 20 | **9 of 20** |
| Prepositions | 12 of 20 | 19 of 20 | **17 of 20** |
| False friends | 6 of 20 | 10 of 20 | **10 of 20** |
| Found under another kind | 8 / 7 / 9 | 1 / 0 / 2 | **4 / 1 / 4** |
| Proposed on the corrected sentence | 9 / 7 / 6 | 1 / 1 / 0 | **1 / 1 / 1** |
| With the labelled correction, of those found | 4 / 9 / 2 | 15 / 18 / 5 | **8 / 16 / 4** |
| The sixty, wall clock | 86 s | 971 s | **124–283 s**, three runs |

A fall in wrong proposals is only a better model if the taxonomy is not throwing more
away, so the suite also counts what the model proposed before anything refused it: over
the 120 sentences (each as said and as corrected) Gemma 4 with thinking off proposed 55
corrections; the taxonomy refused 7 — six whose correction equalled the original, one
whose subcategory did not belong to its kind — and a rule had already made 2. The 46
stored are the 34 found under their kind, the 9 under another kind and the 3 on corrected
sentences above. The per-kind figures were identical in all three runs.

The golden set of real turns, seven turns and eleven labelled errors: detection precision
0.500 over six scored proposals, recall 0.333, on both models; labelling precision 0.167
on Gemma 4 against 0.000 on Gemma 3. Too few to decide the question, as before.

The persona probes, nine probes and 15 phrasings of an instruction spoken in the scene,
ten attempts each:

| | Gemma 3 | **Gemma 4, thinking off** |
|---|---|---|
| Replies clean on every deterministic rule | 8 of 9 | **8 of 9** |
| Judged in character, judged to invite the form | 9 of 9, 9 of 9 | **9 of 9, 9 of 9** |
| Gave its instructions away | 2 of 150 (2–14 across runs) | **1 of 150** |
| Stepped out of the scene | 8 of 150 | **10 of 150** |
| The judge against ten hand-labelled replies | 8 of 10 | **8 of 10** |

A whole spoken turn, twenty turns through the recogniser, the model and the voice, the two
models back to back on the same machine:

| | Gemma 3, at load 2.6–8.5 | **Gemma 4, thinking off, at load 7.8–12** |
|---|---|---|
| Turn, p95 | 4417 ms | **4058 ms** |
| Turn, median | 3493 ms | **2875 ms** |
| Generation, median · p95 | 888 · 2229 ms | **869 · 1506 ms** |
| Recognition, median | 1400 ms | 1424 ms |
| Synthesis tail, median | 734 ms | 525 ms |

Both miss the 3 s budget on that machine, where recognition alone takes 1.4 s; generation is
level, and the token estimator's error on Gemma 4's counts is +5.5 % mean, −5.5 % at worst,
inside the 1.25 margin the context window is sized from.

The spoken answers, forty labelled: Gemma 4's shorter version has a content word the
speaker never said in **0 of 40** (Gemma 3: 26, with 9 withheld). A figure of zero is only
worth anything if the shorter version is a version at all, so three more things are
counted: none of the 40 is the answer word for word; its words are a median 0.72 of the
answer's (0.32–0.99); and it keeps a median 0.73 of the answer's content words, the least
0.32 — eleven of twenty-three, on the office-days answer. Every one has fewer sentences than
the answer. The check that withholds a rewrite with invented words is measured with no
model and still withholds 6 of 6 written to add a fact.

Thinking on the persona reply, warm, three runs each: 1.64, 3.47 and 3.20 s with 276–870
characters of thought and 146–312 tokens generated; 0.70, 0.64 and 0.70 s without, 55–60
tokens.

## Costs

- **The download.** 9.6 GB against 3.3, and Ollama 0.20.0 or later.
- **The analysis is slower.** About 1.0–2.4 s a detection call against 0.7 s, from the
  sixty, moving with the machine's load.
- **Fewer articles than the model can find.** Thinking off gives up 7 of the 16 article
  mistakes Gemma 4 files with thinking on; it still files 3 more than Gemma 3 did, with
  half as many under the wrong kind and a ninth of the proposals on correct sentences.

## Revisit if

- A measurement shows the session report can wait for thinking on the analysis call: the
  provider then takes `think` per call and the detector asks for it.
- A model with a real system channel is configured: the persona's twice-anchoring is
  built for a model without one, and its cost is thirty tokens a turn.
- The quiet-machine S2 figure is re-taken on Gemma 4 and misses where Gemma 3 met it.
