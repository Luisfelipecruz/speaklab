"""Errors a parse can decide on its own: agreement, and a missing article.

**Why a second detector, and why only these two.** The language model proposes errors in
nine categories, and when it lands on a real one it usually files it under the wrong
category. Two of the nine are different in kind. Whether a verb agrees with its
subject, and whether a singular noun has lost its article, are facts about the parse rather
than judgements about meaning: the parse names the subject, its number, the verb's form
and the noun's determiners, and a rule that compares them is right or wrong for a reason a
reader can check. So these two are proposed here, with a confidence of 1.0 and no model.

**Narrow on purpose, and that is the design rather than a first draft.** A proposal from
here reaches a learner's history with no gate in front of it. So every rule fires only on
a shape where the parse leaves no doubt, and stays silent wherever the same words have a
grammatical reading — a collective noun, a quantity, a coordination, a subjunctive, an
uncountable noun, or a past-time context in which a bare verb is a missing past marker
rather than a missing -s. Silence costs recall. A wrong proposal costs a learner being told
something false with full confidence, and nothing downstream would catch it.

**What this does to the category mix.** A layer covering two categories finds those two
more reliably than the model finds the other seven, so a learner's errors per category are
partly a property of which detector covers which category. Every stored row says which
detector proposed it, and the report says what that means.

**What it cannot see.** An omission leaves nothing behind to be unsure of. A recogniser
that swallowed a reduced "an" produces exactly the text a speaker who dropped it would, and
the per-word confidence gate can only read the words on either side of the gap.

Offsets are into the parsed text, which is the stripped transcript — the same text the
model's quotes are located in.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from services.taxonomy import Accepted

CONFIDENCE = 1.0

AGREEMENT = ("SUBJECT_VERB_AGREEMENT", "third_person_s")
THERE_BE = ("SUBJECT_VERB_AGREEMENT", "there_is_are")
INDEFINITE = ("ARTICLE", "missing_indefinite")
DEFINITE = ("ARTICLE", "missing_definite")

# Every label a rule can emit. There is no taxonomy gate in front of these, so the test
# suite checks this tuple against the taxonomy instead.
LABELS: tuple[tuple[str, str], ...] = (AGREEMENT, THERE_BE, INDEFINITE, DEFINITE)

# A rule quotes the subject and its verb, or the noun phrase and its verb — enough to
# read, and short enough never to reach the model's twelve-word limit.
SPAN_WORDS = 6


@dataclass(frozen=True)
class RuleError:
    """One proposal, which rule made it, and the word its correction puts in.

    `replacement` is what a model proposal on the same words has to contain to be the
    same correction rather than a different claim about them. See `services/errors.py`.
    """

    accepted: Accepted
    rule: str
    replacement: str


# ── Word lists ──────────────────────────────────────────────────────────────
#
# Most of these are words on which a rule would be wrong, not words on which it is right.
# They are closed and short, and a word missing from one costs a false positive, which is
# why the tests carry a sentence for each group. `_COUNTABLE_ING` runs the other way.

_THIRD_PRONOUNS = frozenset({"he", "she", "it", "this", "that"})
_INDEFINITE_PRONOUNS = frozenset(
    """
    everyone everybody someone somebody anyone anybody nobody everything something
    anything nothing
    """.split()
)
_PLURAL_PRONOUNS = frozenset({"we", "they", "you", "these", "those"})

# Plural agreement with these is standard British English: "the team are playing".
_COLLECTIVE = frozenset(
    """
    team family staff government company class group audience committee crew band
    public police management board jury couple department club army crowd council
    community population personnel faculty firm union party household squad media
    data
    """.split()
)

# The head of "a lot of people", "the majority of voters": the verb agrees with what is
# measured, not with the word that measures it.
_PARTITIVE = frozenset(
    """
    lot lots number majority minority most half part rest percent plenty couple kind
    sort type bunch series variety total none all some any each one many few several
    both either neither remainder proportion quarter third set pair range amount
    deal
    """.split()
)

# Nouns that end in s and take a singular verb.
_SINGULAR_S = frozenset(
    """
    news series species means physics mathematics maths economics politics athletics
    gymnastics headquarters crossroads whereabouts statistics ethics linguistics
    electronics logistics genetics diabetes
    """.split()
)

# "let him go", "make it work": a bare verb under these is an infinitive, and its
# subject is the verb's object.
_CAUSATIVE = frozenset(
    {"let", "make", "have", "help", "see", "hear", "watch", "feel", "notice", "bid"}
)

# "I suggest that he go": the subjunctive, which is a bare verb on purpose.
_MANDATIVE = frozenset(
    """
    suggest insist recommend demand require request propose ask order urge advise
    prefer
    """.split()
)

_PAST_WORDS = frozenset({"yesterday", "ago", "earlier", "previously", "formerly"})

# Units a number can make into one amount: "two years is a long time", "ten dollars is
# enough". A number in front of anything else is a count, and "three people passes" is an
# agreement error like any other.
_UNITS = frozenset(
    """
    seconds minutes hours days weeks months years decades dollars euros pounds pesos
    cents miles kilometres kilometers metres meters kilos kilograms litres liters
    percent times
    """.split()
)

_TIME_NOUNS = frozenset(
    """
    time moment minute hour day week weekend month year decade century morning
    afternoon evening night today tonight tomorrow yesterday monday tuesday
    wednesday thursday friday saturday sunday spring summer autumn fall winter
    season term semester quarter period
    """.split()
)

# Uncountable, or countable only in a sense a learner rarely means. "It is good news",
# "it is hard work" and "that is good advice" have no article and need none.
_UNCOUNTABLE = frozenset(
    """
    information advice news weather work homework housework music furniture
    equipment luggage baggage money cash fun help water food traffic research
    knowledge feedback software hardware experience progress evidence stuff luck
    quality value space parking heating electricity internet wifi rent noise light
    air business health safety security english spanish history art sport love life
    trouble pleasure practice rain snow coffee tea bread rice access permission
    accommodation transport transportation insurance maintenance storage content
    data production education training management support damage garbage rubbish
    mail fruit meat milk paper clothing vocabulary grammar pronunciation behaviour
    behavior patience confidence happiness peace freedom nature nonsense shopping
    cleaning cooking sense use care importance attention respect time
    """.split()
)

# Nouns ending in -ing that are countable things rather than gerunds. Every other -ing noun
# is treated as a gerund and left alone — "it is good training" needs no article — so a
# word missing from here costs a missed proposal, never a wrong one.
_COUNTABLE_ING = frozenset(
    """
    thing king ring wing string spring building meeting wedding ceiling painting
    drawing feeling finding opening ending beginning saying sibling recording
    booking crossing listing offering warning posting outing earring duckling
    darling evening morning
    """.split()
)

# Nouns that go bare after "be" or "as" without being uncountable: a place in "I am
# home", a share in "part of", an office held by one person at a time.
_BARE_PREDICATES = frozenset(
    """
    home part enough family friends lunch dinner breakfast school college university
    class bed church hospital town course president chairman chairwoman chairperson
    chair head captain king queen mayor governor
    """.split()
)

# Adjectives that make a noun unique, so the article it lost is "the": "the best
# option", "the same problem", "the only way".
_DEFINITE_ADJECTIVES = frozenset(
    """
    same only main next last first second third following previous whole entire
    right wrong
    """.split()
)

# Words that already do an article's job, or sit where it would go.
_ARTICLE_BLOCKERS = frozenset({"such", "what", "quite", "rather", "enough", "own"})

_ROLE_VERBS = frozenset(
    {"work", "serve", "act", "start", "begin", "employ", "hire", "train", "volunteer"}
)
_BE_PERSONS = frozenset({"i", "you", "he", "she"})
_BE_ANY = _BE_PERSONS | frozenset({"it", "this", "that", "we", "they"})


# ── Entry point ─────────────────────────────────────────────────────────────


def propose(doc) -> list[RuleError]:
    """Every rule over one parse, in text order, with no two proposals overlapping.

    `doc` is what `grammar.parse` returned, and None — an empty transcript — proposes
    nothing.
    """
    if doc is None:
        return []

    found = [*_agreement(doc), *_there_be(doc), *_article(doc)]
    found.sort(key=lambda item: (item.accepted.span_start, item.accepted.span_end))

    kept: list[RuleError] = []
    for item in found:
        if item.accepted.correction == item.accepted.original:
            continue  # a correction that changes nothing is a rule that misread its input
        if kept and item.accepted.span_start < kept[-1].accepted.span_end:
            continue
        kept.append(item)
    return kept


# ── Subject–verb agreement ──────────────────────────────────────────────────


def _agreement(doc) -> list[RuleError]:
    out: list[RuleError] = []
    for head in doc:
        if head.pos_ not in ("VERB", "AUX") or head.dep_ in ("aux", "auxpass"):
            continue
        if any(child.dep_ == "expl" for child in head.children):
            continue  # "there is", which `_there_be` owns

        subjects = [c for c in head.children if c.dep_ in ("nsubj", "nsubjpass")]
        tensed = _tensed(head)
        if len(subjects) != 1 or tensed is None:
            # Two subjects on one verb is a parse that has joined two clauses, which in
            # recogniser output with no punctuation is usually what happened.
            continue
        subject = subjects[0]
        if _interrupted(doc, subject, tensed):
            continue
        number = _subject_number(subject)
        if number is None:
            continue

        replacement = _disagreement(tensed, head, number)
        if replacement is None:
            continue

        tokens = _agreement_tokens(doc, subject, tensed)
        out.append(
            _error(
                doc,
                AGREEMENT,
                "agreement",
                tokens,
                tensed,
                replacement,
                _agreement_reason(subject, number, replacement),
            )
        )
    return out


def _tensed(head):
    """The word that carries the clause's tense, or None for a modal or an infinitive."""
    auxes = sorted(
        (c for c in head.children if c.dep_ in ("aux", "auxpass")), key=lambda c: c.i
    )
    if any(aux.tag_ in ("MD", "TO") for aux in auxes):
        return None
    return auxes[0] if auxes else head


def _interrupted(doc, subject, tensed) -> bool:
    """A sentence or clause boundary between the subject and its verb.

    A comma or a conjunction is a clause boundary the parse has reached across, and in
    recogniser output it is where one sentence ran into the next. "in my unit or do I
    need" is two clauses; a parse that makes "unit" the subject of "do" has not found an
    agreement error. So is a capital on a verb that follows its subject — "the letter L.
    Collect the flowers" — which is a new sentence the tokeniser did not see start.
    """
    low, high = sorted((subject.i, tensed.i))
    if any(word.pos_ in ("CCONJ", "PUNCT") for word in doc[low + 1 : high]):
        return True
    return subject.i < tensed.i and tensed.text[:1].isupper()


def _subject_number(subject) -> str | None:
    """The subject's person and number, or None wherever the answer is arguable."""
    lower = subject.lower_
    if subject.tag_ in ("WDT", "WP", "CD"):
        return None  # a relative pronoun or a number: the rule does not chase what it means
    if any(child.dep_ == "conj" for child in subject.children):
        return None  # "my brother and my sister", and the singular idioms among them
    if lower == "i":
        return "first"
    if lower in _THIRD_PRONOUNS or lower in _INDEFINITE_PRONOUNS:
        return "third"
    if lower in _PLURAL_PRONOUNS:
        return "plural"
    if lower in _COLLECTIVE or lower in _PARTITIVE or lower in _SINGULAR_S:
        return None
    if subject.tag_ in ("NN", "NNP"):
        if subject.tag_ == "NNP" and any(c.dep_ == "det" for c in subject.children):
            # "The Linux build": a name modifying a noun, parsed as its subject.
            return None
        return "third"
    if subject.tag_ == "NNS":
        if lower in _UNITS and any(c.dep_ == "nummod" for c in subject.children):
            return None  # "two years is a long time": one amount
        if any(letter.isupper() for letter in subject.text):
            # A capital on a plural is a name far more often than it is a sentence
            # start the recogniser capitalised — "Requests is", "Teams is" — and a
            # product or a team takes a singular verb.
            return None
        return "plural"
    return None


def _disagreement(tensed, head, number: str) -> str | None:
    """The form the verb should have taken, or None when it agrees or cannot be judged."""
    word = tensed.lower_
    if word.startswith(("'", "’")):
        return None  # 's, 're, 'm: a contraction nobody writes with the wrong subject

    if word in ("was", "were"):
        # Past tense is only in agreement for `be`. "If he were" and "I wish it were" are
        # the subjunctive, so singular "were" is never proposed.
        if word == "was" and number == "plural":
            return "were"
        return None

    if tensed.tag_ == "VBZ":
        form = "third"
    elif tensed.tag_ == "VBP" or (tensed.i == head.i and tensed.tag_ == "VB"):
        form = "plain"
    else:
        return None

    if number == "third" and form == "third":
        return None
    if number in ("first", "plural") and form == "plain":
        if number == "first" and word == "are":
            return "am"
        return None

    # A present-tense mismatch on the verb itself. In a past-time context that bare verb
    # is a missing past marker — "yesterday she go" is "she went" — and a rule that cannot
    # tell which of the two errors it is looking at says nothing. An auxiliary is not
    # ambiguous that way: "the user have described" can only be "has".
    main_verb = tensed.i == head.i
    if main_verb and _past_context(head):
        return None
    if number == "third":
        if main_verb and _bare_by_design(head):
            return None
        return _third_person(tensed)
    if number == "first" and word == "is":
        return "am"
    return _plain(tensed)


def _bare_by_design(head) -> bool:
    """A causative complement or a subjunctive: a bare verb that is meant to be bare.

    "let him go", "make it work" — a complement of a causative. "I suggest that he go",
    "it is important that she be on time" — a that-clause under a verb of demanding or an
    adjective. A clause introduced by "when", "whether" or "if" is neither, and "when the
    user disagree" is an agreement error.
    """
    governor = head.head
    if governor.i == head.i or head.dep_ not in ("ccomp", "xcomp"):
        return False
    lemma = governor.lemma_.lower()
    if lemma in _CAUSATIVE:
        return True
    marks = {child.lower_ for child in head.children if child.dep_ == "mark"}
    if marks - {"that"}:
        return False
    return lemma in _MANDATIVE or any(
        child.dep_ == "acomp" and child.pos_ == "ADJ" for child in governor.children
    )


def _past_context(head) -> bool:
    """A past-time word in the sentence, or a past verb in a clause joined to this one.

    Joined means coordinated with it or subordinated to it as a time or reason clause:
    "I finished the report and she send it", "when I arrived she say hello". A past verb
    inside this clause's own complement is somebody's past being reported in the present
    — "I still thinks we were interrupted" — and says nothing about this verb's tense.
    """
    for word in head.sent:
        if word.lower_ in _PAST_WORDS:
            return True
        if word.lower_ == "last" and word.head.lower_ in _TIME_NOUNS:
            return True
    joined = [c for c in head.children if c.dep_ in ("conj", "advcl")]
    if head.dep_ in ("conj", "advcl"):
        joined.append(head.head)
    return any(_is_past(verb) for verb in joined)


def _is_past(verb) -> bool:
    return verb.tag_ == "VBD" or any(
        child.dep_ in ("aux", "auxpass") and child.tag_ == "VBD"
        for child in verb.children
    )


def _agreement_tokens(doc, subject, tensed) -> list:
    """The subject's phrase and the verb, or the verb alone if that would be too long."""
    if subject.i < tensed.i:
        start = subject.left_edge.i
        if tensed.i - start >= SPAN_WORDS:
            start = subject.i
        if tensed.i - start >= SPAN_WORDS:
            return [tensed]
        return list(doc[start : tensed.i + 1])
    if subject.i - tensed.i >= SPAN_WORDS:
        return [tensed]
    return list(doc[tensed.i : subject.i + 1])


def _agreement_reason(subject, number: str, replacement: str) -> str:
    if number == "first":
        return f'With "I", the verb is "{replacement}".'
    if number == "plural":
        return f'"{subject.text}" is plural, so the verb is "{replacement}".'
    return (
        f'"{subject.text}" is one person or thing, so the present tense is '
        f'"{replacement}".'
    )


def _third_person(token) -> str:
    word = token.lower_
    irregular = {"am": "is", "are": "is", "be": "is", "have": "has", "do": "does"}
    if word in irregular:
        return irregular[word]
    if re.search(r"(s|x|z|ch|sh|o)$", word):
        return word + "es"
    if re.search(r"[^aeiou]y$", word):
        return word[:-1] + "ies"
    return word + "s"


def _plain(token) -> str:
    word = token.lower_
    irregular = {"is": "are", "was": "were", "has": "have", "does": "do"}
    return irregular.get(word, token.lemma_.lower())


# ── There is, there are ─────────────────────────────────────────────────────


def _there_be(doc) -> list[RuleError]:
    """Agreement after "there": the verb agrees with the noun after it, or its first
    conjunct if there are several.

    Only the full forms. "There's two bedrooms" is ordinary spoken English from native
    speakers, and a rule that marked it would be correcting the language rather than the
    learner.
    """
    out: list[RuleError] = []
    for there in doc:
        if there.dep_ != "expl" or there.lower_ != "there":
            continue
        verb = there.head
        if verb.lower_ not in ("is", "are", "was", "were"):
            continue
        noun = next(
            (c for c in verb.children if c.dep_ in ("attr", "nsubj") and c.i > verb.i),
            None,
        )
        if noun is None or noun.lower_ in _PARTITIVE:
            continue

        if verb.lower_ in ("is", "was"):
            if noun.tag_ != "NNS" or noun.lower_ in _SINGULAR_S:
                continue
            replacement = "are" if verb.lower_ == "is" else "were"
            reason = f'"{noun.text}" is plural, so it is "there {replacement}".'
        else:
            determiner = next((c for c in noun.children if c.dep_ == "det"), None)
            if (
                noun.tag_ != "NN"
                or determiner is None
                or determiner.lower_ not in ("a", "an", "one", "another")
                or any(child.dep_ == "conj" for child in noun.children)
            ):
                continue
            replacement = "is" if verb.lower_ == "are" else "was"
            reason = (
                f'"{determiner.text} {noun.text}" is one thing, so it is '
                f'"there {replacement}".'
            )

        end = noun if noun.i - there.i < SPAN_WORDS else verb
        tokens = list(doc[there.i : end.i + 1])
        out.append(_error(doc, THERE_BE, "there_be", tokens, verb, replacement, reason))
    return out


# ── Articles ────────────────────────────────────────────────────────────────


def _article(doc) -> list[RuleError]:
    """A singular countable noun with no determiner, in two shapes and no others.

    After `be` with a personal subject — "I am engineer", "it is very good apartment" —
    and after `as` with a verb of working — "I work as teacher". Both are where a Spanish
    first language drops the article most predictably, and both are where the parse
    names the noun's role unambiguously. The shape that looks the same and is not —
    "with possible renewal", "in good condition" — is left alone: after a preposition a
    bare noun phrase is grammatical too often for a rule to say which it is.
    """
    out: list[RuleError] = []
    for token in doc:
        if token.lemma_.lower() == "be" and token.dep_ not in ("aux", "auxpass"):
            found = _after_be(doc, token)
        elif token.lower_ == "as" and token.dep_ == "prep":
            found = _after_as(doc, token)
        else:
            found = None
        if found is not None:
            out.append(found)
    return out


def _after_be(doc, be) -> RuleError | None:
    subject = next((c for c in be.children if c.dep_ == "nsubj"), None)
    if subject is None or subject.i > be.i:
        return None
    who = subject.lower_
    person = who in _BE_PERSONS
    # A noun parsed as an adjectival complement is usually an adjective the tagger got
    # wrong — "it's super lightweight" — so it counts only after a person, where "she is
    # nurse" is the parse the error itself produces.
    noun = next(
        (
            c
            for c in be.children
            if c.i > be.i
            and (c.dep_ == "attr" or (person and c.dep_ == "acomp" and c.tag_ == "NN"))
        ),
        None,
    )
    if noun is None or not _needs_article(noun):
        return None

    described = any(child.dep_ == "amod" for child in noun.lefts)
    if not person and not (who in _BE_ANY and described):
        # "It is time" and "that is life" are bare on purpose. With an adjective in front
        # the noun is being described as one of a kind, and then it needs an article.
        # Only after a pronoun: after a noun subject — "the output may be simple text" —
        # the uncountable reading is common enough that the shape stops deciding anything.
        return None

    start = subject.left_edge if subject.i == be.i - 1 else be
    if noun.i - start.i >= SPAN_WORDS:
        start = be
    return _insert_article(doc, start, noun)


def _after_as(doc, prep) -> RuleError | None:
    verb = prep.head
    if verb.lemma_.lower() not in _ROLE_VERBS or verb.i > prep.i:
        return None
    noun = next((c for c in prep.children if c.dep_ == "pobj"), None)
    if noun is None or not _needs_article(noun):
        return None
    start = verb if noun.i - verb.i < SPAN_WORDS else prep
    return _insert_article(doc, start, noun)


def _needs_article(noun) -> bool:
    lower = noun.lower_
    if noun.tag_ != "NN":
        return False
    if lower.endswith("ing") and lower not in _COUNTABLE_ING:
        return False  # "it is good training": a gerund, and uncountable
    if lower in _UNCOUNTABLE or lower in _TIME_NOUNS or lower in _BARE_PREDICATES:
        return False
    for child in noun.children:
        if child.dep_ in ("det", "poss", "nummod", "predet", "quantmod"):
            return False
        if child.dep_ == "prep" and child.lower_ == "of":
            return False  # "head of the department", "part of the team"
    return not any(word.lower_ in _ARTICLE_BLOCKERS for word in _phrase(noun))


def _phrase(noun) -> list:
    """The noun and everything in front of it that belongs to its phrase."""
    return list(noun.doc[noun.left_edge.i : noun.i + 1])


def _insert_article(doc, start, noun) -> RuleError:
    phrase = _phrase(noun)
    definite = any(
        word.tag_ == "JJS" or word.lower_ in _DEFINITE_ADJECTIVES
        for word in phrase[:-1]
    )
    article = "the" if definite else _indefinite_article(phrase[0].text)
    label = DEFINITE if definite else INDEFINITE

    tokens = list(doc[start.i : noun.i + 1])
    span_start, span_end = tokens[0].idx, tokens[-1].idx + len(tokens[-1].text)
    original = doc.text[span_start:span_end]
    cut = phrase[0].idx - span_start
    correction = original[:cut] + article + " " + original[cut:]

    if definite:
        reason = (
            'This describes the only one of its kind, so it takes "the": '
            f'"the {_text(phrase)}".'
        )
    else:
        reason = (
            f'"{noun.text}" is one of something that can be counted, so it needs '
            f'"{article}": "{article} {_text(phrase)}".'
        )
    return RuleError(
        accepted=Accepted(
            category=label[0],
            subcategory=label[1],
            span_start=span_start,
            span_end=span_end,
            original=original,
            correction=correction,
            explanation=reason,
            confidence=CONFIDENCE,
        ),
        rule="article",
        replacement=article,
    )


def _indefinite_article(word: str) -> str:
    """The indefinite article for `word`, by the sound it starts with, not its letter."""
    lower = word.lower()
    if lower.startswith(("hour", "honest", "honour", "honor", "heir")):
        return "an"
    if re.match(r"(uni|use|usu|uti|ure|eu|one|once|ewe)", lower):
        return "a"
    return "an" if lower[:1] in "aeiou" else "a"


# ── Building a proposal ─────────────────────────────────────────────────────


def _error(doc, label, rule, tokens, changed, replacement, reason) -> RuleError:
    """A proposal covering `tokens`, with `changed` replaced by `replacement`.

    A negation written onto the verb comes too, so "she don't" is corrected to "she
    doesn't" rather than underlining two thirds of a word.
    """
    last = tokens[-1]
    negated = (
        last.i == changed.i
        and last.i + 1 < len(doc)
        and doc[last.i + 1].lower_ == "n't"
        and doc[last.i + 1].idx == last.idx + len(last.text)
    )
    if negated:
        tokens = [*tokens, doc[last.i + 1]]

    span_start = tokens[0].idx
    span_end = tokens[-1].idx + len(tokens[-1].text)
    original = doc.text[span_start:span_end]
    if changed.text[:1].isupper():
        replacement = replacement[:1].upper() + replacement[1:]
    cut = changed.idx - span_start
    correction = original[:cut] + replacement + original[cut + len(changed.text) :]
    if negated:
        replacement += "n't"

    return RuleError(
        accepted=Accepted(
            category=label[0],
            subcategory=label[1],
            span_start=span_start,
            span_end=span_end,
            original=original,
            correction=correction,
            explanation=reason,
            confidence=CONFIDENCE,
        ),
        rule=rule,
        replacement=replacement,
    )


def _text(tokens) -> str:
    return tokens[0].doc.text[tokens[0].idx : tokens[-1].idx + len(tokens[-1].text)]
