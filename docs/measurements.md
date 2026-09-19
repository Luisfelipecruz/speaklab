# Measured

Every figure SpeakLab reports about itself, grouped by the part it measures, with what
produced it. **Source** is the command that measures a figure, the report `make eval` writes
— [evaluation.md](evaluation.md), never edited by hand — or the decision record that
holds the method. Anything not listed here has not been measured
and is not claimed.

Two ways to read these numbers:

- **A figure that comes from sampling is a range.** Synthesis samples, so the same sentence
  is never the same audio twice, and the persona's replies are sampled too; such a figure
  moves from run to run on the same code, and is given as the range across the runs
  recorded. The latest run is in [evaluation.md](evaluation.md).
- **Latencies are orders of magnitude.** They are medians on a laptop running other stacks,
  and they move by a factor of two with what else is busy. The ratios are what hold — the
  login pair below is a claim about the code whatever the machine is doing.

## Setup and footprint

| Measure | Figure | Source |
|---|---|---|
| First run, from nothing | `make setup` **2 min 33 s**, Whisper loaded at **2 min 43 s** — met against five minutes. The same build on a slower connection: 7 min 12 s and 8 min 58 s | a cold copy and `make setup` |
| Containers healthy | 5 of 5; 6 of 6 with `pron` | `make health` |
| Memory, five containers, models loaded | **1.02 GiB** after a conversation, a reading and an answer, Ollama excluded; the frontend 79 MiB of it | `docker stats` |
| Images | api **826 MB** with no torch, asr 790 MB, tts 724 MB, frontend **299 MB**, `postgres:16.15` 657 MB — 3.3 GB | `docker images` after a build |
| … and the development frontend | 1.06 GB, the `dev` profile's, with the source and every tool | its build |
| A page's first visit | **0.03–0.21 s** from the built frontend, against 0.63 s for a route the development server had not yet compiled | `curl` against the running frontend |
| … and the optional one | pron **1.87 GB**, the only image with torch in it | its build |
| Known vulnerabilities in the images built here | api, asr and tts **0 CRITICAL, 44 HIGH**, none with a fixed release yet; pron 0 and 45, one of them in a library — NLTK, with no fix published; frontend **0** | Trivy 0.74.0 on each image |
| … in the database image, pulled not built | `postgres:16.15` 14 CRITICAL, 101 HIGH: Debian packages, and upstream's `gosu` built with an old Go | Trivy 0.74.0 |
| The repository, as CI scans it | **0** HIGH or CRITICAL with a fix in the four requirements files and the lockfile; 0 Dockerfile misconfigurations; 0 secrets | the `security` job's command |
| Frontend releases the trust check refuses | **2** — older-line releases by their own maintainers, each excepted by exact version; every other package in the lockfile passes | pnpm 12.4.1's install; each checked against the npm registry |
| API test suite | **1 061** — 1 023 pass with Postgres alone; the other 38 need `asr`, `tts`, `pron` or Ollama | `make test` |
| Frontend test suite | **319** across 49 suites, no services needed | `make test-frontend` |
| API operations | **31** | `app.openapi()` |
| The project site | **35 pages**; 220 links, every one resolved — 177 to other pages, 8 to a heading on the same page, 9 to files in the repository, 26 elsewhere; no date outside the changelog; built in 0.2–1.1 s | `make site` |

### The first run, measured twice

Each time from a copy of `main` in a directory of its own — empty volumes, and a build cache
of its own that had to pull the Python and Node base images. Both times every container came
up healthy, the database was migrated and seeded, and the API reached the model, with no
manual step; and both times nearly all of it was the four images downloading their
dependencies in parallel — the API's `pip install` alone took 346 s on the slower
connection and 88 s on the faster. The first spoken turn was heard word for word and
answered, with audio, in 2.2 s and 3.5 s. Not in either figure: `postgres:16`, which was
already on the machine, and Ollama with its model, a prerequisite pulled once.

## The conversation

| Measure | Figure | Source |
|---|---|---|
| **A whole spoken turn, p95 over 20** | **2035 ms** against 3000 ms — met, on Gemma 4 with thinking off at a load average of 0.7–1.6; median 1849, recognition 826, generation 810 and a synthesis tail of 174 ms at the median. Gemma 3 met it at 2684 ms, at a load of 1.7–5.0 | `make turn-latency` |
| … on a busy machine | 7283 ms at load 10–16, 5356 ms at load 16.7–18.0, and 5330 ms at load 3.6–7.0 with another stack's containers working beside it — the same code, on Gemma 3 | `make turn-latency` |
| … the two models back to back | Gemma 4 with thinking off **4058 ms** (median 2875) at load 7.8–12, Gemma 3 4417 ms (median 3493) at load 2.6–8.5; generation median 869 against 888 ms, recognition 1.4 s on both | `make turn-latency`, [decision 0025](decisions/0025-gemma-4-with-thinking-off.md) |
| Thinking, on a persona reply | **0.64–0.70 s** with `think: false`, 1.6–3.5 s left to the model's default, warm, three runs each | [decision 0025](decisions/0025-gemma-4-with-thinking-off.md) |
| Turn stages, median | recognition 1146 ms · generation 872 ms · synthesis tail 235 ms | `make turn-latency` |
| Speaking while writing, against its control | 235 ms of synthesis left to wait for, against 375 ms in series | `make turn-latency-noflow` |
| Recognition, about six seconds of audio | **1231 ms** against a 700 ms stage budget — missed, deliberately; `base.en` meets it at 525 ms and 2.6× the word error | [decision 0001](decisions/0001-asr-model-choice.md) |
| Synthesis, an 80-token reply | **320 ms** whole against 400 ms, **78 ms** to the first sentence; 771 ms and 135 ms on a busy machine | `make tts-latency`, [decision 0002](decisions/0002-tts-model-choice.md) |
| Synthesis throughput | 50× real time on the CPU | `make tts-latency` |
| The prompt-size estimate against Ollama's own count | −6.4 % to +6.2 % across three prompt shapes | [decision 0003](decisions/0003-conversation-context-strategy.md) |
| **Persona replies clean of every deterministic rule** | **6 to 9 of 9** across nine runs, 9 in the latest; what fails is the sentence cap the persona itself states | `make persona-adherence`, [evaluation.md](evaluation.md) |
| The persona judge, against hand labels | **0.800** over ten replies; it misses the same two, the two the rules catch, in every run | [evaluation.md](evaluation.md) |
| **An instruction spoken inside the scene** | the persona gave its instructions away **16 of 200** times over ten phrasings, against **59 of 200** before the speaker's words were quoted; on five phrasings written afterwards, 1 of 100 against 26 | [decision 0013](decisions/0013-an-instruction-spoken-in-the-scene.md) |
| … in the suite `make eval` runs | fifteen phrasings, ten times each: **2 to 14 of 150** across eight runs, 2 in the latest | [evaluation.md](evaluation.md) |
| **A question with a figure in its answer** | seven questions to the letting agent, ten times each: the brief's figure in **70 of 70** replies, none quoting the brief; **22 of 70** named any figure before the brief carried the facts, 3 the right one | `make persona-adherence`, [decision 0027](decisions/0027-a-persona-that-answers-the-question.md) |

## Corrections and grammar

| Measure | Figure | Source |
|---|---|---|
| **Error detection precision** | **0.500** over six scored proposals, against 0.70 — not met, and not decidable on a corpus this size; the same in every run | [evaluation.md](evaluation.md) |
| Proposals refused by the gate | **25 %**, each with a reason | [decision 0006](decisions/0006-error-taxonomy.md) |
| **Grammar rules, on planted errors** | **130 of 172** agreement errors caught — 0.756 [0.686, 0.814] — and **2 of 129** missing articles, with no wrong fix and no stray proposal; nothing proposed on 3 111 words of native English. No model involved | [evaluation.md](evaluation.md), [decision 0014](decisions/0014-the-rule-layer.md) |
| **Which verb form a correction was made in** | **32 of 34** held-out corrections joined to both forms a teacher would name — 0.941 [0.809, 0.984] — and 2 of 4 real turns, where the parse of unpunctuated speech loses the verb; none joined to a wrong form | [evaluation.md](evaluation.md), [decision 0015](decisions/0015-accuracy-per-form.md) |
| **A mistake said aloud, heard as its correction** | **1 to 3 of 89** across eleven runs, 2 in the latest; a corrected sentence heard as the mistake **0 of 89** in every run. One clear synthetic voice, not a learner's | [evaluation.md](evaluation.md), [decision 0017](decisions/0017-the-spoken-drill.md) |
| Articles, prepositions and false friends, said aloud | **16 to 20 of 20** of each kind heard as said across ten runs; repaired by the recogniser, prepositions 18 of 200 tries, articles 4 of 200, false friends never | [evaluation.md](evaluation.md), [decision 0018](decisions/0018-scenarios-for-articles-prepositions-and-false-friends.md) |
| … found and filed under their kind | articles **9 of 20**, prepositions **17 of 20**, false friends **10 of 20** — identical in every run; 3 of the 60 corrected sentences drew a proposal. On Gemma 3: 6, 12 and 6 of 20, and 22 corrected sentences flagged | [evaluation.md](evaluation.md), [decision 0025](decisions/0025-gemma-4-with-thinking-off.md) |
| … one detection call | about **1.0–2.4 s**, from 124–283 s over the sixty sentences and their corrections across three runs; 0.7 s on Gemma 3; 8 s with thinking on | [decision 0025](decisions/0025-gemma-4-with-thinking-off.md) |
| … what the model proposed before the taxonomy | **55** over the 120 sentences, 7 refused (six a correction equal to its original), 2 superseded by a rule; the 46 stored are the counts above | [evaluation.md](evaluation.md) |
| Analysing one turn | median **4.9 s**, max 10.1 s — off the request path | [decision 0006](decisions/0006-error-taxonomy.md) |
| Ending straight after speaking | the report holds the last turn in **3 of 3** runs, the end taking 4.15–4.80 s | [decision 0014](decisions/0014-the-rule-layer.md) |
| Grammar forms in the stored corpus | **13 distinct**, over 106 counted instances in 11 turns, 48 of them verb phrases | the stored corpus |

## Read aloud

| Measure | Figure | Source |
|---|---|---|
| **GOP separation, ten planted errors** | **9 detected**, mean drop **8.138 nats**, the competing phone named **10 of 10** — the same in every run | `make pron-golden`, [evaluation.md](evaluation.md) |
| Clean-speech baseline | mean −0.386, **median exactly 0.000** over 35 correctly produced phones | [decision 0005](decisions/0005-gop-pipeline.md) |
| **Scoring a 34-second reading** | **7.5 s** for 250 phones, against 10 s | `make pron-golden` |
| Alignment over the shipped passages | 12 of 12, **3091 phones, 0 desyncs** | [decision 0005](decisions/0005-gop-pipeline.md) |
| **Word error rate, `small.en`** | **1.72 %** on ten LibriSpeech utterances, 232 reference words — the same in every run | `make asr-wer`, [evaluation.md](evaluation.md) |

The word error rate is a **floor**: LibriSpeech is native, fluent, read-aloud English, and a
learner's speech will be worse by an amount that set cannot estimate.

## Make your point

| Measure | Figure | Source |
|---|---|---|
| **The counter, on 16 held-out answers** | precision / recall: reasons **0.957 / 1.000**, examples 1.000 / 0.909, steps 0.933 / 1.000, contrasts 1.000 / 1.000, summing up 1.000 / 1.000, a word said twice 0.923 / 1.000. **A phrase started again 0.636 / 0.636 — below the bar, so counted and not shown.** No model involved | [evaluation.md](evaluation.md), [decision 0019](decisions/0019-make-your-point.md) |
| A spoken answer, as the recogniser writes it | twelve answers spoken by the `tts` voice, seven runs: fillers **21 to 23 of 24**, words said twice 12 to 13 of 13, phrases started again 8 to 9 of 9, signposts 52 of 52 every time; the sentence count within one of the written in 8 to 12 of 12 | [evaluation.md](evaluation.md), [decision 0019](decisions/0019-make-your-point.md) |
| **The model's shorter version** | on 40 labelled answers, a content word the speaker never said in **0**, none withheld, every one shorter than the answer; Gemma 3's put one in 26 and had 9 withheld, 2 of 16 held out | [evaluation.md](evaluation.md), [decision 0025](decisions/0025-gemma-4-with-thinking-off.md) |
| … and whether it is a version at all | none of the 40 is the answer word for word; its words a median **0.72** of the answer's (0.32–0.99); the answer's content words kept, median **0.73**, least 0.32 | [evaluation.md](evaluation.md) |
| The check on a shorter version | withholds **6 of 6** rewrites written to add a fact, and shows 6 of 6 faithful ones | [evaluation.md](evaluation.md) |

## Progress

| Measure | Figure | Source |
|---|---|---|
| **Sessions behind the trends** | **7** on 2 calendar days on the best-provisioned account, against 20 — criterion S7 not met | the census in [evaluation.md](evaluation.md) |
| The stored corpus, rolled up | 7 turns · 272 words · 2 readings · 450 phone instances · **2.57 errors per 100 words** · 11 distinct forms · one week | [decision 0007](decisions/0007-progress-metrics.md) |
| Reading the progress page | **7 ms** — it reads snapshots and computes nothing; a forced rebuild of both snapshots, 17 ms | [decision 0007](decisions/0007-progress-metrics.md) |

## The API

| Measure | Figure | Source |
|---|---|---|
| `GET /scenarios`, warm | 3.5 ms median | timed against the running API |
| `GET /health`, warm | 32 ms median — every model probe answering, rather than failing DNS fast | timed against the running API |
| `POST /auth/register` | 61 ms median — one Argon2id hash at 64 MiB | timed against the running API |
| Wrong password against unknown email | 75.6 against 78.1 ms — the login endpoint does not reveal who has an account | timed against the running API |
