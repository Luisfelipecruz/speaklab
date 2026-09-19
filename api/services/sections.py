"""Splitting a script into pieces to rehearse. Deterministic, and no model in it.

The split is shown to the writer before anything is saved, and a suggestion they have to
check is only worth checking if it is the same suggestion every time. A model asked to
"divide this into sections" gives a different answer on Tuesday, cannot say why, and
would be the one piece of this feature that could quietly reword somebody's talk.

So: blank lines first, because a writer who left one meant it. A paragraph over the cap
is cut at sentence ends, greedily, which for pieces that have to stay in order is also
the fewest pieces that fit. A sentence longer than the cap on its own is left whole —
there is nowhere to cut it that is not inside a sentence, and a section that stops
mid-clause is worse to rehearse than a long one.

Nothing here rewrites a word. Runs of whitespace inside a paragraph collapse to single
spaces, which is wrapping rather than content; the words, in order, come out exactly as
they went in, and `create` in `services/rehearsals.py` checks that against the script it
was given.
"""

from __future__ import annotations

import re

# A sentence ends at one of these followed by whitespace, or at the end of the text. The
# closing quote or bracket belongs to the sentence it closes, so it is taken with it.
_SENTENCE_END = re.compile(r"[.!?]['\"”’)\]]*(?=\s|$)")

# One or more blank lines. What a writer uses to mean "new part".
_PARAGRAPH = re.compile(r"\n\s*\n")


def word_count(text: str) -> int:
    """Whitespace-separated tokens. The same count everything else here uses."""
    return len(text.split())


def sentence_spans(text: str) -> list[tuple[int, int]]:
    """Character spans of the sentences in a piece of text, in order.

    Not `services.structure.sentences`, which runs spaCy: this is called while a request
    is held open, on text nobody has recorded yet, and it needs punctuation rather than
    grammar. Text with no sentence mark in it is one span.
    """
    spans: list[tuple[int, int]] = []
    start = 0
    for match in _SENTENCE_END.finditer(text):
        end = match.end()
        if text[start:end].strip():
            spans.append((start, end))
        start = end
    if text[start:].strip():
        spans.append((start, len(text)))
    return spans


def split_script(script: str, max_words: int, min_words: int) -> list[str]:
    """A script to the sections it will be rehearsed in.

    A piece shorter than `min_words` is joined to the piece before it, unless that would
    take the pair over `max_words` — a short section is a smaller cost than a section too
    long to score in one go, and the writer can move the boundary themselves either way.
    """
    pieces: list[str] = []
    for paragraph in _PARAGRAPH.split(script):
        text = " ".join(paragraph.split())
        if not text:
            continue
        pieces.extend(_fit(text, max_words))

    return _join_short_pieces(pieces, max_words, min_words)


def _fit(text: str, max_words: int) -> list[str]:
    """One paragraph, cut at sentence ends into pieces that fit. Greedy is fewest."""
    if word_count(text) <= max_words:
        return [text]

    sentences = [text[start:end].strip() for start, end in sentence_spans(text)]
    pieces: list[str] = []
    current: list[str] = []
    counted = 0

    for sentence in sentences:
        words = word_count(sentence)
        if current and counted + words > max_words:
            pieces.append(" ".join(current))
            current, counted = [], 0
        current.append(sentence)
        counted += words

    if current:
        pieces.append(" ".join(current))
    return pieces


def _join_short_pieces(pieces: list[str], max_words: int, min_words: int) -> list[str]:
    joined: list[str] = []
    for piece in pieces:
        if (
            joined
            and word_count(piece) < min_words
            and word_count(joined[-1]) + word_count(piece) <= max_words
        ):
            joined[-1] = f"{joined[-1]} {piece}"
        else:
            joined.append(piece)
    return joined


def splittable(text: str) -> bool:
    """Whether this text has anywhere to be cut that is not inside a sentence.

    A section over the cap is refused unless this is false: one long sentence has no
    boundary to use, and refusing it would refuse the script rather than the split.
    """
    return len(sentence_spans(text)) > 1
