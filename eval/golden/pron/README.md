# Pronunciation golden set

Two things live here, and they answer different questions.

| | what it is | what it proves | status |
|---|---|---|---|
| **The probe** | one real human recording, scored against *deliberately wrong reference text* | the pipeline separates a phone that was produced from one that was not | **fetchable now** |
| **The pairs** | human recordings of the same passages read correctly and with planted errors | criterion **S4** — broken readings score measurably worse than clean ones | **not recorded yet** |

## The probe — reference perturbation

`fetch.py` downloads one 3.4-second utterance of read English by a native speaker and
`manifest.json` carries ten probes over it. Each probe replaces one word of the reference
with a word containing a phone the speaker **did not** produce, and asserts that GOP at
that phone collapses.

This is the mirror image of planting an error in the audio, and it runs on genuine human
speech, which is why m0 used it after the first attempt failed (see below). It is exactly
the situation the product is in when a learner mispronounces a word: the reference says
one sound, the waveform contains another.

m0 measured **9 of 10 detected**, mean drop **8.138 nats**, Cohen's d **8.26**, with the
competing phone named correctly in **10 of 10** — including the one probe the threshold
missed. `api/tests/test_gop.py` re-runs it through the live service.

**The one miss is a vowel, and that is the expected shape of the failure.** /ɪ/ against
spoken /æ/ dropped 2.23 where the consonant probes averaged 9.0. Vowel quality is gradient
and formant-continuous; stops and fricatives are categorical. It is the evidence behind
per-phone thresholds rather than a global one.

## The pairs — not yet recorded, and they need a person

**S4 cannot be met by the probe.** Perturbing the reference proves the arithmetic works;
it does not prove the system detects a *learner error*, because a planted reference is a
categorically different phone and a learner error is a gradient one — a retracted /s/,
epenthesis with a particular vowel quality, an unreleased final stop. The 8-nat gap above
is an upper bound.

The protocol is `spike/RECORD.md` — about five minutes. **Note that it was written for
m0 and tells you to put the files in `spike/audio/`; put them here instead**, or do both:
the spike scripts and this suite read different directories, and only this one is wired to
criterion S4.

### What to say

Read each line twice — once normally, once saying the **bold** words wrong, naturally
rather than exaggerated. Same microphone, same room, one sitting, same pace and volume in
both takes. GOP moves with the microphone (handoff trap 5), so changing device between
takes invalidates the comparison.

| file | say this |
|---|---|
| `p1_clean` | I **think there** is a **very** good reason to **zip** the file before we send it. |
| `p1_broken` | I **sink dare** is a **berry** good reason to **sip** the file before we send it. |
| `p2_clean` | At the **shop** on the **hill** I saw a **jet** fly past. |
| `p2_broken` | At the **chop** on the **ill** I saw a **yet** fly past. |
| `p3_clean` | The **ship** was in **bad** shape, so we could not **speak** to the crew. |
| `p3_broken` | The **sheep** was in **bed** shape, so we could not **es peak** to the crew. |

### Convert to 16 kHz mono

`afconvert` is built into macOS; no ffmpeg needed. Adjust the extension for whatever your
recorder wrote — the conversion matters regardless, because sample rate and channel count
must be 16 kHz mono.

```bash
for f in eval/golden/pron/raw/*.m4a; do
  b=$(basename "$f" .m4a)
  afconvert -f WAVE -d LEI16@16000 -c 1 "$f" "eval/golden/pron/$b.wav"
done
```

### Register them

Replace `"pairs": []` in `manifest.json` with:

```json
"pairs": [
  {"clean": "p1_clean.wav", "broken": "p1_broken.wav",
   "text": "I think there is a very good reason to zip the file before we send it."},
  {"clean": "p2_clean.wav", "broken": "p2_broken.wav",
   "text": "At the shop on the hill I saw a jet fly past."},
  {"clean": "p3_clean.wav", "broken": "p3_broken.wav",
   "text": "The ship was in bad shape, so we could not speak to the crew."}
]
```

`text` is the **clean** reference both times. That is the whole method: the broken take is
scored against the words it was *supposed* to say, which is exactly the situation a learner
is in.

Then `make pron-golden` — `test_broken_readings_score_worse_than_clean_ones` stops skipping.

### Read the result before believing it

If the clean and broken takes decode to the same phone string, the takes are not actually
different and everything downstream is meaningless. **That is exactly how the m0 TTS
attempt failed** (§3 below), and it is why the first thing to check is whether the two
recordings differ at all, not whether the score looks good.

Expect the vowel contrasts — `ship`/`sheep`, `bad`/`bed` — to be the weakest. That held on
the native-speaker probe too, and it is the reason per-phone thresholds are needed.

### Do not synthesise them

Not because TTS is unusable in general — good neural TTS decodes cleanly through this
acoustic model, and m0 verified that (Chatterbox output decoded `θ` correctly in *three*
and *thirty*). Two reasons that do hold:

1. **macOS `say` specifically is degenerate here.** m0's first attempt planted ten
   substitutions in `say` output and scored 3/10. Three checks showed the instrument, not
   the method, was broken: `p1_clean` and `p1_bad` decoded to an *identical* phone string
   despite different waveforms and different MD5s; in isolation the model heard
   `say("think")` as `s iɛ5 ŋ`, getting the /θ/–/s/ contrast wrong in **both** directions;
   and `say -v Alex` and `say -v Samantha` produced byte-identical output, so the
   experiment never varied the speaker it claimed to vary.
2. **TTS substitutions are categorical; learner errors are gradient.** Synthetic pairs
   would test the easy case while appearing to pass, and a cloned voice gives no ground
   truth on which phones are actually wrong.

Handoff D13 and §9 trap 8.

## The audio is not committed

Unlike `eval/golden/asr`, which commits ten `.flac` files, **nothing here is in git.**
`.gitignore` covers `*.wav`, which is trap 4 doing its job: recordings of somebody's voice
must never be able to appear in `git status`. So `fetch.py` is not an audit tool here, it
is the way the file gets onto a machine at all, and the pairs — once recorded — stay
local to whoever recorded them.

```bash
python3 eval/golden/pron/fetch.py
```

`manifest.json` records the sha256, so a re-run is verifiable even though the bytes are
not versioned.
