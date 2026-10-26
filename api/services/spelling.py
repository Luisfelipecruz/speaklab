"""Spelling, for English the person wrote: a dictionary, never a model.

The speech detector leaves spelling alone, because its input is the recogniser's and the
speaker never spelled anything. Typed and copied English is different: a misspelling is
the writer's, and it is found here with `symspellpy` and its English frequency list
(82 765 words, pinned with the package), within two edits.

**What it never checks**, because a dictionary of common words would "correct" it:
- links, e-mail addresses, @handles, and anything in backticks or double quotes;
- words with a digit or a letter outside English's alphabet;
- capitalised words inside a sentence, which are names, and acronyms and mixed case
  (API, GitHub);
- a capitalised word that opens a sentence and is a name the person has used before;
- words of one or two letters.

Words of software and office work that the list lacks are added to it from
`services/words/technical.txt`, so `backend` is not corrected to `backed`.

**Which correction, when several are as close.** The frequency list alone would pick the
commonest word, turning *realy* into *real* and *wich* into *with*. The commonest typing
mistakes are a letter left out and two letters swapped, so a correction that adds a letter
or swaps two is preferred to one that removes a letter, and that to one that changes a
letter; frequency decides within each, which keeps *teh* from becoming *tech*. A handful
of words typed without their apostrophe, and *alot*, are corrected from a table.
"""

from __future__ import annotations

import importlib.resources
import re
from collections.abc import Iterable
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from symspellpy import SymSpell, Verbosity

MAX_DISTANCE = 2
MIN_LENGTH = 3
CONFIDENCE = 1.0

TECHNICAL = Path(__file__).parent / "words" / "technical.txt"

# Typed without the apostrophe, or run together: the correction is not in doubt, and the
# dictionary's nearest word is the wrong one (dont to done, alot to allot).
TABLE = {
    "alot": "a lot",
    "arent": "aren't",
    "cant": "can't",
    "couldnt": "couldn't",
    "didnt": "didn't",
    "doesnt": "doesn't",
    "dont": "don't",
    "hadnt": "hadn't",
    "hasnt": "hasn't",
    "havent": "haven't",
    "im": "I'm",
    "isnt": "isn't",
    "ive": "I've",
    "shouldnt": "shouldn't",
    "thats": "that's",
    "theres": "there's",
    "theyre": "they're",
    "wasnt": "wasn't",
    "werent": "weren't",
    "whats": "what's",
    "wont": "won't",
    "wouldnt": "wouldn't",
    "youre": "you're",
}

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_LINK = re.compile(
    r"(?:https?://|www\.)\S+|\b(?:[\w-]+\.)+[a-z]{2,}/\S*", re.IGNORECASE
)
_HANDLE = re.compile(r"(?<![\w@./])@\w[\w.-]*")
_QUOTED = re.compile(r"`[^`]*`|\"[^\"]*\"|“[^”]*”")
_TOKEN = re.compile(r"[^\W_]+(?:['’][^\W_]+)*")
_STOPS = ".!?:;\n…"
_OPENERS = " \t\"'“‘([¿¡"


@dataclass(frozen=True)
class Misspelling:
    """One word the dictionary does not know, and the word it most likely meant."""

    span_start: int
    span_end: int
    original: str
    correction: str


@cache
def dictionary() -> SymSpell:
    """The frequency list and the technical words, loaded once: about a second, 125 MB."""
    spell = SymSpell(max_dictionary_edit_distance=MAX_DISTANCE, prefix_length=7)
    words = (
        importlib.resources.files("symspellpy") / "frequency_dictionary_en_82_765.txt"
    )
    with importlib.resources.as_file(words) as path:
        spell.load_dictionary(str(path), term_index=0, count_index=1)
    for line in TECHNICAL.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            spell.create_dictionary_entry(line.strip(), 1)
    return spell


def _masked(text: str) -> str:
    """The text with everything that is never checked blanked out, offsets kept."""
    chars = list(text)
    for pattern in (_EMAIL, _LINK, _HANDLE, _QUOTED):
        for match in pattern.finditer("".join(chars)):
            for i in range(*match.span()):
                chars[i] = " "
    return "".join(chars)


def _opens_sentence(text: str, start: int) -> bool:
    i = start - 1
    while i >= 0 and text[i] in _OPENERS:
        i -= 1
    return i < 0 or text[i] in _STOPS


def _kind(word: str, candidate: str) -> int:
    """How likely a one-edit correction is as a typing mistake undone, most likely first:
    a letter added or two swapped, then a letter removed, then a letter changed."""
    if len(candidate) == len(word) + 1:
        return 0
    if len(candidate) == len(word):
        diffs = [i for i, (a, b) in enumerate(zip(word, candidate)) if a != b]
        swapped = (
            len(diffs) == 2
            and diffs[1] == diffs[0] + 1
            and word[diffs[0]] == candidate[diffs[1]]
            and word[diffs[1]] == candidate[diffs[0]]
        )
        return 0 if swapped else 2
    if len(candidate) == len(word) - 1:
        return 1
    return 3


def suggest(word: str) -> str | None:
    """The correction for one lower-case word, or None when it is known or unknowable."""
    found = dictionary().lookup(
        word, Verbosity.CLOSEST, max_edit_distance=MAX_DISTANCE, include_unknown=False
    )
    if not found or found[0].distance == 0:
        return None
    best = min(
        found,
        key=lambda s: (_kind(word, s.term) if s.distance == 1 else 3, -s.count, s.term),
    )
    return best.term


def check(text: str, known: Iterable[str] = ()) -> list[Misspelling]:
    """Every misspelling in `text`, in order, with where it is."""
    names = {name.casefold() for name in known}
    masked = _masked(text)
    found: list[Misspelling] = []
    for match in _TOKEN.finditer(masked):
        stem = re.sub(r"['’]s$", "", match.group())
        letters = stem.replace("'", "").replace("’", "")
        if not letters.isascii() or not letters.isalpha():
            continue
        if any(ch.isupper() for ch in stem[1:]):
            continue
        if stem[0].isupper() and (
            not _opens_sentence(masked, match.start()) or stem.casefold() in names
        ):
            continue
        lowered = stem.casefold().replace("’", "'")
        if lowered in TABLE:
            correction = TABLE[lowered]
        elif len(letters) < MIN_LENGTH or "'" in lowered:
            # Too short to guess at, or a contraction, which the list knows or not.
            continue
        else:
            correction = suggest(lowered)
        if correction is None:
            continue
        if stem[0].isupper():
            correction = correction[0].upper() + correction[1:]
        found.append(
            Misspelling(
                span_start=match.start(),
                span_end=match.start() + len(stem),
                original=text[match.start() : match.start() + len(stem)],
                correction=correction,
            )
        )
    return found
