"""What a number word is worth, so that two spellings of one number are one number.

A take is compared with its script word by word, and the recogniser writes numbers as
digits however they were said. "eleven" against "11" is not a mistake anybody made, and
counting it as one tells a speaker they got a figure wrong that they said correctly.

**One word at a time, deliberately.** The alignment pairs single tokens, so "2026"
against "twenty twenty-six" is one word against two and the pairing already says so.
Nothing here tries to read a number out of several words, and a table that pretended to
would be wrong in a way that is hard to see.

The evaluation harness keeps its own list of these words, for a different question — does
a reply name any figure at all — and `tests/test_fidelity_kinds.py` asserts the two still
agree about which words are numbers. The harness must not import from the application it
measures, so one table cannot serve both; a test that fails when they drift is what
stands in for that.
"""

from __future__ import annotations

# Cardinals to twenty, then the tens, then the two multipliers a spoken figure uses.
# Ordinals are here because a date is a figure: "the fourth of March" against "the 4th".
NUMBER_WORDS: dict[str, int] = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
    "hundred": 100,
    "thousand": 1000,
    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,
    "fifth": 5,
    "sixth": 6,
    "seventh": 7,
    "eighth": 8,
    "ninth": 9,
    "tenth": 10,
    "eleventh": 11,
    "twelfth": 12,
}

_ORDINAL_MARKS = ("st", "nd", "rd", "th")


def value_of(token: str) -> int | None:
    """What one word is worth as a number, or None when it is not one.

    Digits and number words both, with a written ordinal's mark taken off, so "4th" and
    "fourth" are the same four. Anything else — a word, a year with a letter in it, an
    empty string — is not a number, and saying so is the whole point: the caller uses
    None to mean "these two are not the same figure" rather than "these two differ".
    """
    word = token.strip().lower()
    if not word:
        return None
    if word in NUMBER_WORDS:
        return NUMBER_WORDS[word]

    digits = word[:-2] if word[-2:] in _ORDINAL_MARKS else word
    return int(digits) if digits.isdigit() else None
