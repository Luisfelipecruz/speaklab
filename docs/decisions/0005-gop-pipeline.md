# 0005 — The GOP pipeline: forced alignment in production

**Status:** accepted · **Date:** 2026-08-30 · **Milestone:** m8
**Promotes:** the m0 spike (`spike/gop-feasibility.md`), per plan §7 m0

Read this before touching `infra/pron/`, the phone map, or anything that reports a
per-phoneme number to a learner.

---

## What was decided

1. **The m0 method ships unchanged.** Forced alignment against a wav2vec2 CTC phoneme
   model, GOP as Witt & Young define it, per-phone rows carrying the phone that actually
   won. Re-measured through the production service: **identical to the spike, to three
   decimal places**.
2. **The vocabulary is vendored into the repository**, not fetched during the image build.
3. **The competitor maximum is taken over phones, excluding CTC's blank.** A deviation
   from the spike, and a measured one: it changed **0 of 35** rows on real speech.
4. **`torch` is installed from PyTorch's CPU index.** Not a tidy-up — it is 6.7 GB.
5. **Scoring is asynchronous, but only the alignment half.** Transcription happens inside
   the request because the audio row cannot exist without it.
6. **Read-aloud requires audio retention, and refuses rather than working around it.**
   FR-16 and FR-26 genuinely conflict for this feature.
7. **No GOP threshold is configured, and the interface says so.** Q2 stays open.

---

## 1. The image: 8.51 GB, and why

The plan budgeted "~2 GB of torch" for the `pron` image and profiled the service on that
basis (D10). The first build came out at **8.51 GB**. `du` inside it named the cause:

```
2.9G  site-packages/nvidia
914M  site-packages/torch
652M  site-packages/triton
```

**PyPI's `torch` wheels declare the whole NVIDIA CUDA stack as dependencies on
`linux/aarch64` as well as on x86_64.** The aarch64 wheels exist for Jetson and GH200, so
building on an Apple-silicon laptop — which produces a `linux/arm64` image that will only
ever run on CPU — still drags in 3.5 GB of CUDA libraries and Triton that no code in the
image can execute.

The `requirements.txt` comment written before measuring said the opposite: *"On
linux/arm64 PyPI's torch wheels are already CPU-only."* That was wrong, and it is the kind
of wrong that never surfaces as a failure — the image works, it is just four times the
size it should be. It surfaced because the size was looked at.

**The fix is a separate install from an index that only has CPU builds:**

```dockerfile
RUN pip install --no-cache-dir \
    --index-url https://download.pytorch.org/whl/cpu \
    torch==2.13.0 torchaudio==2.11.0
RUN pip install --no-cache-dir -r requirements.txt && pip check
```

`--extra-index-url` was tried in principle and rejected: both indexes carry version
2.13.0, pip is free to take either, and an image whose size depends on resolver mood is
worse than a duplicated version pin. `pip check` at the end is what makes the duplication
safe — if the Dockerfile and `requirements.txt` ever disagree, the build fails.

**Result: 8.51 GB → 1.78 GB**, no `nvidia`, no `triton`, and back inside the budget the
profile decision was made against.

---

## 2. `vocab.json` is in the repository

m0 prescribed reading `vocab.json` off the hub at build time, to avoid instantiating
`Wav2Vec2PhonemeCTCTokenizer` — which would drag in `phonemizer` and the espeak-ng
binary for a job this project does itself. That advice is kept. What changed is *when*.

The file is now committed at `infra/pron/vocab.json` (4.6 KB, 392 tokens), and three
things follow that do not follow from fetching it:

- **The phone map became testable without the image.** `api/tests/test_phone_map.py` runs
  in CI, on a runner with no torch, no network and no 1.2 GB download, and asserts the map
  against the model's real vocabulary. That test is the one that catches the U+0261 trap.
  **A test that can only run inside a 1.78 GB image is a test that stops being run.**
- **The ids are pinned.** These 392 tokens are the meaning of every number this system
  stores. Fetching them at build time means an upstream edit to the model card silently
  redefines every phone in every stored score, with no diff anywhere to notice.
- **The build stopped needing the network** for anything but pip and NLTK.

The vendored file is a claim; the weights are the fact. So `app.py` checks
`model.config.vocab_size` against `len(VOCAB)` at start-up and refuses to serve if they
disagree — the failure mode where every symbol still resolves and every id now means a
different sound.

### The import-time assertion is kept, and the build runs it

`phone_map.py` builds its table at import and raises on any token the vocabulary does not
contain. The Dockerfile then does:

```dockerfile
RUN python -c "import phone_map; print(phone_map.summary())"
```

so a bad edit fails the **build**, loudly, in front of whoever made it — rather than at
the first request, in front of a user, as a number that measures nothing.

Both m0 traps are re-confirmed present in this vocabulary and both are asserted in tests:
`ɡ` is U+0261 and ASCII `g` is **absent entirely** (id would be nothing), and `r` (id 31)
exists as the trill while English /r/ is `ɹ` (id 27).

---

## 3. The tokeniser bug: two of the twelve shipped passages

The spike's rule for splitting reference text into words was *a whitespace token with
`.,!?;:` stripped*. Checked against the real seed file before writing any production code:

```
DESYNC a-pleasure-to-measure: 79 surface words vs 78 phone groups
DESYNC in-june-the-judge:     73 surface words vs 72 phone groups
```

**Both passages contain a standalone em dash.** It survives that strip, counts as a word,
and produces no phones — so the two sequences differ by one, and `spike/gop.py` raises
`ValueError`. Read-aloud would have been broken on **a sixth of the shipped corpus**, and
the failure would have read as a bug in alignment rather than in tokenisation.

The rule is now **a token containing at least one letter**, which is effectively the rule
`g2p_en` itself applies. 12 of 12 passages align, 3091 phones.

The bug is worth stating carefully, because the interesting part is not the em dash. The
old rule was *a list of punctuation somebody thought of*; the new one is a property. That
is why the regression test is parameterised over eight marks rather than written once for
the dash, and why it runs against `api/seeds/passages.json` rather than a fixture — a
passage added next month fails the test in thirty seconds instead of failing a user.

### Homographs are why the whole passage is converted at once

`g2p_en` tags parts of speech before it looks anything up. In `in-june-the-judge` the word
*use* is a verb: the passage converted whole gives `Y UW1 Z`, and the same word converted
on its own gives `Y UW1 S`. Scoring a learner's correct /z/ against a canonical /s/ would
mark right speech wrong — in a word chosen for that passage precisely because it is a
/dʒ/–/j/ contrast. **Per-word G2P is not a simplification of this module; it is a
different and worse answer.** It is also the reason the re-attribution above has to exist
at all.

### The desync check is kept, and it is a 422

Passages are authored content and the corpus will grow. `$5` becomes two phone groups for
one token; `Dr.` becomes `D R AY1 V` plus a stray group. When the two disagree, nothing is
scored and the error names the passage. A misaligned reading does not produce
slightly-wrong scores — it attributes every phone to the wrong word from the divergence
onward, which is a screen full of confident nonsense.

---

## 4. Three deviations from the spike, each with a reason

### 4.1 PyAV, not `soundfile`

m0 prescribed `soundfile` because `torchaudio.load` now requires `torchcodec`. Correct
about `torchaudio`, wrong about the replacement: **`soundfile` cannot open WebM/Opus or
MP4/AAC**, which is exactly what `MediaRecorder` produces (decision 0004 §2). PyAV is the
ffmpeg libraries in-process, it is already proven in `infra/asr`, and it means this image
needs no ffmpeg binary.

The decode function is a near-copy of the one in `infra/asr/app.py`, and the duplication
is deliberate: these are separate images with separate dependency sets, and the
alternative to forty duplicated lines is a shared build context that couples a 1.78 GB
image's cache to a 200 MB one's.

### 4.2 `merge_tokens`, not a hand-walked alignment

The spike walked the frame labels itself and had to defend against emitting more spans
than there were targets (`if pos >= len(flat): continue`). `torchaudio.functional.merge_tokens`
returns exactly one span per target, so that class of off-by-one is gone and the code
**asserts** the count rather than skipping the overflow. Wrong attribution is a heatmap
that tints the wrong word, which is worse than a crash because it looks like an answer.

### 4.3 The competitor maximum excludes CTC's blank — measured at zero

Witt & Young's max is over the phone set. The spike took it over every token, blank
included. **The blank is not a phone**, and a segment where it wins is a segment that was
short or quiet — not one where the speaker produced silence instead of a /θ/. Reporting
`<pad>` as "what you said instead" would be a claim about speech the acoustic model never
made, which is what invariant I2 forbids.

That is the principle. The measurement is what makes it a decision rather than a
preference — `gop.py` computes the spike's arithmetic too, as `gop_all_tokens`:

| material | rows | rows where excluding the blank changed GOP |
|---|---:|---:|
| the probe, against its own truth (real speech, matching text) | 35 | **0** |
| 34 s of audio against a mismatched 79-word passage | 250 | 2 |

**Zero on real, matching material.** The two on mismatched audio are in a case where the
alignment is meaningless anyway. So the deviation is principled, and its measured cost on
anything the product will actually see is nothing — which is why m0's numbers reproduce
exactly despite the change.

---

## 5. What was measured

All of it through the live service, via `make pron-golden`. Every figure below came from
running the system on the date of this document (invariant I9).

### 5.1 The probe reproduces m0 exactly

Real human speech (VOiCES, 3.4 s, native adult English) scored against reference text
containing a phone the speaker did not produce. Threshold is the 5th percentile of GOP
over the correctly produced phones — the operating point that would wrongly flag 5 % of
correct speech.

```
  detection threshold = 5th pctile of clean GOP = -3.119

  #  contrast                        clean    wrong    drop  heard   verdict
  1  /b/ against spoken /h/          0.000   -9.366   9.366  h       DETECTED
  2  /s/ against spoken /ð/          0.000  -10.687  10.687  ð       DETECTED
  3  /d/ against spoken /b/          0.000   -7.311   7.311  b       DETECTED
  4  /w/ against spoken /m/          0.000   -9.985   9.985  m       DETECTED
  5  /ɪ/ against spoken /æ/          0.000   -2.232   2.232  æ       missed
  6  /ʌ/ against spoken /ɪ/          0.000   -6.212   6.212  ɪ       DETECTED
  7  /k/ against spoken /m/          0.000  -10.658  10.658  m       DETECTED
  8  /t/ against spoken /d/, final   0.000   -4.737   4.737  d       DETECTED
  9  /n/ against spoken /m/          0.000   -6.373   6.373  m       DETECTED
  10 /tʃ/ against spoken /ð/         0.000  -13.819  13.819  ð       DETECTED

  mean drop +8.138   detected 9/10   named 10/10
```

Baseline over the 35 correctly produced phones: **mean −0.386, median exactly 0.000, p5
−3.1195**. Every one of these matches `spike/gop-feasibility.md` §4 to the digit, through
an entirely rewritten code path — different span extraction, different competitor set,
different I/O library, running in a container instead of on the host. That agreement is
the strongest evidence available that the rewrite is faithful.

**The one miss is a vowel, and it is the expected shape of the failure.** Consonant probes
averaged a 9.0-nat drop; the two vowel probes averaged 4.2. Vowel quality is gradient and
formant-continuous where stops and fricatives are categorical. This is the evidence for
per-phone thresholds rather than a global one, and it is why §7 does not ship a threshold.

### 5.2 The corpus aligns

All 12 seeded passages through real `g2p_en` and the live service: **3091 phones, 0
desyncs**, every phone attributed to a word. Counts are pinned in `api/tests/test_g2p.py`
so a dependency upgrade that changes a pronunciation fails a test rather than a reading.

### 5.3 Latency, and the number that does not extrapolate

| audio | phones | service | round trip | per audio-second |
|---|---:|---:|---:|---:|
| 3.4 s | 35 | 819 ms | 825 ms | 241 ms |
| 34.0 s | 250 | 8095 ms | 8105 ms | 238 ms |

**Linear in audio length**, as expected. And **m0's 99.5 ms on the same 3.4 s of audio is
not the number that matters** — that was measured on the host with 8 torch threads; the
service is 8.2× slower in its container. The cost is the container's CPU allocation, not
the method.

Against PRD §9.1's 10 000 ms budget for asynchronous read-aloud scoring, a 34-second
reading lands at 8.1 s. **That is 1.9 s of margin, and it is the thinnest budget in the
system.** Decision 0004 §3a measured stage degradation of 1.3×–3.4× on a loaded machine.
This budget will be missed under load, and the honest thing is to say so now rather than
discover it: see §8.

### 5.4 End to end, through the real API

One reading of 34 s posted to `POST /attempts` on the live stack:

```
POST /attempts -> pending in 6.6s     wer 0.962
after 11.2s total: status=scored  pronunciation=ok  phonemes 250
```

The WER of 0.962 is correct and is the design working: the audio does not say that
passage, and that is precisely what WER is stored to detect. Per-phone GOP against the
wrong words is noise with decimal places, and the interface says so above 0.5.

---

## 6. Two design decisions the schema forced

### 6.1 Only the alignment is asynchronous

The plan says scoring is asynchronous and the client polls (FR-15). Half of it cannot be.
`audio_assets.duration_ms`, `sample_rate` and `format` are NOT NULL and only a decoder
knows them, so the row cannot exist until the recording has been decoded — which is the
recogniser's pass. So:

```
POST /attempts   transcribe + store + WER   inside the request   ~6.6 s
background       G2P + align + GOP          polled               ~4.6 s
```

This also makes PRD R6 fall out rather than be implemented: an attempt whose `pron` never
answers still has everything the recogniser produced, because the recogniser ran first and
in a different request.

**No migration was needed.** m2 built the whole of plan §5, `attempts` and
`phoneme_scores` included, so the `0005_attempts_phonemes.py` the plan lists does not
exist — writing an empty revision to match a deliverables list would be worse than not
writing one.

### 6.2 FR-16 and FR-26 conflict, and read-aloud refuses

`attempts.audio_asset_id` is NOT NULL by design: *"an attempt without its audio cannot be
rescored — FR-16 would be a promise the schema could not keep."* An account with
`retain_audio` off has asked for exactly the opposite.

There is no arrangement that honours both. The options were to store the recording anyway
(breaking a promise the user made a deliberate choice about), to drop rescoring silently
for those accounts (an FR-16 that is true for some users), or to refuse. **It refuses**,
with a 409 that names the setting and points at conversation practice, which works with
retention off and stores no audio.

This is a product decision made by an agent and it deserves a human's eye: handoff **Q14**.

---

## 7. No threshold is configured, and the interface says so

`PRON_GOP_THRESHOLDS` is an empty map. m0 settled the *method* — a percentile of the
correct-speech distribution, per phone — and could not settle the numbers: one speaker, 35
phones, 10 probes. The spike's −3.119 is **one native speaker's number** and is
deliberately not the default.

So the API reports each reading's own 5th percentile, and the heatmap bands are relative
to the reading with a legend that says so: *"These bands are relative to this reading, not
a pass mark."* A consequence worth being awake to is that roughly 5 % of words are tinted
even in a flawless reading, because a percentile always has something below it — which is
why the strongest band is styled as *attention* rather than *error*, and why the count is
shown. "3 of 79 words marked" reads very differently from a page of red.

A calibrated threshold that is wrong would silently decide which sounds a learner is told
to work on. An honest relative ranking is less than the PRD asks for and is what the
measurements support. **Q2 stays open.**

---

## 8. What this does not establish

1. **Criterion S4 is not met.** It cannot be met by the probe. Perturbing the *reference*
   proves the arithmetic separates a produced phone from an unproduced one; it does not
   prove the system detects a **learner** error, because a planted reference is a
   categorically different phone and a learner error is gradient — a retracted /s/,
   epenthesis with a particular vowel quality, an unreleased final stop. **m0's 8-nat gap
   is an upper bound.** `test_gop.py::test_broken_readings_score_worse_than_clean_ones`
   exists, skips, and says what it needs: five minutes of somebody's voice,
   `spike/RECORD.md`.
2. **The latency budget has 1.9 s of margin and will be missed under load.** Nothing was
   changed in response, for the same reason m6 declined to act on its own margin: every
   available lever trades quality for a problem the machine does not have when idle. But
   this one is thinner than m6's, and the fallback if it becomes real is a smaller
   wav2vec2 or chunked alignment, not a faster loop.
3. **The r-coloured segmentation question is still open.** eSpeak emits `ɑːɹ ɔːɹ oːɹ ɛɹ ɪɹ
   ʊɹ aɪɚ aɪə` as single tokens where `g2p_en` emits two ARPAbet phones. Every *symbol*
   maps; *segmentation* can differ. `gop.py` flags affected rows and the summary counts
   them — **0 on everything measured so far** — so the decision can be made on a count
   rather than on a guess.
4. **Safari has still never recorded through this app**, which is m7's outstanding item
   and now applies to this screen too.
5. **One speaker, and not the target speaker.** Everything above is native adult English.
   The users of this product are not that.

---

## 9. Consequences

- **D3 confirmed in production.** The ASR-diff fork in handoff §10 is not taken.
- **`spike/` can now be deleted** except `RECORD.md` and `passages.json`, which are inputs
  to the work in §8.1. `phone_map.py` has moved into `infra/pron/` with its safety
  properties intact and tests around them.
- **`make pron-golden`** is where every number in §5 comes from. `make pron-fetch` is not
  an audit step here but the way the probe reaches a machine at all — `*.wav` is
  gitignored (trap 4), so unlike `eval/golden/asr` nothing in `eval/golden/pron` is
  versioned but the manifest.
- **Q2 (threshold) remains open** with the method settled and the numbers not.
- **Q14 (read-aloud versus audio retention) is new** and is a product call.
