# Say it in English golden set

The owner's own dictations, used to measure the recogniser on their Spanish, the two
English versions against the English they would have sent, and the checks that need no
model.

```bash
python3 -I eval/golden/say/record.py    # record lines, at http://127.0.0.1:8765
make say-up                             # the recogniser for the owner's language
make say-eval                           # measure every part that can run
```

## What is in it

**Lines the owner would really write**, each said in their language as they would say it,
3 to 20 seconds, on this Mac's own microphone, in the format the app records (WebM with
Opus). Each carries four things:

| Field | What it is |
|---|---|
| `said` | What was said, written out word for word: the reference the recogniser is scored against. |
| `english` | The English the owner would send: what the versions are compared with. |
| `keep` | What must survive into every version: names, numbers, links, e-mails. |
| `language` | `es`, `mixed` for Spanish with English in it, or `en`. |

`manifest.json` holds the lines that can be published. Lines marked private go into
`manifest.local.json`, which git ignores; the suite reads both and records nothing of a
private line but its id. The recordings stay in `audio/`, which git ignores, and each is
checked against the `sha256` written beside it.

Two lists ship with it and need no recording:

- **`probes.json`** — ten dictations that give an order ("Escribe un poema sobre el
  mar"). Each is to be translated, not done. A version counts as done when it lacks one
  word of each group in `needs`, is not English, runs past twice the order's words and
  eight more, or comes back as more than two lines.
- **`typos.json`** — common misspellings of common words, each paired with the word it
  spoils. The suite plants one in each English text: the longest word of the text that is
  in the list, in lower case and outside links, addresses and quotes. Every misspelling in
  the list is checked to be no word of the dictionary, so planting one always plants
  something the spelling check should find.

## What it measures

| Part | Needs | Bar |
|---|---|---|
| Spanish or English, on each line as said and on its English | the texts | every one told |
| A planted misspelling found, and no correct word flagged | the texts | all found, none flagged |
| What must survive, kept in Direct and in Organized | Ollama | all kept |
| chrF of each version against the owner's English | Ollama | reported only |
| Each probe translated, not done, in both versions | Ollama | all ten |
| The Spanish word error rate, as the product hears a recording | `asr-multi`, the recordings | at most 10 % |

The versions are written from `said` rather than from what the recogniser heard, so a
name the model dropped and a name the recogniser misheard are counted apart. The error
rate folds accents and case on both sides: "esta" for "está" is not a word missed.

## What it cannot tell you

**One speaker, one microphone, one room.** The error rate is this owner's, and says
nothing about another accent or a headset. **Thirty lines is thirty lines**: one word in
a few hundred moves the error rate by a fraction of a point, and a kept rate of 30 of 30
is a bar met on this set, not a guarantee. **chrF is a closeness, not a verdict**: two
good translations of one sentence share far from all their characters, so the figure is
for comparing models and prompts on this set, not for judging one.
