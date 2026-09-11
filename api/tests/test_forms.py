"""The join between a correction and the verb form it corrects, against hand labels.

The labels are in `form_labels.py`, with what each set is evidence of. A case in the
development set the join gets wrong fails here rather than being relabelled to pass; on
the held-out set and the golden turns a missing side is allowed and measured, and a wrong
form never is.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from services import forms, grammar
from services.forms import Link
from tests.form_labels import (
    HELD_OUT,
    LABELLED,
    PAST,
    PC,
    PP,
    PS,
    SVA,
    VT,
    WILL,
    golden_cases,
    link_one,
    verdict,
)


@pytest.fixture(scope="module", autouse=True)
def parser():
    return grammar.load()


@pytest.mark.parametrize("case", LABELLED, ids=lambda case: case.quote)
def test_a_labelled_correction_is_linked_to_its_forms(case):
    assert link_one(case) == case.label


@pytest.mark.parametrize("case", HELD_OUT, ids=lambda case: case.quote)
def test_a_held_out_correction_is_never_linked_to_a_wrong_form(case):
    assert verdict(case, link_one(case)) != "wrong", link_one(case)


def test_the_golden_labels_are_never_linked_to_a_wrong_form():
    source, cases = golden_cases()
    if source is None:
        pytest.skip("no golden error manifest here")
    assert cases
    for case in cases:
        assert case.form != "?", f"{case.quote!r} has no line in GOLDEN_FORMS"
        assert verdict(case, link_one(case)) != "wrong", (case.quote, link_one(case))


# ── The join's rules ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Row:
    category: str
    span_start: int | None
    span_end: int | None
    correction: str


def at(transcript: str, quote: str, correction: str, category: str = VT) -> Row:
    start = transcript.index(quote)
    return Row(category, start, start + len(quote), correction)


def test_one_phrase_is_linked_to_one_correction():
    """A rule and the model correcting the same verb differently: the first links."""
    text = "My sister work in a bank."
    links = forms.link(
        text,
        [
            at(text, "My sister work", "My sister works", SVA),
            at(text, "work", "worked"),
        ],
    )
    assert links == [Link(PS, PS), forms.UNLINKED]


def test_a_correction_that_rewrites_two_phrases_is_linked_to_the_first():
    text = "Yesterday I go and see my friends."
    assert forms.link(text, [at(text, "go and see", "went and saw")]) == [
        Link(PS, PAST)
    ]


def test_a_correction_with_no_location_is_not_linked():
    assert forms.link("I go there.", [Row(VT, None, None, "went")]) == [forms.UNLINKED]


def test_nothing_is_parsed_when_nothing_could_link():
    """Most turns have no verb-form correction, and they cost no second parse."""
    text = "She is teacher."
    assert forms.link(text, [at(text, "is teacher", "is a teacher", "ARTICLE")]) == [
        forms.UNLINKED
    ]


# ── Accuracy per form ───────────────────────────────────────────────────────


def test_accuracy_is_right_over_said_and_needed():
    used = {PS: 5, PAST: 2, PP: 1, "main_clause": 4}
    links = [Link(PAST, PP), Link(PS, PAST), Link(PP, PP), Link(None, PC)]
    found = {form: tally.as_dict() for form, tally in forms.tally(used, links).items()}
    assert found == {
        PS: {"used": 5, "right": 4, "wrong": 1, "missed": 0, "accuracy": 0.8},
        PC: {"used": 0, "right": 0, "wrong": 0, "missed": 1, "accuracy": 0.0},
        PAST: {"used": 2, "right": 1, "wrong": 1, "missed": 1, "accuracy": 0.3333},
        PP: {"used": 1, "right": 0, "wrong": 1, "missed": 1, "accuracy": 0.0},
    }


def test_a_form_never_needed_or_used_is_absent():
    assert forms.tally({"main_clause": 2}, []) == {}


def test_a_labelled_turn_is_tallied_by_hand():
    """Four corrections in one turn, and every figure worked out on paper first."""
    text = (
        "Yesterday I go to the office and I finished the report. I never went to "
        "London, but my sister work there and she is loving it. I will travel there "
        "next year."
    )
    corrections = [
        at(text, "go", "went"),
        at(text, "never went", "have never been"),
        at(text, "my sister work", "my sister works", SVA),
        at(text, "is loving", "loves"),
    ]
    doc = grammar.parse(text)
    found = {
        form: tally.as_dict()
        for form, tally in forms.tally(
            grammar.count(doc), forms.link(text, corrections, doc)
        ).items()
    }
    assert found == {
        PS: {"used": 2, "right": 0, "wrong": 2, "missed": 1, "accuracy": 0.0},
        PC: {"used": 1, "right": 0, "wrong": 1, "missed": 0, "accuracy": 0.0},
        PAST: {"used": 2, "right": 1, "wrong": 1, "missed": 1, "accuracy": 0.3333},
        PP: {"used": 0, "right": 0, "wrong": 0, "missed": 1, "accuracy": 0.0},
        WILL: {"used": 1, "right": 1, "wrong": 0, "missed": 0, "accuracy": 1.0},
    }
