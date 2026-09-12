# 0022 — The model libraries

Status: accepted · 2026-09-13 · supersedes decision 12 of
[0021](0021-dependencies-images-and-the-supply-chain.md)

0021 brought every dependency current except the libraries the models run on, because
each of them can change what the product measures and none carried a published
vulnerability. This records upgrading them, one at a time, and what each changed.

## What was decided

1. **pron: torch 2.14.0, transformers 5.17.0, huggingface_hub 1.31.0.** torchaudio stays
   at 2.11.0: it is the latest release on PyTorch's CPU index, declares no torch version,
   and `pip check` passes against torch 2.14.0 — and its forced alignment returns the same
   answer on it, below.
2. **tts: onnxruntime 1.30.0, piper-tts 1.8.0.** Piper 1.8 still carries its espeak-ng
   phonemiser as a compiled extension, and the image's whole dependency closure is still
   seven packages.
3. **asr pins nothing new.** faster-whisper 1.2.1 and PyAV 18.1.0 are the latest releases.
   CTranslate2 4.8.2, onnxruntime 1.30.0 and huggingface_hub 1.31.0 were already current in
   the image, because faster-whisper leaves them unpinned and the build takes the current
   release.
4. **Each library was measured alone, against the image before it, instead of by a
   `make eval` per library.** Each one feeds one suite: torch, transformers and the hub the
   pronunciation suite; onnxruntime and Piper the synthesis suite, and the recogniser's
   suite through the voice it listens to. After each change the service was rebuilt, and
   the image built from the commit before this record ran beside it: the same audio and
   text, requests alternating between the two, so both saw the same machine. `make eval`
   runs once, on the committed tree, for the release, because the report carries the
   revision it was generated at and a tree with uncommitted code has none.
   **Accepted cost:** no report per library. The per-library figures are here.

## Measured

On 2026-09-13, in Docker, at load averages between 10 and 25 on 16 cores.

**Pronunciation**, after each of the three changes:

| | Result |
|---|---|
| Per-phone GOP, the probe (35 phones) and a passage-length reading (250) | **identical** to the image before, every field of every phone, after each change |
| The golden suite | unchanged: clean mean −0.386, 5th percentile −3.119; planted errors mean drop +8.138, **9 of 10 detected, 10 of 10 named**; 12 passages, 3 091 phones, 0 desyncs |
| Median latency, 8 alternating rounds, short / passage | torch 1 510 / 5 120 ms against 1 612 / 5 894; transformers 938 / 4 882 against 844 / 4 882; hub 1 398 / 7 617 against 1 237 / 7 636 |
| A cold download with hub 1.31.0 | an empty volume filled with the 1.2 GB of weights as uid 10001; loaded in 72.8 s |
| Image | 1.84 GB → **1.87 GB** (torch 1.86, transformers 1.87) |

**Synthesis**, 20 alternating requests per text:

| | Median whole reply, short / long | Audio length |
|---|---|---|
| onnxruntime 1.30.0 against 1.29.0 | 306 / 743 ms against 299 / 747 | the same |
| piper-tts 1.8.0 against 1.7.0 | 124 / 371 ms against 131 / 357 | the same |

`make tts-latency` 9 of 9 after each. Image 722 → **724 MB**.

**Recognition**, through the new voice and the old in the same sitting:

| | piper-tts 1.8.0 | 1.7.0 |
|---|---|---|
| Word error rate, human recordings | 1.72 % (4 / 232) | 1.72 % |
| 89 sentences said with their mistake, heard as the correction / as something else | 3 / 7 | 1 / 7; 2 / 5 earlier the same evening |
| Heard as said, of 20: articles, false friends, prepositions | 19, 18, 17 | 17, 18, 16; 18, 18, 16 earlier |
| Spoken answers: fillers, repeats, restarts, signposts | 22 / 24, 13 / 13, 9 / 9, 52 / 52 | 21 / 24, 13 / 13, 9 / 9, 52 / 52 |

Synthesis is not deterministic, and the two voices differ by no more than one voice differs
from itself an hour apart.

**Trivy**, CRITICAL / HIGH: pron 0 / 45, the one in a library still NLTK's, with no fix;
tts 0 / 44; none with a fixed release. CI's repository scan: exit 0.

## Found on the way

- **The pronunciation latency test fails on a machine this busy, with either image.** At a
  load average of 25 a passage-length reading took 10 252 ms against the 10 000 ms budget
  on the new image, and up to 10 096 ms on the old one alternating with it; at a load of 10
  it took 4 999 ms. The budget is a property of the service on a machine doing little
  else.
- **A golden run straight after `up --wait` skips every test.** `/health` answers while
  the weights load, so Compose calls the service healthy before it can score; the suite
  says the model is still loading and to run it again, which is what it is for.
- **The recogniser's figures on the synthetic voice are wider than published.** The
  unchanged voice gave 16 of 20 prepositions heard as said, twice, where the published
  range across the report's runs is 17 to 20. The report's next run is where that range
  moves.

## Revisit if

- torchaudio publishes a release past 2.11, or a torch release it cannot run on;
- a figure in the pronunciation suite moves after an upgrade — the per-phone output has
  not moved across three;
- the latency test fails on a quiet machine.
