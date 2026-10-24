"""Every sound this system scores, said in words a speaker can act on.

`/IY/` is a code. It is the right code — it is what the acoustic model thinks in and what
every table in this project is keyed by — and it is useless to the person who recorded
the take, who wants to know which sound in their own mouth to pay attention to. So each
of the thirty-nine gets a name: *the vowel in "see"*, *the "th" in "this"*.

**Hand-written, and validated against the inventory at import.** A name that is quietly
missing would be a sound the screen could not talk about, and a name for a phone that
does not exist is a table drifting away from the model. The check is the same one
`infra/pron/phone_map.py` makes about its own table and for the same reason: a
pronunciation table nobody verifies is a pronunciation claim nobody can check.

**No model writes these.** They are the product's own words about English, chosen so the
example word contains the sound obviously and is one anybody reading this has said.
"""

from __future__ import annotations

import re

from models.common import ARPABET_PHONES

# The example word carries the sound in the position it is most often noticed in. `Z` is
# named at the end of a word rather than the start of "zoo" on purpose: the way it goes
# wrong here is a lost plural, not a lost "zoo".
PHONE_NAMES: dict[str, str] = {
    "AA": 'the vowel in "father"',
    "AE": 'the vowel in "cat"',
    "AH": 'the vowel in "cup"',
    "AO": 'the vowel in "thought"',
    "AW": 'the vowel in "now"',
    "AY": 'the vowel in "my"',
    "B": 'the "b" in "bad"',
    "CH": 'the "ch" in "church"',
    "D": 'the "d" in "day"',
    "DH": 'the "th" in "this"',
    "EH": 'the vowel in "bed"',
    "ER": 'the vowel in "her"',
    "EY": 'the vowel in "say"',
    "F": 'the "f" in "fine"',
    "G": 'the "g" in "give"',
    "HH": 'the "h" in "home"',
    "IH": 'the vowel in "sit"',
    "IY": 'the vowel in "see"',
    "JH": 'the "j" in "jump"',
    "K": 'the "k" in "keep"',
    "L": 'the "l" in "look"',
    "M": 'the "m" in "make"',
    "N": 'the "n" in "no"',
    "NG": 'the "ng" at the end of "sing"',
    "OW": 'the vowel in "go"',
    "OY": 'the vowel in "boy"',
    "P": 'the "p" in "put"',
    "R": 'the "r" in "red"',
    "S": 'the "s" in "sun"',
    "SH": 'the "sh" in "she"',
    "T": 'the "t" in "take"',
    "TH": 'the "th" in "think"',
    "UH": 'the vowel in "book"',
    "UW": 'the vowel in "food"',
    "V": 'the "v" in "very"',
    "W": 'the "w" in "we"',
    "Y": 'the "y" in "yes"',
    "Z": 'the "z" at the end of "is"',
    "ZH": 'the "s" in "measure"',
}

# The word each name ends on, which is the word a speaker can be offered to hear. The
# pattern anchors on the trailing quoted word rather than on `in "…"`, because two names
# do not use that phrasing — `NG` is at the end of "sing" and `Z` is at the end of "is" —
# and a pattern that assumed it would drop exactly those two silently.
_EXAMPLE = re.compile(r'"([a-z\']+)"\s*$')

EXAMPLE_WORDS: dict[str, str] = {}
_unnamed: list[str] = []
for _phone, _name in PHONE_NAMES.items():
    _match = _EXAMPLE.search(_name)
    if _match is None:  # pragma: no cover - import-time guard
        _unnamed.append(_phone)
    else:
        EXAMPLE_WORDS[_phone] = _match.group(1)

if _unnamed:  # pragma: no cover - import-time guard
    raise RuntimeError(
        "these phone names end on no quoted word, so no sound can be offered to hear: "
        f"{_unnamed}"
    )

_missing = sorted(set(ARPABET_PHONES) - set(PHONE_NAMES))
_extra = sorted(set(PHONE_NAMES) - set(ARPABET_PHONES))
if _missing or _extra:  # pragma: no cover - import-time guard
    raise RuntimeError(
        "the phone names and the phone inventory disagree: "
        f"unnamed {_missing}, not a phone {_extra}"
    )


def name_of(phone: str) -> str:
    """What to call one sound, stress folded away, or the code itself if it is unknown.

    An unknown phone falls back to `/XX/` rather than raising: a name is something to
    read, and a take that has already been scored should not fail to render because a
    future model emitted a symbol this table has not met. The import-time check above is
    what keeps that from happening silently for the phones that exist now.
    """
    folded = phone.rstrip("012").upper()
    return PHONE_NAMES.get(folded, f"/{folded}/")


def example_word_of(phone: str) -> str | None:
    """The word that carries this sound, stress folded away, or None if it is unknown.

    None rather than a fallback: the caller is deciding whether there is a word to
    offer, and inventing one would put a button on a sound this table cannot speak.
    """
    return EXAMPLE_WORDS.get(phone.rstrip("012").upper())
