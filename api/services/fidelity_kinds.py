"""What kind of thing a difference between the script and the take actually is.

One number for every word that came out differently is the least useful true thing a
rehearsal can say. A dropped plural, a word the recogniser misheard, and a number it
wrote as a digit are three different events: the first is something to work on, the
second may be the microphone, and the third is not a difference at all. Counting them
together produces a figure that is correct and tells nobody what to do.

So each substitution is sorted into one of three kinds, by arithmetic and string
comparison only. No model is asked, because the answer has to be the same tomorrow and
has to be explainable to the person it is about.

- **A figure** — the same number written two ways. `services/wer.py` leaves numbers
  alone by design, which is the honest reading for a passage everybody reads, and the
  wrong one for a script somebody wrote: a speaker who says "eleven" and is transcribed
  "11" has said the word. These are excluded from the count entirely rather than shown
  in a gentler colour.
- **An ending** — the two words are the same word with something lost or gained at the
  end: a plural or third-person *-s*, an *-ing*, a past *-ed*, a comparative *-er*, or a
  contraction. A speaker whose differences are mostly endings has a different thing to
  practise from one whose words are being misheard outright, and for a Spanish-first
  speaker it is a common and fixable one.
- **A different word** — everything else, including a word the recogniser simply got
  wrong. The name says what is known: the two words are not the same. It does not claim
  the speaker mispronounced anything, because nothing here heard the audio.

A contraction counts as an ending from either side: *we're* against *are* has lost its
subject and its mark, and what is left is the ending. The alternative — calling it a
different word — would file the most regular thing in spoken English under the bin for
everything else.
"""

from __future__ import annotations

from services.numbers import value_of

FIGURE = "figure"
ENDING = "ending"
DIFFERENT_WORD = "different-word"

# What may be lost or gained at the end of a word and still leave the same word. `er` is
# here and is not a plural or a tense: a comparative loses its ending the same way, and
# it turned up in real speech ("fewer" heard as "few").
_ENDINGS = ("s", "es", "ed", "ing", "er", "'s", "'re", "'d", "'ll")

# Two words that agree for this many characters and then diverge are one word with its
# end changed, not two words. Four is long enough that "even" and "events" are the same
# word and short enough to catch the endings that matter; below it, "the" and "they"
# would be one word, which they are not.
_SHARED_STEM = 4


def classify(expected: str, heard: str) -> str:
    """`figure`, `ending` or `different-word` for one substituted word.

    Both arguments are single normalised words, as `services/wer.py` produces them:
    lower case, no punctuation but an apostrophe inside a word. The order matters only
    for reading — every rule here is symmetric, because the recogniser dropping an
    ending and the speaker dropping one are the same difference to look at.
    """
    left, right = expected.strip().lower(), heard.strip().lower()
    if not left or not right:
        return DIFFERENT_WORD

    number = value_of(left)
    if number is not None and number == value_of(right):
        return FIGURE

    if _is_ending(left, right) or _is_ending(right, left):
        return ENDING

    return DIFFERENT_WORD


def _is_ending(longer: str, shorter: str) -> bool:
    """Whether `longer` is `shorter` with an ending on it, or the two share a stem.

    A contraction is an ending on either side: the mark is the only thing an apostrophe
    can be inside a normalised word, so one word carrying it and the other not is a
    contraction gained or lost, whatever letters came with it.
    """
    if ("'" in longer) != ("'" in shorter):
        return True
    if longer.startswith(shorter) and longer[len(shorter) :] in _ENDINGS:
        return True
    return _shared_stem(longer, shorter) >= _SHARED_STEM


def _shared_stem(first: str, second: str) -> int:
    """How many characters the two words agree on from the start."""
    shared = 0
    for left, right in zip(first, second):
        if left != right:
            break
        shared += 1
    return shared
