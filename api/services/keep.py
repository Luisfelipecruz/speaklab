"""The keep check: what a version must carry over from what was said, and what it lost.

A language model rewriting a person's words can drop a fact while the sentence still reads
well, and the person pasting it would not see the hole. So each version is compared with
its source, by plain code, for the things that cannot be paraphrased:

- numbers written in digits, compared by their digit groups — 1.250 and 1,250 are the same
  number, 9:30 is not 9:00, and 14 is kept in "the 14th";
- links, e-mail addresses and @handles, as written;
- capitalised words that do not open a sentence, which are names; and a name that opens
  one ("Laura, te escribo…") once it is known from elsewhere.

Words are compared without case or accents, since Dubái is Dubai in English. What is
missing is reported, and the version is never changed or swapped for another: the panel
names it and the person decides.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Iterable

_TLDS = (
    "com|org|net|io|dev|co|app|ai|gov|edu|me|info|biz|es|mx|ar|cl|pe|uk|us|ae|ca|de|fr|it|"
    "br|xyz|tech|site|page|cloud|ly|to|gg|tv|so|sh"
)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_LINK = re.compile(
    rf"(?:https?://|www\.)[^\s<>\"'«»]+"
    rf"|(?<![\w@.])(?:[\w-]+\.)+(?:{_TLDS})(?![\w-])(?:/[^\s<>\"'«»]*)?",
    re.IGNORECASE,
)
_HANDLE = re.compile(r"(?<![\w@./])@[A-Za-z0-9_](?:[\w.-]*\w)?")
_NUMBER = re.compile(r"\d+(?:[.,:/-]\d+)*")
_WORD = re.compile(r"[^\W\d_](?:[\w'’-]*[^\W_])?")
# English's capital I, which is not a name.
_PRONOUN = re.compile(r"I(?:['’](?:m|ll|ve|d))?")
_TRAILING = ".,;:!?)]}\"'»”’"
_OPENERS = " \t\"'«“‘([¿¡"
_STOPS = ".!?¿¡:;\n…"


def fold(text: str) -> str:
    """Lower case, no accents, single spaces."""
    decomposed = unicodedata.normalize("NFKD", text)
    bare = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(bare.casefold().split())


def _blank(text: str, spans: list[tuple[int, int]]) -> str:
    chars = list(text)
    for start, end in spans:
        chars[start:end] = " " * (end - start)
    return "".join(chars)


def _opens_sentence(text: str, start: int) -> bool:
    i = start - 1
    while i >= 0 and text[i] in _OPENERS:
        i -= 1
    return i < 0 or text[i] in _STOPS


def _digit_groups(text: str) -> list[tuple[str, ...]]:
    return [tuple(re.findall(r"\d+", m.group())) for m in _NUMBER.finditer(text)]


def kept_items(text: str, known: Iterable[str] = ()) -> dict[str, list]:
    """Everything in `text` that a version of it must keep, by kind."""
    found: dict[str, list] = {
        "emails": [],
        "links": [],
        "handles": [],
        "numbers": [],
        "names": [],
    }
    spans: list[tuple[int, int]] = []
    for pattern, kind in ((_EMAIL, "emails"), (_LINK, "links"), (_HANDLE, "handles")):
        for match in pattern.finditer(_blank(text, spans)):
            item = (
                match.group().rstrip(_TRAILING) if kind != "handles" else match.group()
            )
            found[kind].append(item)
            # The item alone: a full stop after a link still ends its sentence.
            spans.append((match.start(), match.start() + len(item)))
    rest = _blank(text, spans)
    found["numbers"] = [m.group() for m in _NUMBER.finditer(rest)]
    names = {fold(name) for name in known}
    for match in _WORD.finditer(rest):
        word = match.group()
        if not word[0].isupper() or _PRONOUN.fullmatch(word):
            continue
        if _opens_sentence(rest, match.start()) and fold(word) not in names:
            continue
        found["names"].append(word)
    return found


def names_in(text: str) -> list[str]:
    """The capitalised words inside a sentence: the names a text teaches the check."""
    return kept_items(text)["names"]


def _contains(groups: tuple[str, ...], candidate: tuple[str, ...]) -> bool:
    n = len(groups)
    return any(candidate[i : i + n] == groups for i in range(len(candidate) - n + 1))


def missing(source: str, version: str, known: Iterable[str] = ()) -> list[str]:
    """What `version` dropped of what `source` must keep, written as in the source."""
    wanted = kept_items(source, known)
    folded = fold(version)
    dropped: list[str] = []
    for kind in ("emails", "links", "handles"):
        dropped += [item for item in wanted[kind] if fold(item) not in folded]
    # Names and numbers outside the links and addresses: acme.io does not keep Acme.
    spans = [m.span() for p in (_EMAIL, _LINK, _HANDLE) for m in p.finditer(version)]
    rest = _blank(version, spans)
    plain = fold(rest)
    for word in wanted["names"]:
        if not re.search(rf"(?<!\w){re.escape(fold(word))}(?!\w)", plain):
            dropped.append(word)
    have = _digit_groups(rest)
    written = {}
    for number in wanted["numbers"]:
        written.setdefault(tuple(re.findall(r"\d+", number)), number)
    counts = Counter(tuple(re.findall(r"\d+", number)) for number in wanted["numbers"])
    for groups, count in counts.items():
        if sum(1 for candidate in have if _contains(groups, candidate)) < count:
            dropped.append(written[groups])
    return dropped
