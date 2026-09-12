# ASR golden set

Ten utterances, ten speakers, 83 seconds. `manifest.json` is the index; every entry
carries the reference transcript and the sha256 of the audio beside it.

## What it is

LibriSpeech **test-clean**, the standard held-out split, fetched through the Hugging Face
dataset viewer at ten pinned row indices. Read English by adult native speakers in good
recording conditions, with references verified by the corpus authors.

Regenerate and audit with:

```bash
python3 eval/golden/asr/fetch.py          # re-downloads only what the manifest cannot vouch for
```

The row indices are pinned in the script, so a re-run reproduces the same ten files, and
the sha256 in the manifest is what proves it did.

## What it is not

**It is not representative of the people this product is for.** Every claim measured
here is about native, fluent, read-aloud speech recorded on good equipment. That makes it
the right instrument for exactly one question — *what is the recogniser's floor?* — and
the wrong instrument for *how well does this work for a Spanish-L1 learner?*

A WER measured here is a lower bound. Learner speech is accented, disfluent, and recorded
on a laptop microphone in a room; the error rate will be higher and the gap is not
estimable from this set. Closing it needs learner recordings; the pronunciation set's
protocol ([`eval/golden/pron/README.md`](../pron/README.md)) is the first five minutes of
that work.

**It is also not the pronunciation golden set.** That one is human recordings of *planted
errors*, it belongs to m8, and it cannot be drawn from a corpus of correct speech.

## Why not the recordings already in `spike/audio/`

They are macOS `say` output. m0 established that instrument is degenerate — two takes
saying genuinely different words decoded to an identical phone string
(`spike/gop-feasibility.md` §3). WER against synthetic speech from a single fallback
voice would be a flattering number about nothing.

## Licence

LibriSpeech is distributed under **CC BY 4.0**. Attribution, as the licence requires:

> LibriSpeech ASR corpus — V. Panayotov, G. Chen, D. Povey, S. Khudanpur,
> *"LibriSpeech: an ASR corpus based on public domain audio books"*, ICASSP 2015.
> <http://www.openslr.org/12>

The files here are unmodified excerpts of the `test-clean` split.

## Why the audio is committed

`.gitignore` excludes `*.wav` and friends so that user recordings and model weights can
never reach the history. This directory is the stated exception, and it is a deliberate
one: an evaluation whose fixtures are downloaded at run time is an evaluation that
changes when the network does. 1.6 MB of FLAC buys a number that means the same thing in
CI, on a laptop, and in a year.

FLAC rather than WAV is not only about size. The service under test claims to normalise
*whatever arrives* to 16 kHz mono PCM at its own boundary; a golden set that was already
in the target format would never exercise that claim.
