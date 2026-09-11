"""Which grammatical forms a speaker actually produced, counted from a parse.

**This is breadth, not accuracy, and the difference is the reason the module exists.** A
learner reaches a zero error rate by only ever using the present simple. Counting errors
would call that improvement; counting which forms were *used* shows it for the retreat it
is. The two numbers are meant to be read together and are produced by different code for
different reasons — this half is deterministic, and no language model touches it, because
it is the half that gets plotted over months.

**A closed vocabulary, and it is not closed for tidiness.** Scenarios declare the forms
they are built to elicit, in exactly these names, so "the scenario asked for the present
perfect and none was produced" is a set difference rather than a judgement. A detector
that invented its own feature names would break that comparison silently: the form would
be counted, the scenario would still report it missing, and nothing would look wrong.

**What the parser can and cannot be asked.** Morphology and dependencies are reliable for
tense, aspect, voice and clause structure. They are much weaker on intent, so the two
features here that are about intent rather than form — a polite request, and duration with
`for`/`since` — are deliberately narrow: they fire on a specific shape and miss the rest.
Undercounting a form is a gap in a chart; overcounting it tells a learner they practised
something they did not.

The parser is loaded once, on first use, and never at import time: importing this module
must stay free, because the test suite imports it hundreds of times and a 1.4-second model
load per collection is a suite nobody runs.
"""

from __future__ import annotations

import threading
from collections import Counter
from dataclasses import dataclass

from config import SPACY_MODEL

# ── The vocabulary ──────────────────────────────────────────────────────────

TENSE_ASPECT: tuple[str, ...] = (
    "present_simple",
    "present_continuous",
    "past_simple",
    "past_continuous",
    "present_perfect",
    "present_perfect_continuous",
    "past_perfect",
    "past_perfect_continuous",
    "future_will",
    "going_to_future",
)

MODALITY: tuple[str, ...] = (
    "modal_can",
    "modal_could",
    "modal_should",
    "modal_would",
    "modal_must",
    "modal_may_might",
)

# Clause counts are what a subordination index is computed from later. They are stored as
# features rather than derived at read time so the index is a ratio of two stored counts
# and not a re-parse of every turn a chart covers.
STRUCTURE: tuple[str, ...] = (
    "main_clause",
    "subordinate_clause",
    "relative_clause",
    "passive_voice",
    "conditional_1",
    "conditional_2",
    "conditional_3",
    "comparatives",
    "superlatives",
    "reported_speech",
    "duration_for_since",
    "polite_request",
)

FEATURES: frozenset[str] = frozenset(TENSE_ASPECT + MODALITY + STRUCTURE)

# The forms a single verb phrase is classified into. The rest of the vocabulary lives on a
# clause, a word or a whole sentence, and no one verb phrase can be said to be in it.
VERB_FORMS: tuple[str, ...] = TENSE_ASPECT + MODALITY

_MODAL_FEATURE = {
    "can": "modal_can",
    "ca": "modal_can",  # "ca" + "n't" is how the tokeniser splits "can't"
    "could": "modal_could",
    "should": "modal_should",
    "would": "modal_would",
    "must": "modal_must",
    "may": "modal_may_might",
    "might": "modal_may_might",
}

# Verbs whose complement clause is somebody else's words. Narrow on purpose: a wider list
# ("think", "feel", "know") counts every opinion as reported speech.
_REPORTING_VERBS = frozenset({"say", "tell", "ask", "mention", "explain", "reply"})

# Finite subordinate clauses only. `xcomp` is absent deliberately: it is always
# non-finite, so it can never reach the clause counter, and listing it would suggest
# otherwise to the next reader.
_SUBORDINATE_DEPS = frozenset({"advcl", "ccomp", "csubj", "csubjpass", "acl"})

# spaCy's pipeline is not safe to call from two threads at once, and analysis runs in a
# worker thread so it does not block the event loop. One lock, held for the parse only.
_lock = threading.Lock()
_nlp = None


def load():
    """The parser, loaded once. Raises if the model is not installed."""
    global _nlp
    if _nlp is None:
        import spacy

        # The named-entity recogniser is excluded and nothing else is. Nothing here asks
        # a question about entities, and it is a third of the parse time. The lemmatizer
        # stays: without it `going`, `said` and `asked` never reach their base forms, and
        # every rule below that names a verb silently stops firing.
        _nlp = spacy.load(SPACY_MODEL, exclude=["ner"])
    return _nlp


def parse(transcript: str):
    """The parse of one transcript, or None when there is nothing to parse.

    Separate from `analyse` because the rule layer in `services/rules.py` reads the same
    parse, and a turn is parsed once rather than once per reader.
    """
    text = (transcript or "").strip()
    if not text:
        return None
    nlp = load()
    with _lock:
        return nlp(text)


def analyse(transcript: str) -> dict[str, int]:
    """Feature counts for one transcript. Only features that occurred appear.

    Absent means zero, and the caller writes one row per entry — a turn with no
    conditionals should not carry a row of zero for every form it did not use.
    """
    return count(parse(transcript))


def count(doc) -> dict[str, int]:
    """Feature counts from a parse `parse` returned."""
    if doc is None:
        return {}

    counts: Counter[str] = Counter()
    for token in doc:
        if _heads_phrase(token):
            counts.update(_verb_phrase_forms(token))
            _count_clause(token, counts)
        _count_word_level(token, counts)

    _count_conditionals(doc, counts)
    return dict(counts)


# ── Verb phrases ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Phrase:
    """One verb phrase the counter classified, with the words it is made of.

    `tokens` are the head, its auxiliaries and, for a `going to` future, the complement
    that carries its meaning — the words a correction has to change for the phrase to be
    a different phrase.
    """

    form: str
    head: int
    tokens: tuple[int, ...]
    words: tuple[str, ...]
    spans: tuple[tuple[int, int], ...]

    def overlaps(self, start: int, end: int) -> bool:
        return any(left < end and start < right for left, right in self.spans)


def verb_phrases(doc) -> list[Phrase]:
    """Every verb phrase `count` counts a form for, in order.

    The same classification as the counts, from the same function, so a form a
    correction is linked to is always a form the repertoire counted.
    """
    if doc is None:
        return []
    phrases = []
    for token in doc:
        if not _heads_phrase(token):
            continue
        found = _verb_phrase_forms(token)
        if not found:
            continue
        members = sorted(
            {token.i} | {aux.i for aux in _auxes(token)} | _going_to_complement(token)
        )
        phrases.append(
            Phrase(
                form=found[0],
                head=token.i,
                tokens=tuple(members),
                words=tuple(doc[i].lower_ for i in members),
                spans=tuple((doc[i].idx, doc[i].idx + len(doc[i])) for i in members),
            )
        )
    return phrases


def _verb_phrase_forms(head) -> list[str]:
    """One verb phrase, classified by its auxiliaries and its morphology together.

    The head carries the aspect and the auxiliaries carry the tense, which is why neither
    is read alone: `been working` is a participle whose tense sits two tokens to its left,
    and `going` is progressive in form while being future in meaning.
    """
    auxes = _auxes(head)
    found: list[str] = []

    for aux in auxes:
        if aux.tag_ == "MD" and aux.lower_ in _MODAL_FEATURE:
            found.append(_MODAL_FEATURE[aux.lower_])
        if aux.lower_ in ("will", "'ll"):
            found.append("future_will")

    if head.tag_ == "MD" and head.lower_ in _MODAL_FEATURE:
        found.append(_MODAL_FEATURE[head.lower_])

    if any(aux.tag_ == "MD" for aux in auxes) or head.tag_ == "MD":
        # A modal phrase is the modal, and nothing else. Without this, "would have told"
        # is counted as a present perfect as well, which puts a form the speaker did not
        # produce into their repertoire.
        return found

    if _heads_going_to(head):
        # `going` is the tensed half and the complement is the meaning. Counted here, on
        # the `going`, and skipped below when the complement comes round in its own turn
        # of the loop — otherwise one future is counted twice.
        return ["going_to_future"]
    if _is_going_to_complement(head):
        return []

    # A tense is a property of a finite phrase. `having finished` and `being told` carry
    # an aspect and no tense, and are not a perfect or a continuous anybody said.
    if not _is_finite(head):
        return []

    perfect = any(aux.lemma_.lower() == "have" for aux in auxes)
    be_aux = any(aux.lemma_.lower() == "be" for aux in auxes)

    # Progressive needs the auxiliary, not just the participle: `start checking` is an
    # -ing form under another verb and is not the continuous at all. In a passive the
    # -ing is on the auxiliary: `is being built`.
    progressive = be_aux and (
        "Prog" in head.morph.get("Aspect")
        or head.tag_ == "VBG"
        or any(aux.dep_ == "auxpass" and aux.tag_ == "VBG" for aux in auxes)
    )

    # The tense is on the first finite word. Read from the head it is wrong whenever the
    # head is a participle: `is built` and `has been finished` have a past participle and
    # a present tense.
    tensed = next((aux for aux in auxes if _finite_word(aux)), None)
    past = "Past" in (tensed or head).morph.get("Tense")

    if perfect and progressive:
        return ["past_perfect_continuous" if past else "present_perfect_continuous"]
    if perfect:
        return ["past_perfect" if past else "present_perfect"]
    if progressive:
        return ["past_continuous" if past else "present_continuous"]

    if tensed is not None and tensed.lemma_.lower() == "do" and not _has_subject(head):
        # `Don't worry` is an imperative, and `do` is the only finite word in it.
        return []
    if past:
        return ["past_simple"]
    if "Pres" in (tensed or head).morph.get("Tense"):
        return ["present_simple"]
    return []


def _heads_phrase(token) -> bool:
    """Whether a verb phrase is classified on this token.

    Every verb that is not an auxiliary of another. The tagger sometimes calls a lexical
    verb an auxiliary — `enjoy` in `I enjoy swimming` — and that verb still heads its
    own phrase.
    """
    if token.pos_ not in ("VERB", "AUX"):
        return False
    return token.dep_ not in ("aux", "auxpass") or not _is_auxiliary(token)


def _auxes(head) -> list:
    """The auxiliaries of a verb phrase, without a lexical verb the tagger miscalled one."""
    return [
        child
        for child in head.children
        if child.dep_ in ("aux", "auxpass") and _is_auxiliary(child)
    ]


def _is_auxiliary(token) -> bool:
    return token.tag_ in ("MD", "TO") or token.lemma_.lower() in (
        "be",
        "have",
        "do",
        "get",
    )


def _has_subject(head) -> bool:
    """Whether a verb has a subject, its own or one shared with the verb it is joined to."""
    if any(
        child.dep_ in ("nsubj", "nsubjpass", "expl", "csubj", "csubjpass")
        for child in head.children
    ):
        return True
    return head.dep_ == "conj" and head.head is not head and _has_subject(head.head)


def _heads_going_to(token) -> bool:
    """A progressive `go` with a `to`-infinitive under it: the future, not the journey.

    "I'm going to work" and "I'm going to the office" differ by whether a verb follows, so
    the test is the shape of the complement rather than the words.
    """
    if token.lemma_.lower() != "go" or token.tag_ != "VBG":
        return False
    return any(child.dep_ == "xcomp" and _has_to_aux(child) for child in token.children)


def _is_going_to_complement(token) -> bool:
    """The verb after `going to`, already counted on the `going`."""
    return token.dep_ == "xcomp" and _has_to_aux(token) and _heads_going_to(token.head)


def _going_to_complement(token) -> set[int]:
    """The complement of a `going to` future and its `to`, as token indices."""
    if not _heads_going_to(token):
        return set()
    for child in token.children:
        if child.dep_ == "xcomp" and _has_to_aux(child):
            return {child.i} | {
                grandchild.i
                for grandchild in child.children
                if grandchild.dep_ == "aux" and grandchild.lower_ == "to"
            }
    return set()


def _has_to_aux(token) -> bool:
    return any(child.dep_ == "aux" and child.lower_ == "to" for child in token.children)


def _is_finite(token) -> bool:
    """Whether this verb phrase carries tense, from the head or from an auxiliary."""
    return _finite_word(token) or any(_finite_word(aux) for aux in _auxes(token))


def _finite_word(token) -> bool:
    """Whether this one word carries tense.

    `been` never does, whatever the tagger says: in `I been to Paris` it is tagged as a
    present-tense verb, and it is a participle with its auxiliary missing.
    """
    if token.lower_ == "been":
        return False
    return "Fin" in token.morph.get("VerbForm") or token.tag_ in (
        "VBD",
        "VBZ",
        "VBP",
        "MD",
    )


# ── Structure ───────────────────────────────────────────────────────────────


def _count_clause(head, counts: Counter[str]) -> None:
    """One clause, counted as main or subordinate. Non-finite phrases are neither.

    A clause here is a verb phrase that carries tense. `to have a really good unit` is a
    complement, not a clause, and counting every to-infinitive as subordination would
    make an infinitive-heavy sentence read as syntactically complex when it is not — the
    subordination index is a ratio and both halves have to mean the same thing.
    """
    if not _is_finite(head):
        return
    if head.dep_ == "relcl":
        counts["relative_clause"] += 1
        counts["subordinate_clause"] += 1
    elif head.dep_ in _SUBORDINATE_DEPS:
        counts["subordinate_clause"] += 1
    else:
        # ROOT, and also a coordinated verb hanging off one: "I finished X and I started
        # Y" is two main clauses, and the second is a `conj`.
        counts["main_clause"] += 1


def _count_word_level(token, counts: Counter[str]) -> None:
    """Features that live on a single word rather than on a verb phrase."""
    if token.dep_ == "auxpass":
        # Counted on the passive auxiliary rather than on the participle, so that
        # "is going to be established" contributes one passive and not two.
        counts["passive_voice"] += 1

    degree = token.morph.get("Degree")
    if "Cmp" in degree and _is_modifier(token):
        counts["comparatives"] += 1
    elif "Sup" in degree and _is_modifier(token) and not _is_fixed_phrase(token):
        counts["superlatives"] += 1

    if (
        token.lower_ in ("for", "since")
        and token.dep_ == "prep"
        and _has_time_object(token)
    ):
        counts["duration_for_since"] += 1

    if token.lemma_.lower() in _REPORTING_VERBS and any(
        child.dep_ == "ccomp" for child in token.children
    ):
        counts["reported_speech"] += 1

    if _is_polite_request(token):
        counts["polite_request"] += 1


def _is_modifier(token) -> bool:
    """Whether a comparative form is modifying something, rather than standing as a noun.

    "more expensive than that one" compares; "I want to know more about the price" is a
    quantity. Both carry Degree=Cmp and only the first is the form a scenario asks for, so
    the test is the token's role rather than its morphology.
    """
    return token.dep_ in ("amod", "advmod", "acomp", "attr", "conj", "oprd")


def _is_fixed_phrase(token) -> bool:
    """`at least`, `at most` — superlative in form, an adverb of degree in use."""
    return (
        token.lower_ in ("least", "most")
        and token.i > 0
        and token.nbor(-1).lower_ == "at"
    )


def _has_time_object(prep) -> bool:
    """Whether a `for`/`since` phrase is about a stretch of time rather than a purpose.

    "for two years" and "since Monday" are duration; "for us" and "for the DevOps team"
    are not. The test is the object, not the preposition, which is why this cannot be
    done on a word list.
    """
    for child in prep.children:
        if child.dep_ != "pobj":
            continue
        if child.like_num:
            return True
        if child.lower_ in (
            "years",
            "year",
            "months",
            "month",
            "weeks",
            "week",
            "days",
            "day",
            "hours",
            "hour",
            "minutes",
            "minute",
            "ages",
            "while",
            "long",
            "yesterday",
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        ):
            return True
        if any(g.like_num for g in child.children):
            return True
    return False


def _is_polite_request(token) -> bool:
    """`Could/Would/Can you ...` asking for something, rather than asking about it.

    Deliberately narrow. It fires on a modal with `you` as its subject in a question, which
    is the shape the scenarios are built to elicit, and misses every other polite form —
    "I was wondering whether", "do you mind" — because widening it to catch those starts
    counting ordinary questions as requests.
    """
    if token.tag_ != "MD" or token.lower_ not in ("could", "would", "can", "will"):
        return False
    head = token.head
    subject = next((child for child in head.children if child.dep_ == "nsubj"), None)
    if subject is None or subject.lower_ != "you":
        return False
    return token.i < subject.i and "?" in token.sent.text


def _count_conditionals(doc, counts: Counter[str]) -> None:
    """The three conditional patterns, told apart by the tense in each half.

    First: `if` + present, main clause with `will`. Second: `if` + past, main clause with
    `would`. Third: `if` + past perfect, main clause with `would have`. The `if`-clause
    alone is not enough — "if I can have one pet" with no consequent is a question, not a
    conditional sentence — so both halves must be present.
    """
    for token in doc:
        if token.lower_ != "if" or token.dep_ != "mark":
            continue
        condition = token.head
        main = condition.head
        if condition is main or main.pos_ not in ("VERB", "AUX"):
            continue

        main_auxes = [
            child.lower_ for child in main.children if child.dep_ in ("aux", "auxpass")
        ]
        cond_auxes = [
            child.lower_
            for child in condition.children
            if child.dep_ in ("aux", "auxpass")
        ]

        would = "would" in main_auxes or "'d" in main_auxes
        will = "will" in main_auxes or "'ll" in main_auxes
        had = "had" in cond_auxes
        past = "Past" in condition.morph.get("Tense") or any(
            "Past" in child.morph.get("Tense")
            for child in condition.children
            if child.dep_ == "aux"
        )

        if would and had:
            counts["conditional_3"] += 1
        elif would and past:
            counts["conditional_2"] += 1
        elif will:
            counts["conditional_1"] += 1
