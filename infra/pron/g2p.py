"""The reference text → canonical phones, grouped by the word they belong to.

Two things make this less trivial than it looks, and both were measured rather than
guessed.

**Context matters, so the whole passage is converted at once.** `g2p_en` tags parts of
speech before it looks anything up, which is how it resolves homographs. In
``in-june-the-judge`` the word *use* is a verb, and the passage converted whole gives
``Y UW1 Z``; the same word converted on its own gives ``Y UW1 S``, the noun. Scoring a
learner's correct /z/ against a canonical /s/ would mark right speech wrong, in a word
chosen for that passage precisely because it is a /dʒ/-/j/ contrast. So per-word G2P is
not a simplification of this module, it is a different and worse answer.

**Which means the two sequences have to be re-aligned afterwards**, because `g2p_en`
returns one flat list for the whole text and the result has to be attributed back to
individual words for the heatmap to tint anything. That is what desyncs, and it desynced
here:

    The spike's rule — a surface word is a whitespace token with ``.,!?;:`` stripped —
    fails on **2 of the 12 seeded passages**. Both contain a standalone em dash, which
    survives that strip, counts as a word, and produces no phones. 79 surface words
    against 78 phone groups, and `spike/gop.py` raises ValueError on it. Read-aloud
    would have been broken on a sixth of the shipped corpus, and the failure would have
    looked like a bug in alignment rather than in tokenisation.

The rule here is instead: **a surface word is a token containing at least one letter.**
That is the same rule `g2p_en` effectively applies when it decides whether to emit
phones, which is why the two now agree — 12 of 12 passages, 3049 phones, verified by
``api/tests/test_g2p.py`` over the real seed file rather than over a fixture that cannot
notice the corpus changing.

The desync check is kept anyway. It is not defensive clutter: passages are authored
content and the corpus will grow, and there are constructs that genuinely split — ``$5``
becomes two phone groups for one token, ``Dr.`` becomes ``D R AY1 V`` plus a stray group.
When it fires, the caller turns it into a 422 that names the passage, which is a bug
report; scoring a misaligned passage would be a screen full of confident nonsense.
"""

from __future__ import annotations

import re
from typing import Iterable

# g2p_en emits ARPAbet with an optional stress digit, plus " " between words and raw
# punctuation characters for everything else. This is the filter that keeps phones.
ARPA_RE = re.compile(r"^[A-Z]{1,3}[0-2]?$")

# A token is a word if it contains a letter. See the module docstring — this one line is
# the fix for the em-dash desync, and the reason it is a search for a letter rather than
# a longer strip set is that a strip set is a list of the punctuation somebody thought of.
HAS_LETTER = re.compile(r"[A-Za-z]")

# Stripped only to recover the surface spelling for display; it plays no part in the
# count. Quotes and dashes are included because the word shown under the heatmap should
# be *worth* rather than *"worth*.
EDGE_PUNCTUATION = ".,!?;:—–-\"'“”‘’()[]"


class TextAlignmentError(ValueError):
    """The words and the phone groups did not line up. Never scored, always reported."""


class Word:
    """One word of the reference text and the canonical phones it should be read as."""

    __slots__ = ("index", "surface", "phones")

    def __init__(self, index: int, surface: str, phones: list[str]) -> None:
        self.index = index
        self.surface = surface
        self.phones = phones

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return f"Word({self.index}, {self.surface!r}, {self.phones})"


def surface_words(text: str) -> list[str]:
    """The words a reader would say, in order, lowercased and stripped of edge marks."""
    out = []
    for token in text.split():
        stripped = token.strip(EDGE_PUNCTUATION).lower()
        if HAS_LETTER.search(stripped):
            out.append(stripped)
    return out


def phone_groups(tokens: Iterable[str]) -> list[list[str]]:
    """g2p_en's flat output → one phone list per word.

    A space closes the current group. Punctuation tokens are dropped rather than closing
    one, because ``"worth ,"`` is a single word followed by a mark, not two words.
    """
    groups: list[list[str]] = []
    buffer: list[str] = []
    for token in tokens:
        if token == " ":
            if buffer:
                groups.append(buffer)
                buffer = []
        elif ARPA_RE.match(token):
            buffer.append(token)
    if buffer:
        groups.append(buffer)
    return groups


def words_with_phones(text: str, g2p) -> list[Word]:
    """The passage, as words paired with the phones they are supposed to contain.

    `g2p` is passed in rather than constructed here: building a `G2p` loads the CMU
    dictionary and the tagger, which is work to do once per process, not once per
    request.
    """
    groups = phone_groups(g2p(text))
    surface = surface_words(text)

    if len(surface) != len(groups):
        raise TextAlignmentError(
            f"word/phone desync: {len(surface)} words in the text but {len(groups)} "
            f"phone groups from G2P. The passage contains something the tokeniser and "
            f"g2p_en disagree about — a number, an abbreviation, or a symbol. The text "
            f"begins {text[:60]!r}."
        )

    return [Word(i, surface[i], groups[i]) for i in range(len(surface))]


def flatten(words: list[Word]) -> list[tuple[int, str, int, str]]:
    """``[(word_idx, surface, phone_idx, phone), ...]`` — one entry per phone to score.

    This is the order the aligner's targets are built in and the order its output is read
    back in, so the two cannot drift: there is exactly one place that decides what
    position *n* means.
    """
    return [
        (word.index, word.surface, phone_index, phone)
        for word in words
        for phone_index, phone in enumerate(word.phones)
    ]
