"""The gate between a model's proposal and a stored error record.

Every test here is about something the taxonomy must *refuse*. That is the point of the
module: the accepting path is one line, and the value is entirely in the cases where a
plausible-looking proposal does not become a row a learner is shown.
"""

import pytest

from services.taxonomy import (
    CATEGORIES,
    CATEGORY_GLOSS,
    SUBCATEGORIES,
    TAXONOMY,
    Accepted,
    Rejected,
    locate,
    validate,
)

TRANSCRIPT = (
    "yesterday I go to the office and I speak with my manager about the new project"
)


def reason_for(raw: dict, transcript: str = TRANSCRIPT) -> str:
    outcome = validate(raw, transcript, set())
    assert isinstance(outcome, Rejected), f"expected a rejection, got {outcome}"
    return outcome.reason


def proposal(**overrides) -> dict:
    base = {
        "category": "VERB_TENSE",
        "subcategory": "missing_past_marker",
        "original": "I go to the office",
        "correction": "I went to the office",
        "explanation": "Yesterday needs the past simple.",
        "confidence": 0.9,
    }
    base.update(overrides)
    return base


# ── The vocabulary itself ───────────────────────────────────────────────────


def test_every_category_has_a_gloss():
    """A category the model is shown by name alone is a category it files by feel.

    This is the property that keeps the two in step: adding a category to the taxonomy
    without explaining it would leave the prompt listing a word with no meaning attached.
    """
    assert set(CATEGORY_GLOSS) == CATEGORIES


def test_a_subcategory_is_checked_against_its_own_category():
    """Some subcategory names sit under more than one category — `superfluous` is both an
    ARTICLE and a PREPOSITION — so membership is only ever a question about one category's
    own set. Checking against the flattened list instead would accept
    ARTICLE/wrong_progressive_aspect."""
    assert "superfluous" in TAXONOMY["ARTICLE"]
    assert "superfluous" in TAXONOMY["PREPOSITION"]
    assert "superfluous" in SUBCATEGORIES

    accepted = validate(
        proposal(
            category="ARTICLE",
            subcategory="superfluous",
            original="to the office",
            correction="to office",
        ),
        TRANSCRIPT,
        set(),
    )
    assert isinstance(accepted, Accepted)
    assert (
        reason_for(proposal(subcategory="superfluous"))
        == "wrong_category_for_subcategory"
    )


def test_the_flattened_subcategories_are_the_union_of_the_categories():
    """`SUBCATEGORIES` is what tells "filed under the wrong heading" apart from "invented
    a label", so it has to be derived from the same table it is describing."""
    union = set()
    for subcategories in TAXONOMY.values():
        union |= set(subcategories)
    assert union == SUBCATEGORIES


# ── Labels outside the vocabulary ───────────────────────────────────────────


def test_an_invented_category_is_rejected():
    assert reason_for(proposal(category="SPELLING")) == "unknown_category"


def test_an_invented_subcategory_is_rejected():
    assert reason_for(proposal(subcategory="past_tense_thing")) == "unknown_subcategory"


def test_a_real_subcategory_under_the_wrong_category_is_told_apart():
    """Two different model failures. Filing a real label under the wrong heading is a
    mistake about the taxonomy; inventing one is ignoring it. Counting them together
    would hide which of the two is happening."""
    assert (
        reason_for(proposal(category="ARTICLE", subcategory="missing_past_marker"))
        == "wrong_category_for_subcategory"
    )


def test_a_category_is_accepted_without_a_subcategory():
    """The category is the closed part. A model that can name the category and not the
    subcategory has still produced something comparable across months."""
    outcome = validate(proposal(subcategory=None), TRANSCRIPT, set())
    assert isinstance(outcome, Accepted)
    assert outcome.subcategory is None


def test_the_category_is_matched_case_insensitively():
    outcome = validate(proposal(category="verb_tense"), TRANSCRIPT, set())
    assert isinstance(outcome, Accepted)
    assert outcome.category == "VERB_TENSE"


# ── Locations the model does not get to invent ──────────────────────────────


def test_a_quote_that_is_not_in_the_transcript_is_rejected():
    assert (
        reason_for(proposal(original="I went to the shops"))
        == "original_not_in_transcript"
    )


def test_a_quote_that_appears_twice_is_rejected():
    """An error attached to the wrong occurrence underlines words the speaker got right,
    and there is no way to tell which one was meant."""
    transcript = "I speak English and my sister speak English"
    assert (
        reason_for(
            proposal(original="speak English", correction="speaks English"),
            transcript,
        )
        == "ambiguous_original"
    )


def test_the_span_is_taken_from_the_transcript_not_from_the_model():
    """The stored `original` is whatever the transcript says at that offset, so a model
    that changed the capitalisation while quoting cannot make the two disagree."""
    outcome = validate(proposal(original="i GO to the OFFICE"), TRANSCRIPT, set())
    assert isinstance(outcome, Accepted)
    assert TRANSCRIPT[outcome.span_start : outcome.span_end] == outcome.original
    assert outcome.original == "I go to the office"


def test_a_quote_is_matched_at_word_boundaries():
    """Without this, a quote of "go" matches inside "goes" and underlines two letters in
    the middle of a word."""
    assert locate("go", "he goes to the office") is None
    assert locate("goes", "he goes to the office") == (3, 7)


def test_extra_whitespace_in_a_quote_still_matches():
    outcome = validate(proposal(original="I  go to   the office"), TRANSCRIPT, set())
    assert isinstance(outcome, Accepted)


def test_the_same_span_twice_produces_one_row():
    taken: set[tuple[int, int]] = set()
    first = validate(proposal(), TRANSCRIPT, taken)
    second = validate(proposal(correction="I did go to the office"), TRANSCRIPT, taken)
    assert isinstance(first, Accepted)
    assert isinstance(second, Rejected)
    assert second.reason == "duplicate_span"


# ── Corrections that correct nothing ────────────────────────────────────────


def test_a_correction_identical_to_the_original_is_rejected():
    assert (
        reason_for(proposal(correction="I go to the office"))
        == "correction_equals_original"
    )


def test_a_correction_that_only_moves_punctuation_is_rejected():
    """The speaker did not produce any punctuation — the recogniser did — so a note about
    a comma is a correction nobody can act on. It is the single most common thing a small
    model does with this prompt."""
    assert (
        reason_for(
            proposal(
                category="PREPOSITION",
                subcategory="missing",
                original="about the new project",
                correction="about the new project,",
            )
        )
        == "punctuation_only"
    )


def test_a_correction_that_only_changes_capitalisation_is_rejected():
    assert reason_for(proposal(correction="I Go To The Office")) == "punctuation_only"


def test_an_empty_correction_is_rejected():
    assert reason_for(proposal(correction="   ")) == "empty_correction"


# ── Shapes that are not proposals at all ────────────────────────────────────


@pytest.mark.parametrize("raw", ["a string", 7, None, ["a", "list"]])
def test_something_that_is_not_an_object_is_rejected(raw):
    outcome = validate(raw, TRANSCRIPT, set())
    assert isinstance(outcome, Rejected)
    assert outcome.reason == "malformed"


@pytest.mark.parametrize("confidence", [-0.1, 1.5, "high", True])
def test_a_confidence_outside_zero_to_one_is_rejected(confidence):
    assert reason_for(proposal(confidence=confidence)) == "confidence_out_of_range"


def test_a_missing_confidence_is_answered_with_the_midpoint():
    """A model that omits the field made a formatting slip. Rejecting on it would spend
    the rejection rate — which measures whether the model can *label* — on whether it can
    fill in every key."""
    raw = proposal()
    del raw["confidence"]
    outcome = validate(raw, TRANSCRIPT, set())
    assert isinstance(outcome, Accepted)
    assert outcome.confidence == 0.5


def test_a_quote_longer_than_the_limit_is_rejected():
    """A whole-sentence quote is an underline nobody can read and a span that collides
    with every other error in the turn."""
    assert reason_for(proposal(original=TRANSCRIPT)) == "span_too_long"


# ── A rejection has to be usable ────────────────────────────────────────────


def test_a_rejection_records_what_the_model_wanted_to_say():
    """The reason answers "how often", which is the model's quality. The text answers
    "what did it want", which is whether the taxonomy is missing a category. Different
    problems, different fixes, so both are kept."""
    outcome = validate(proposal(category="SPELLING"), TRANSCRIPT, set())
    assert isinstance(outcome, Rejected)
    record = outcome.as_record()
    assert record["reason"] == "unknown_category"
    assert record["label"] == "SPELLING/missing_past_marker"
    assert record["original"] == "I go to the office"
