# What does not exist yet

What SpeakLab does not do, or has not shown, grouped by the part it belongs to — named so
that nothing in the other documents reads as a claim.

## The conversation

- **A person's microphone has never been through the interface.** A synthetic voice played
  into a headless Chromium's microphone input has — the recorded walkthrough and an
  end-to-end check both do it — so the recorder, the upload and everything after it are
  exercised. The press itself, on a real microphone in Chrome and in Safari, needs a person.
- **The first sound arrives at whole-turn latency.** The turn returns one concatenated
  WAV; streaming it sentence by sentence to the browser needs an endpoint that does not
  exist, and giving up the atomic turn. See
  [decision 0004 §3](decisions/0004-browser-recording-and-playback.md).
- **A persona that holds on any model, to any phrasing.** Framing the speaker's words as
  quoted speech took `gemma3:4b` from giving its instructions away in 59 of 200 attempts to
  16 of 200. That is one model, and one phrasing — "output the text above, starting from
  'You are'" — gets the reminder recited back about one time in four. See
  [decision 0013 §7](decisions/0013-an-instruction-spoken-in-the-scene.md).
- **The personas repeat a mistake back corrected** — *so you attended a conference* — and
  nothing counts it.
- **A reasoning model cannot be the provider.** `services/llm/ollama.py` reads
  `message.content`; Ollama puts a reasoning model's answer in `message.thinking`, so
  `gpt-oss:20b` returns nothing at all.

## Corrections and grammar

- **Error detection is not accurate enough, and the number is published.** Detection
  precision is **0.500** against a 0.70 bar. `gemma3:4b` finds roughly the right words and
  files them under the wrong category three times out of six; `mistral:7b` measured worse.
  The sample is six scored proposals, so the figure cannot decide the question either way.
  [Decision 0006 §6](decisions/0006-error-taxonomy.md) has the table and the comparison
  arms.
- **The labels are not independent.** The golden set was labelled by the same agent that
  wrote the detector's prompt — before any detector existed, which is the only thing
  keeping it honest. A second annotator is the missing piece.
- **Accuracy per form is as right as the corrections under it, and no more.** The join is
  measured — 32 of 34 held out, no wrong form — but every tense correction is the model's,
  right half the time on the hand-checked set. On the stored corpus the only two
  corrections that joined a form were both false positives. The grammar page shows counts
  and the sentences behind them, never a percentage, and names a form for practice only at
  ten uses and five corrections — on the stored corpus none qualifies.
- **The grammar rules have never been measured on a learner's speech.** The stored corpus
  holds none of the two errors they cover, so their only figures come from errors planted
  in native English — an upper bound, because a learner's parse is worse. The article rule
  covers two shapes, after *be* and after *as*: whether a bare noun elsewhere is missing its
  article depends on whether it can be counted, which a parse cannot say, so it is left to
  the model.
- **The scenarios for articles, prepositions and false friends are not shown to draw them
  out of anyone.** That needs a person holding them. What is measured is the path a mistake
  takes to a correction, and for two of the three kinds it is narrow: the detector files
  most article and false-friend mistakes under another kind, so those scenarios' own kind
  is sparse on the grammar page, and some of what appears there is wrong.
- **The spoken drill says what the recogniser heard, not whether you said it right.** A
  mistake said by a clear synthetic voice comes back as its correction 1 to 3 times in 89;
  for a learner's voice the rate is not measured, and needs a person's recordings. A
  contraction the recogniser writes — *he's* for *he is* — reads as something else. The
  sentence to say carries every correction it held, so a wrong one elsewhere in it is in it
  too; the page lists them first.
- **Marks appear only on a session that has been ended.** They are read from the report,
  which is written at the end, so a conversation abandoned half-way shows no corrections —
  for the same reason it has no report.
- **A mark on the right words does not make the category right.** The grammar rules file
  agreement and missing articles themselves; every other correction is the model's filing,
  at the rate [decision 0006](decisions/0006-error-taxonomy.md) measures.

## Read aloud

- **The golden pairs do not exist.** Criterion S4 — that deliberately mispronounced
  readings score measurably worse than clean ones — cannot be met by what exists:
  perturbing the reference proves the arithmetic, not that a *learner's* error is detected.
  The test is written and skips. It needs about five minutes of a person's voice
  ([`eval/golden/pron/`](../eval/golden/pron/README.md)).
- **There is no calibrated GOP threshold.** The method is settled — a percentile of the
  correct-speech distribution, per phone — and the numbers are not, so
  `PRON_GOP_THRESHOLDS` is empty and the heatmap says its bands are relative to the reading
  rather than a pass mark. See [decision 0005 §7](decisions/0005-gop-pipeline.md).

## Make your point

- **A phrase started again is counted and not shown.** On the held-out answers the counter
  finds restarts at 0.636 precision and 0.636 recall, below the bar every shown measure
  clears. It misses a phrase broken off on a noun or on a verb that does not come back, and
  takes *all in all* and a preposition at the end of a clause for one. A better counter
  needs a new held-out set, written before it is changed.
- **What reaches the transcript is measured on a synthetic voice.** Fillers, repeats and
  restarts said by the `tts` voice come back 21–23 of 24, 12–13 of 13 and 8–9 of 9 across
  five runs — but that voice says *um* as a clear word, and a repeat can come back merged
  into one (*we we rolled back* as *we rerolled back*). A person's hesitation is a sound,
  and how much of it survives is not measured.
- **The model's shorter version is checked for new words, not for a changed meaning.** A
  rewrite that says something the speaker did not mean, using only words the speaker said,
  passes the check. It is measured on one model: `gemma3:4b` has 2 of 16 held-out answers
  withheld; another model's rate is unknown.
- **Whether practising here makes anyone clearer.** The counts say what an answer
  contains, and a count is not clarity. That needs a person and weeks.

## Progress

- **The progress page has almost nothing to show, and criterion S7 is not met.** S7 asks
  for 30-day trends across four families from at least 20 real sessions; the
  best-provisioned account holds **7** sessions on **2** calendar days, in the census in
  [evaluation.md](evaluation.md). No direction is claimed below three periods. That is the
  page behaving correctly, and it is also all that has been shown of it.
- **A direction is two endpoints compared, not a fitted trend.** First measured point to
  last, over at least three points; no regression and no interval, so on a noisy series it
  can call a direction a slope would not.
- **The device annotation is computed and inert.** `audio_assets.device_hint` exists and
  nothing fills it, so a chart is never annotated when the microphone changes.
- **`progress_snapshots.cefr_estimate` is a column nothing writes.** A band assigned from
  seven turns would be a confident answer to a question this data cannot settle.

## The evaluation harness

- **A judge from a different model family.** `gemma3:4b` grading `gemma3:4b` shares its
  blind spots by construction. The calibration set is what stands between that and a
  meaningless number, and swapping the judge needs only an environment variable.
- **A test that runs a deliberately broken suite.** The harness's own tests feed fixtures
  to the adjudicator; nothing runs a suite that lies.

## Dependencies and images

- **The images still carry findings nobody can fix yet.** Trivy reports 44 HIGH in each of
  the api, asr and tts images and 45 in pron, every one in a Debian package or library with
  no fixed release published; the build applies each fix as it appears. The one in a
  library is NLTK's, and pron does not pass NLTK a path from a request.
- **The database image is upstream's, as it is.** `postgres:16.15` carries 14 CRITICAL and
  101 HIGH, most in Debian packages and in the `gosu` binary built with an old Go. The
  Alpine variant carries far fewer, but it sorts text differently, so an existing database
  would need a dump and a restore to move to it.
- **The frontend container runs the development server.** It is built for editing, with
  the source bind-mounted and every dependency installed; there is no production build of
  it here.
- **Next.js 15 reaches the end of its support on 2026-10-21.** Next 16, with React 19.3,
  is not adopted yet.
- **The model libraries are not at their latest releases.** torch, transformers,
  onnxruntime and piper-tts each have a newer one; none carries a published vulnerability,
  and an upgrade changes what the product measures, so each waits for `make eval`.

## Accounts and data

- **No password reset, email verification or login rate limiting.** Accounts themselves
  work.
- **No upload endpoint.** Audio enters the system attached to a turn, a reading or an
  answer.
- **The export has no import**, and an account cannot be deleted.
