"""Spanish or English: which language a typed or copied text is in, by plain code.

What was said is decided by the recogniser, which hears the language; what was typed is
decided here. The share of the text's words found in a list of about 300 common words of
each language, kept in `services/words/`: the larger share wins, and a tie — a text with
no common word of either, such as a name or "OK" — goes to the account's own language.
Accents are folded away first, so a text typed without them counts the same.

**No model, and no library.** The decision is a count anyone can repeat by hand, it is
what decides whether a text is translated or checked, and the person can overturn it with
the panel's switch. A language for which no list exists here is told from English by the
English share alone: half or more of its words common English words.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import cache
from pathlib import Path

WORDS = Path(__file__).parent / "words"

# The share of common English words above which a text in a language with no list of its
# own is taken for English.
ENGLISH_WITHOUT_A_LIST = 0.5

_WORD = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*")


def fold(text: str) -> str:
    """Lower case, without accents, straight apostrophes."""
    decomposed = unicodedata.normalize("NFKD", text.replace("’", "'"))
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).casefold()


@cache
def common(code: str) -> frozenset[str]:
    """The list for one language, or nothing when there is none."""
    path = WORDS / f"common-{code}.txt"
    if not path.exists():
        return frozenset()
    return frozenset(
        fold(line.strip())
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    )


@dataclass(frozen=True)
class Decision:
    """The language chosen, and the counts that chose it."""

    language: str
    words: int
    shares: dict[str, float]


def words_of(text: str) -> list[str]:
    return _WORD.findall(fold(text))


def decide(text: str, account: str = "es") -> Decision:
    """English or the account's language, for a text the person typed or copied."""
    words = words_of(text)
    total = len(words) or 1
    english = sum(word in common("en") for word in words) / total
    own_list = common(account) if account != "en" else frozenset()
    if account == "en":
        return Decision("en", len(words), {"en": round(english, 3)})
    if not own_list:
        chosen = "en" if words and english >= ENGLISH_WITHOUT_A_LIST else account
        return Decision(chosen, len(words), {"en": round(english, 3)})
    own = sum(word in own_list for word in words) / total
    chosen = "en" if english > own else account
    return Decision(
        chosen, len(words), {"en": round(english, 3), account: round(own, 3)}
    )
