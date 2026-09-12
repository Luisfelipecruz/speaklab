"""How a spoken answer is built, counted from its transcript.

Everything here is deterministic: a closed list of signposts, the dependency parse to decide
the words that have another use, and arithmetic over punctuation. No model reads the
answer to decide how well it was built — the same transcript gives the same counts on
every run, which is what lets them sit beside each other from one week to the next.

**Signposts, by what they do.** Five functions: a *reason* (a cause, a purpose or a
consequence), an *example*, a *sequence* step, a *contrast*, and a *close* that sums up.
Most signposts are phrases that mean one thing wherever they appear — *for example*,
*however*, *to sum up* — and are matched as phrases. A few words have a second use, and
the parse decides:

- *so* joining a result to its cause counts; *so slow*, *so has the team*, *I think so*
  and *or so* do not, and *so* opening an answer is how people start talking. *So*
  opening the last sentence sums up, and counts as a close.
- *since* counts as a reason when it introduces a clause and the main clause is not a
  perfect: *since it was late, we stopped*, but not *we have had two outages since we
  moved*, and never *since 2019*.
- *then* is a step, except in *if … then*, *back then* and *until then*.
- *first*, *second*, *next* and *last* are steps at the start of a clause, or before
  *step*, *thing*, *reason* or *point* — not *my first job*, *next week* or *test it first*.
- *but*, *yet*, *while* and *though* count only in their contrasting use.
- *like* is never counted. "Tools like Jira" gives an example and "it looks like rain"
  does not, and nothing in a parse separates them reliably enough to be worth the
  false ones.

**Repeats and restarts are counted from what the recogniser wrote down.** A repeat is a
word or a run of up to four words said twice in a row. A restart is a phrase broken off at
a pause and begun again: it ends on a word that cannot end a phrase — *the*, *to*, *was*
— or its verb comes back straight after the pause, as in *Lee was, he was honest*. A
recogniser trained on clean transcripts may leave out the first attempt entirely, and
then there is nothing here to count; whether it does is measured, not assumed.

**Sentences are the recogniser's punctuation.** Whisper puts in full stops where the voice
fell, and words per sentence is words over those. It is a property of the transcript, and
of the speaker only as far as the recogniser heard where they stopped.

**Counted is not judged.** More signposts is not a better answer — counting *because*
rewards saying it — so these are shown as what the answer contains, and the page never
calls a higher number better.

Only the measures in `SHOWN` reach a learner. Each was scored against answers labelled by
hand and held out from the writing of this code, and a measure below its bar is counted
and stored but not shown.
"""

from __future__ import annotations

import re
import threading
from dataclasses import asdict, dataclass

from services.fluency import FILLERS
from services.grammar import load, parse
from services.wer import normalise

REASON = "reason"
EXAMPLE = "example"
SEQUENCE = "sequence"
CONTRAST = "contrast"
CLOSE = "close"
FUNCTIONS: tuple[str, ...] = (REASON, EXAMPLE, SEQUENCE, CONTRAST, CLOSE)

REPEAT = "repeat"
RESTART = "restart"
SENTENCES = "sentences"

# The bar a measure has to clear on the held-out answers before a learner sees it:
# precision, recall, and enough marked instances for the two to mean something.
MIN_PRECISION = 0.90
MIN_RECALL = 0.75
MIN_INSTANCES = 10

# The measures that cleared it, as measured. A measure left out is still counted and
# stored, so it can be shown the day it clears the bar, but no page shows it.
#
# Restarts are left out. The recogniser writes them down, but the counter finds them
# at 0.64 precision and 0.64 recall on the held-out answers: it misses a phrase broken
# off on a noun or a verb that does not come back, and it takes a clause-final
# preposition or "all in all" for a phrase left hanging. Sentences are shown because the
# recogniser's sentence count was within one of the speaker's in most answers said aloud.
SHOWN: frozenset[str] = frozenset(FUNCTIONS + (REPEAT, SENTENCES))

# Signposts that mean the same thing wherever they appear. Written out as a person says
# them; tokenised the way the parser tokenises the transcript, on first use.
PHRASES: dict[str, tuple[str, ...]] = {
    REASON: (
        "because of",
        "because",
        "so that",
        "that's why",
        "that is why",
        "which is why",
        "this is why",
        "as a result",
        "therefore",
        "thus",
        "hence",
        "due to",
        "in order to",
        "that way",
    ),
    EXAMPLE: (
        "for example",
        "for instance",
        "such as",
        "e.g.",
        "to give you an example",
        "to give an example",
        "as an example",
    ),
    SEQUENCE: (
        "first of all",
        "to start with",
        "to begin with",
        "after that",
        "after this",
        "afterwards",
        "afterward",
        "before that",
        "firstly",
        "secondly",
        "thirdly",
        "lastly",
        "finally",
        "at the end",
    ),
    CONTRAST: (
        "on the other hand",
        "on the one hand",
        "on one hand",
        "on the other side",
        "on one side",
        "even though",
        "even if",
        "having said that",
        "that said",
        "in contrast",
        "on the contrary",
        "in spite of",
        "instead of",
        "instead",
        "however",
        "although",
        "whereas",
        "nevertheless",
        "nonetheless",
        "despite",
    ),
    CLOSE: (
        "to sum up",
        "to sum it up",
        "in summary",
        "to summarise",
        "to summarize",
        "in short",
        "in brief",
        "all in all",
        "in conclusion",
        "to conclude",
        "long story short",
        "the bottom line",
        "bottom line",
        "in a nutshell",
        "in the end",
        "all things considered",
        "overall",
    ),
}

# Words before an answer's first real word that are not yet the answer: "Okay, so…".
_OPENERS = frozenset(
    {"okay", "ok", "right", "well", "yeah", "yes", "alright", "oh", "now", "anyway"}
    | {"and", "so"}
    | FILLERS
)

# Nouns an ordinal names a step with: "the first step", "the last point".
_STEP_NOUNS = frozenset(
    {
        "step",
        "thing",
        "reason",
        "point",
        "part",
        "stage",
        "problem",
        "issue",
        "question",
    }
)
_ORDINALS = frozenset({"first", "second", "third", "fourth", "next", "last"})

# Before "then", these make it a time and not a step: "until then", "back then".
_TIME_BEFORE_THEN = frozenset(
    {"until", "till", "by", "since", "from", "back", "before", "even"}
)

# The same word twice in a row with no pause between is grammatical for these: "had
# had", "that that", "what it is is", "very very". With a comma between, it is a repeat.
_GRAMMATICAL_DOUBLES = frozenset(
    {"had", "that", "is", "do", "very", "really", "much", "many", "so", "no", "yes"}
)

# Where a voice breaks off. A comma is how the recogniser writes most of them.
_BREAKS = frozenset({",", "-", "--", "—", "–", "...", "…", ";"})

# Words that only ever stand before a noun, whatever the parser calls them: a phrase that
# stops on one was abandoned. And degree words, which stop nothing: "it's very, it's".
_ONLY_BEFORE_A_NOUN = frozenset(
    {
        "the",
        "a",
        "an",
        "no",
        "every",
        "each",
        "my",
        "your",
        "our",
        "their",
        "his",
        "its",
    }
)
_DEGREE = frozenset({"very", "really", "quite", "pretty", "rather", "extremely"})

_SENTENCE_END = re.compile(r"[.?!]+(?=\s|$)")

_phrase_lock = threading.Lock()
_phrase_table: dict[tuple[str, ...], str] | None = None


@dataclass(frozen=True)
class Found:
    """One thing counted, where it is in the transcript, and what it is."""

    kind: str
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class Structure:
    """How one answer is built. Counts only; nothing here says whether it is good."""

    words: int
    sentences: int
    words_per_sentence: float | None
    longest_sentence: int | None
    signposts: dict[str, int]
    repeats: int
    restarts: int
    found: tuple[Found, ...]

    def as_dict(self) -> dict:
        return asdict(self)


def words_of(text: str) -> list[str]:
    """The words of a stretch of transcript, as word error rate counts them, no fillers."""
    return [word for word in normalise(text) if word not in FILLERS]


def sentences(text: str) -> list[tuple[int, int]]:
    """Where each sentence is, as the recogniser punctuated it.

    A full stop, question mark or exclamation mark followed by a space or the end closes
    a sentence; one inside a number does not. A stretch with no words in it — a stray
    "Um." — is not a sentence.
    """
    text = text or ""
    spans: list[tuple[int, int]] = []
    start = 0
    for end in _SENTENCE_END.finditer(text):
        spans.append((start, end.end()))
        start = end.end()
    if start < len(text):
        spans.append((start, len(text)))
    trimmed = []
    for left, right in spans:
        while left < right and text[left].isspace():
            left += 1
        if words_of(text[left:right]):
            trimmed.append((left, right))
    return trimmed


def analyse(transcript: str) -> Structure:
    """Everything counted for one answer. Never raises; an empty answer counts nothing."""
    text = transcript or ""
    spans = sentences(text)
    per_sentence = [len(words_of(text[left:right])) for left, right in spans]
    words = sum(per_sentence)

    found: list[Found] = []
    doc = parse(text)
    if doc is not None:
        repeats, echoes = _repeats(doc)
        # A signpost said twice in a repeat — "Then you, then you decide" — is one step.
        found += [
            item
            for item in _signposts(doc, spans)
            if not any(left <= item.start < right for left, right in echoes)
        ]
        found += repeats
        found += _restarts(doc, repeats, spans)
    found.sort(key=lambda item: (item.start, item.end))

    return Structure(
        words=words,
        sentences=len(spans),
        words_per_sentence=round(words / len(spans), 1) if spans else None,
        longest_sentence=max(per_sentence) if per_sentence else None,
        signposts={
            function: sum(1 for item in found if item.kind == function)
            for function in FUNCTIONS
        },
        repeats=sum(1 for item in found if item.kind == REPEAT),
        restarts=sum(1 for item in found if item.kind == RESTART),
        found=tuple(found),
    )


# ── Signposts ───────────────────────────────────────────────────────────────


def _phrases() -> dict[tuple[str, ...], str]:
    """The phrase lists, tokenised the way a transcript is."""
    global _phrase_table
    with _phrase_lock:
        if _phrase_table is None:
            tokenizer = load().tokenizer
            _phrase_table = {
                tuple(token.lower_ for token in tokenizer(phrase)): function
                for function, phrases in PHRASES.items()
                for phrase in phrases
            }
        return _phrase_table


def _signposts(doc, spans: list[tuple[int, int]]) -> list[Found]:
    table = _phrases()
    longest = max(len(key) for key in table)
    found = []
    i = 0
    while i < len(doc):
        matched = _phrase_at(doc, i, table, longest)
        if matched is not None:
            function, length = matched
            found.append(_found(doc, function, i, i + length - 1))
            i += length
            continue
        function, last = _word(doc, i, spans)
        if function is not None:
            found.append(_found(doc, function, i, last))
            i = last + 1
            continue
        i += 1
    return found


def _phrase_at(doc, i: int, table, longest: int) -> tuple[str, int] | None:
    """The longest listed phrase starting at token `i` whose conditions hold."""
    for length in range(min(longest, len(doc) - i), 0, -1):
        key = tuple(token.lower_ for token in doc[i : i + length])
        function = table.get(key)
        if function is not None and _phrase_holds(doc, i, length, key):
            return function, length
    return None


def _phrase_holds(doc, i: int, length: int, key: tuple[str, ...]) -> bool:
    after = doc[i + length] if i + length < len(doc) else None
    if key in (("at", "the", "end"), ("in", "the", "end")):
        # "At the end of the day" is an idiom, not the last step.
        return after is None or after.lower_ != "of"
    if key == ("that", "way"):
        # "That way the client gets it" is a consequence; "go that way" is a direction.
        return _clause_initial(doc, i)
    if key == ("overall",):
        # "The overall cost" describes a noun and sums nothing up.
        return doc[i].dep_ != "amod"
    if key == ("so", "that"):
        # "So that the job can finish" is a purpose; in "so that's why" the "that" is
        # the subject of the next clause, and the two are counted apart.
        return doc[i + 1].tag_ == "IN" or doc[i + 1].dep_ == "mark"
    return True


def _word(doc, i: int, spans) -> tuple[str | None, int]:
    """A single word with another use, read from the parse. Returns (function, last index)."""
    token = doc[i]
    low = token.lower_
    if low == "so":
        return _so(doc, i, spans), i
    if low == "since":
        return _since(token), i
    if low == "then":
        return _then(doc, i, spans), i
    if low in _ORDINALS:
        return _ordinal(doc, i)
    if low == "but":
        return _but(doc, i), i
    if low == "yet":
        return (CONTRAST if token.dep_ == "cc" or token.pos_ == "CCONJ" else None), i
    if low == "while":
        before = doc[i - 1] if i > 0 else None
        contrast = before is not None and before.text == "," and token.dep_ == "mark"
        return (CONTRAST if contrast else None), i
    if low == "though":
        return _though(doc, i), i
    if low == "reason" and i + 1 < len(doc):
        return _reason_is(doc, i)
    return None, i


def _so(doc, i: int, spans) -> str | None:
    before = doc[i - 1] if i > 0 else None
    if before is not None and before.lower_ == "or":
        return None  # "ten minutes or so"
    following = _next_word(doc, i)
    if following is None:
        return None  # "I think so."
    if following.lower_ in ("on", "forth"):
        return None  # "and so on"
    if _opens_answer(doc, i, spans):
        return None
    if _starts_close(doc, following.i):
        return None  # "So overall", "So, in summary": the close is counted, once
    adjacent = doc[i + 1] if i + 1 < len(doc) else None
    if adjacent is not None and not adjacent.is_punct:
        if adjacent.tag_ in ("JJ", "JJR", "JJS", "RB", "RBR", "VBN"):
            return None  # "so slow", "so much", "so tangled"
        if adjacent.pos_ in ("AUX", "VERB"):
            return None  # "and so has the team"
    if _sentence_initial(doc, i, spans) and _in_last(doc[i], spans) and len(spans) > 1:
        return CLOSE
    return REASON


def _since(token) -> str | None:
    if token.dep_ != "mark":
        return None  # "since 2019", "since last year"
    clause = token.head
    main = clause.head if clause.head is not clause else clause
    if any(
        child.dep_ == "aux" and child.lemma_.lower() == "have"
        for child in main.children
    ):
        return None  # "we have had two outages since we moved"
    return REASON


def _then(doc, i: int, spans) -> str | None:
    token = doc[i]
    before = _previous_word(doc, i)
    if before is not None and before.lower_ in _TIME_BEFORE_THEN:
        return None
    if token.dep_ == "pobj":
        return None
    if _conditional(doc, i, spans):
        return None
    return SEQUENCE


def _conditional(doc, i: int, spans) -> bool:
    """Whether this `then` answers an `if` in the same sentence."""
    token = doc[i]
    for child in token.head.children:
        if child.dep_ == "advcl" and any(
            grandchild.dep_ == "mark" and grandchild.lower_ in ("if", "unless")
            for grandchild in child.children
        ):
            return True
    left, _ = _sentence_of(token, spans)
    before = doc[i - 1] if i > 0 else None
    return (
        before is not None
        and before.text == ","
        and any(
            other.lower_ in ("if", "unless")
            for other in doc
            if left <= other.idx < token.idx
        )
    )


def _ordinal(doc, i: int) -> tuple[str | None, int]:
    token = doc[i]
    head = token.head
    if token.dep_ == "amod" or (head.pos_ == "NOUN" and 0 < head.i - token.i <= 2):
        if head.lemma_.lower() in _STEP_NOUNS and head.i > token.i:
            return SEQUENCE, head.i
        return None, i
    if _clause_initial(doc, i) and _next_word(doc, i) is not None:
        return SEQUENCE, i
    return None, i


def _but(doc, i: int) -> str | None:
    token = doc[i]
    if token.dep_ == "prep" or token.pos_ == "ADP":
        return None  # "nothing but the logs"
    before = _previous_word(doc, i)
    if before is not None and before.lower_ in ("all", "nothing", "anything", "none"):
        return None
    return CONTRAST


def _though(doc, i: int) -> str | None:
    token = doc[i]
    before = doc[i - 1] if i > 0 else None
    if before is not None and before.lower_ in ("as", "even"):
        return None
    if token.dep_ == "mark":
        return CONTRAST
    after = doc[i + 1] if i + 1 < len(doc) else None
    if before is not None and before.text == "," and (after is None or after.is_punct):
        return CONTRAST  # "It is late, though."
    return None


def _reason_is(doc, i: int) -> tuple[str | None, int]:
    """ "The reason is", "the main reason was" — but not "the first reason is", a step."""
    after = doc[i + 1]
    if after.lower_ not in ("is", "was", "being", "'s"):
        return None, i
    before = doc[i - 1] if i > 0 else None
    if before is not None and before.lower_ in _ORDINALS | {"other", "final"}:
        return None, i
    return REASON, i + 1


def _starts_close(doc, j: int) -> bool:
    table = _phrases()
    longest = max(len(key) for key in table)
    matched = _phrase_at(doc, j, table, longest)
    return matched is not None and matched[0] == CLOSE


# ── Repeats and restarts ────────────────────────────────────────────────────


def _spoken(doc) -> list:
    """The words a speaker said, without punctuation and fillers."""
    return [
        token
        for token in doc
        if not token.is_punct and not token.is_space and token.lower_ not in FILLERS
    ]


def _repeats(doc) -> tuple[list[Found], list[tuple[int, int]]]:
    """Every repeat, and where each one's second copy is."""
    words = _spoken(doc)
    found = []
    echoes = []
    k = 0
    while k < len(words):
        hit = None
        for run in (4, 3, 2, 1):
            if k + 2 * run > len(words):
                continue
            first = [word.lower_ for word in words[k : k + run]]
            second = [word.lower_ for word in words[k + run : k + 2 * run]]
            if first != second:
                continue
            if _sentence_ends_between(doc, words[k + run - 1], words[k + run]):
                continue
            if (
                run == 1
                and first[0] in _GRAMMATICAL_DOUBLES
                and not _pause_between(doc, words[k], words[k + 1])
            ):
                continue
            hit = run
            break
        if hit is None:
            k += 1
            continue
        repeat = _found(doc, REPEAT, words[k].i, words[k + 2 * hit - 1].i)
        found.append(repeat)
        echoes.append((words[k + hit].idx, repeat.end))
        k += 2 * hit
    return found, echoes


def _restarts(doc, repeats: list[Found], spans) -> list[Found]:
    covered = [(item.start, item.end) for item in repeats]
    found = []
    for token in doc:
        if not _is_break(doc, token):
            continue
        if any(left <= token.idx < right for left, right in covered):
            continue
        last = _previous_word(doc, token.i)
        if last is None or _sentence_of(last, spans) != _sentence_of(token, spans):
            continue
        after = _words_after(doc, token.i, 4, spans)
        if not after:
            continue
        core = last
        if last.dep_ == "neg" and last.i > 0:
            core = doc[last.i - 1]  # "couldn't" is "could" and "n't"
        if _dangles(core, token) or _resumes(doc, core, last, after):
            found.append(
                _found(doc, RESTART, _fragment_start(doc, core, spans), last.i)
            )
    return found


def _dangles(core, brk) -> bool:
    """Whether a phrase stops, at the pause, on a word that cannot end it."""
    if core.lower_ in _ONLY_BEFORE_A_NOUN or core.lower_ in _DEGREE:
        return True  # "had no, there was no", "is very, it's very relational"
    if core.tag_ in ("DT", "PRP$", "TO", "WDT") and core.dep_ not in (
        "pobj",
        "nsubj",
        "nsubjpass",
        "dobj",
        "attr",
        "npadvmod",
    ):
        return True  # "had no, there was no", "going to, we're building"
    if core.tag_ == "IN" and core.dep_ != "mark":
        if not any(
            child.dep_ in ("pobj", "pcomp") and child.i < brk.i
            for child in core.children
        ):
            return True  # "committed to, we promised", "puts everything in, it puts"
    if core.pos_ == "AUX" or core.tag_ == "MD":
        return True  # "the main mistake was, it was"
    if (
        core.dep_ in ("det", "amod", "poss", "compound", "nummod", "predet")
        and core.head.i > brk.i
    ):
        return True  # the word it belongs to is after the pause: "at the old, at the"
    return False


def _resumes(doc, core, last, after) -> bool:
    """Whether the words before the pause come straight back after it."""
    if last.i > 0 and doc[last.i - 1].lower_ == "to" and after[0].lower_ == "to":
        return True  # "need to meet, to see each other"
    if core.pos_ in ("VERB", "AUX") and after[0].pos_ in (
        "PRON",
        "PROPN",
        "NOUN",
        "DET",
    ):
        if any(word.lemma_.lower() == core.lemma_.lower() for word in after[1:3]):
            return True  # "Lee was, he was honest", "the team runs, they run"
    if last.i > 0:
        pair = (doc[last.i - 1].lower_, last.lower_)
        if not doc[last.i - 1].is_punct:
            for left, right in zip(after, after[1:]):
                if (left.lower_, right.lower_) == pair:
                    return True  # "takes us, it takes us"
    return False


def _fragment_start(doc, core, spans) -> int:
    """Up to two words before the one a phrase broke off at, inside its clause."""
    left, _ = _sentence_of(core, spans)
    start = core.i
    for _ in range(2):
        before = start - 1
        if before < 0 or doc[before].is_punct or doc[before].idx < left:
            break
        start = before
    return start


# ── Positions ───────────────────────────────────────────────────────────────


def _found(doc, kind: str, first: int, last: int) -> Found:
    start = doc[first].idx
    end = doc[last].idx + len(doc[last])
    return Found(kind=kind, start=start, end=end, text=doc.text[start:end])


def _sentence_of(token, spans) -> tuple[int, int]:
    for left, right in spans:
        if left <= token.idx < right:
            return left, right
    return 0, 0


def _in_last(token, spans) -> bool:
    return bool(spans) and _sentence_of(token, spans) == spans[-1]


def _previous_word(doc, i: int):
    for j in range(i - 1, -1, -1):
        if not doc[j].is_punct and doc[j].lower_ not in FILLERS:
            return doc[j]
    return None


def _next_word(doc, i: int):
    for j in range(i + 1, len(doc)):
        if doc[j].text in (".", "?", "!"):
            return None
        if not doc[j].is_punct and doc[j].lower_ not in FILLERS:
            return doc[j]
    return None


def _words_after(doc, i: int, count: int, spans) -> list:
    sentence = _sentence_of(doc[i], spans)
    words = []
    for j in range(i + 1, len(doc)):
        token = doc[j]
        if _sentence_of(token, spans) != sentence:
            break
        if token.is_punct or token.lower_ in FILLERS:
            continue
        words.append(token)
        if len(words) == count:
            break
    return words


def _before_in_sentence(doc, i: int, spans) -> list:
    left, _ = _sentence_of(doc[i], spans)
    return [
        token
        for token in doc[:i]
        if token.idx >= left and not token.is_punct and not token.is_space
    ]


def _sentence_initial(doc, i: int, spans) -> bool:
    return all(token.lower_ in _OPENERS for token in _before_in_sentence(doc, i, spans))


def _opens_answer(doc, i: int, spans) -> bool:
    """Whether this word comes before the answer's first real word."""
    if not spans or _sentence_of(doc[i], spans) != spans[0]:
        return False
    return _sentence_initial(doc, i, spans)


def _clause_initial(doc, i: int) -> bool:
    """At the start of a sentence or a clause: nothing before it but a pause or a joiner."""
    j = i - 1
    while j >= 0 and doc[j].lower_ in FILLERS:
        j -= 1
    if j < 0:
        return True
    before = doc[j]
    if before.is_punct:
        return True
    return before.lower_ in ("and", "then", "so", "but", "okay", "right", "well")


def _sentence_ends_between(doc, left, right) -> bool:
    return any(token.text in (".", "?", "!") for token in doc[left.i + 1 : right.i])


def _pause_between(doc, left, right) -> bool:
    return any(_is_break(doc, token) for token in doc[left.i + 1 : right.i])


def _is_break(doc, token) -> bool:
    """A pause written into the transcript. A hyphen inside a word — "take-home" — is not."""
    if token.text not in _BREAKS:
        return False
    if token.text in ("-", "–"):
        before = doc[token.i - 1] if token.i > 0 else None
        return before is None or bool(before.whitespace_) or bool(token.whitespace_)
    return True
