"""The closed error taxonomy, and the gate that makes a model proposal rejectable.

**Why a closed vocabulary at all.** Categories are compared across months. A label set
that grows whenever a model invents a word cannot be compared with itself: "preposition
errors fell" would mean nothing if last month the same mistakes were filed under
`prep_error`, `wrong_preposition` and `PREPOSITION`. So the vocabulary below is the
whole vocabulary, and anything outside it is refused.

**Refused, and counted.** A rejection is not a failure to handle — it is the measurement
that says whether the model behind the detector is strong enough for this job. Every
refusal carries a machine-readable reason, the caller stores the tally on the turn, and
the rejection *rate* is what a decision about changing models is made from. Silently
dropping a bad proposal would throw that measurement away; silently accepting one would
put an invented category into a trend line.

**The model never supplies a location.** It quotes the text it thinks is wrong, and this
module finds that quote in the transcript. A proposal whose quote is not there is
rejected, and so is one whose quote appears twice — an error attached to the wrong
occurrence is a correction pointing at words the speaker got right. Asking a 4B model for
character offsets and trusting them would be the same bug with an arithmetic step in
front of it.

Subcategories are extensible in the way categories are not: the product's requirements
give a representative list per category, and reading real transcripts adds to it. Adding
one is a change to this file with a test, deliberately — not something a prompt can do at
runtime.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from config import ERROR_MAX_SPAN_WORDS

# ── The vocabulary ──────────────────────────────────────────────────────────
#
# Nine categories, fixed. `false_friend` has its own subcategory because it is the
# highest-value signal for a Spanish first language — actually/currently,
# assist/attend, realise/notice, sensible/sensitive — and folding it into
# `collocation` would bury the one category worth surfacing on its own.
TAXONOMY: dict[str, frozenset[str]] = {
    "VERB_TENSE": frozenset(
        {
            "past_simple_for_present_perfect",
            "present_perfect_for_past_simple",
            "missing_past_marker",
            "wrong_progressive_aspect",
            "conditional_form",
            "future_form",
            "modal_form",
            "reported_speech_backshift",
            # Added after reading the first real corpus: "I appreciate to be here" is a
            # verb-form error with nowhere else to go. The governing verb decides
            # whether its complement is a gerund or an infinitive, and Spanish makes the
            # opposite choice often enough that this is a recurring first-language
            # signal rather than a one-off.
            "non_finite_complement",
        }
    ),
    "SUBJECT_VERB_AGREEMENT": frozenset(
        {"third_person_s", "there_is_are", "collective_noun"}
    ),
    "ARTICLE": frozenset(
        {"missing_definite", "missing_indefinite", "superfluous", "wrong_choice"}
    ),
    "PREPOSITION": frozenset({"wrong", "missing", "superfluous"}),
    "WORD_ORDER": frozenset(
        {"adverb_placement", "question_inversion", "adjective_order"}
    ),
    "NUMBER_COUNTABILITY": frozenset(
        {"plural_marking", "uncountable_pluralised", "quantifier"}
    ),
    "PRONOUN": frozenset({"reference", "case", "omitted_subject"}),
    "LEXICAL_CHOICE": frozenset({"false_friend", "collocation", "register_mismatch"}),
    "OMISSION": frozenset({"missing_auxiliary", "missing_copula"}),
}

CATEGORIES: frozenset[str] = frozenset(TAXONOMY)

# One line per category, written for the model rather than for a reader of this file.
# A 4B model given nine bare category names picks by the sound of them and files a wrong
# preposition under WORD_ORDER; given an example of what each one is about it picks
# correctly far more often. They live here, beside the vocabulary they explain, so a
# category cannot be added without one.
CATEGORY_GLOSS: dict[str, str] = {
    "VERB_TENSE": "the form of a verb is wrong: went/gone, is working/works, "
    "enjoy to swim/enjoy swimming",
    "SUBJECT_VERB_AGREEMENT": "the verb does not agree with its subject: she work/she works",
    "ARTICLE": "a/an/the is missing, extra, or the wrong one: is teacher/is a teacher",
    "PREPOSITION": "the wrong small linking word, or one missing or extra: "
    "depends of/depends on, arrive to/arrive at",
    "WORD_ORDER": "the words are all correct but in the wrong order: "
    "I know where is it/I know where it is",
    "NUMBER_COUNTABILITY": "singular or plural is wrong: three car/three cars, "
    "an information/some information",
    "PRONOUN": "the wrong pronoun, or a missing subject: for she/for her, "
    "is raining/it is raining",
    "LEXICAL_CHOICE": "the wrong word for the meaning: actually/currently, "
    "make a mistake not do a mistake",
    "OMISSION": "a needed auxiliary or `be` is missing: she going/she is going",
}


# Every subcategory, flattened. Used to tell "wrong category for a real subcategory"
# apart from "invented both", which is a different kind of model failure: the first is a
# filing mistake, the second is the model ignoring the list it was given.
SUBCATEGORIES: frozenset[str] = frozenset().union(*TAXONOMY.values())


RejectionReason = Literal[
    "malformed",
    "unknown_category",
    "unknown_subcategory",
    "wrong_category_for_subcategory",
    "empty_original",
    "empty_correction",
    "correction_equals_original",
    "punctuation_only",
    "span_too_long",
    "original_not_in_transcript",
    "ambiguous_original",
    "confidence_out_of_range",
    "duplicate_span",
]


@dataclass(frozen=True)
class Rejected:
    """A proposal that will not be stored, and the reason it was not.

    `label` and `original` are kept verbatim, truncated. The reason alone answers "how
    often", which is the model-quality number; the text answers "what did it want to
    say", which is what tells you whether the taxonomy is missing a category rather than
    the model being weak. Those are different remedies, so both are recorded.
    """

    reason: RejectionReason
    label: str
    original: str

    def as_record(self) -> dict:
        return {
            "reason": self.reason,
            "label": self.label[:120],
            "original": self.original[:200],
        }


@dataclass(frozen=True)
class Accepted:
    """A proposal that survived every check, with the location this module found."""

    category: str
    subcategory: str | None
    span_start: int
    span_end: int
    original: str
    correction: str
    explanation: str | None
    confidence: float


def label_of(raw: object) -> str:
    """How a proposal is named in a rejection record, whatever shape it arrived in."""
    if not isinstance(raw, dict):
        return type(raw).__name__
    category = str(raw.get("category", "")).strip()
    subcategory = str(raw.get("subcategory", "")).strip()
    if category and subcategory:
        return f"{category}/{subcategory}"
    return category or subcategory or "(no label)"


def validate(
    raw: object, transcript: str, taken: set[tuple[int, int]] | None = None
) -> Accepted | Rejected:
    """One proposal, checked against the vocabulary and against the actual words.

    `taken` collects the spans already accepted for this transcript so that a model
    which lists the same mistake twice produces one row and one rejection rather than
    two rows. Pass the same set through a whole turn's proposals.
    """
    if not isinstance(raw, dict):
        return Rejected("malformed", label_of(raw), "")

    label = label_of(raw)
    category = str(raw.get("category", "")).strip().upper()
    subcategory_raw = raw.get("subcategory")
    subcategory = (
        str(subcategory_raw).strip().lower()
        if isinstance(subcategory_raw, str) and subcategory_raw.strip()
        else None
    )

    if category not in CATEGORIES:
        return Rejected("unknown_category", label, _text(raw.get("original")))

    if subcategory is not None and subcategory not in TAXONOMY[category]:
        # Two different failures wearing one shape. A subcategory that exists elsewhere
        # in the taxonomy means the model knew the vocabulary and filed the error under
        # the wrong heading; one that exists nowhere means it wrote its own.
        reason: RejectionReason = (
            "wrong_category_for_subcategory"
            if subcategory in SUBCATEGORIES
            else "unknown_subcategory"
        )
        return Rejected(reason, label, _text(raw.get("original")))

    original = _text(raw.get("original"))
    correction = _text(raw.get("correction"))
    if not original:
        return Rejected("empty_original", label, "")
    if not correction:
        return Rejected("empty_correction", label, original)
    if correction == original:
        # A correction identical to the text is a model agreeing with itself. Stored, it
        # would be an error record the learner cannot act on and a count that inflates
        # every accuracy rate.
        return Rejected("correction_equals_original", label, original)
    if _bare(correction) == _bare(original):
        # The only difference is punctuation or capitalisation, neither of which the
        # speaker produced — they come from the recogniser. "also?" corrected to "also,"
        # is a note about a comma nobody said, filed under a grammar category, and it is
        # the single most common thing a small model does with this prompt.
        return Rejected("punctuation_only", label, original)

    confidence = _confidence(raw.get("confidence"))
    if confidence is None:
        return Rejected("confidence_out_of_range", label, original)

    if len(original.split()) > ERROR_MAX_SPAN_WORDS:
        return Rejected("span_too_long", label, original)

    located = locate(original, transcript)
    if located is None:
        return Rejected("original_not_in_transcript", label, original)
    if located == AMBIGUOUS:
        return Rejected("ambiguous_original", label, original)

    span_start, span_end = located
    if taken is not None and (span_start, span_end) in taken:
        return Rejected("duplicate_span", label, original)
    if taken is not None:
        taken.add((span_start, span_end))

    explanation = _text(raw.get("explanation")) or None

    return Accepted(
        category=category,
        subcategory=subcategory,
        span_start=span_start,
        span_end=span_end,
        original=transcript[span_start:span_end],
        correction=correction[:500],
        explanation=explanation[:500] if explanation else None,
        confidence=confidence,
    )


# Returned when a quote matches more than once and there is no way to tell which
# occurrence was meant. A sentinel rather than None because "not there at all" and "there
# twice" are different model failures and are counted separately.
AMBIGUOUS = (-1, -1)


def locate(quote: str, transcript: str) -> tuple[int, int] | None:
    """Where `quote` sits in `transcript`, if it sits there exactly once.

    Case-insensitive, because a recogniser capitalises the first word of what it thinks
    is a sentence and a model quoting it back rarely reproduces that. Whitespace inside
    the quote matches any run of whitespace, so a model that normalises two spaces to one
    is not punished for it.

    Matching is bounded by word edges. Without that, a quote of "is" would match inside
    "amenities" and underline three letters in the middle of a word.
    """
    quote = quote.strip()
    if not quote:
        return None

    pattern = r"\s+".join(re.escape(part) for part in quote.split())
    left = r"(?<![\w'])" if quote[0].isalnum() or quote[0] == "'" else ""
    right = r"(?![\w'])" if quote[-1].isalnum() or quote[-1] == "'" else ""

    matches = list(re.finditer(left + pattern + right, transcript, re.IGNORECASE))
    if not matches:
        return None
    if len(matches) > 1:
        return AMBIGUOUS
    return matches[0].start(), matches[0].end()


def _bare(text: str) -> str:
    """Letters and digits only, lowercased: what the speaker actually produced."""
    return re.sub(r"[^\w]+", "", text).lower()


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _confidence(value: object) -> float | None:
    """A confidence in 0-1, or None if the model did not supply a usable one.

    Absent is not the same as wrong: a model that omits the field is answered with the
    midpoint rather than a rejection, because a missing number is a formatting slip and
    rejecting on it would spend the taxonomy's rejection rate — the signal about whether
    the model can do the *labelling* — on whether it can fill in every key.
    """
    if value is None:
        return 0.5
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not 0.0 <= float(value) <= 1.0:
        return None
    return round(float(value), 4)
