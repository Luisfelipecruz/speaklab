"""Sorting a difference into a figure, an ending, or a different word.

The fixture is not invented. It is every substitution from four takes of one speaker's
own script, read out of the database — twenty-five pairs, each one a word they said and
the word the recogniser wrote. Made-up pairs would test the rules against the
imagination that wrote them; these test them against the only speech this feature has
ever been used on.

Each pair is asserted on its own rather than only in the totals, because two mistakes
that cancel produce the right totals and the wrong screen, and because a reader who
disagrees with one of these labels should be able to find it and argue about that one.
"""

from __future__ import annotations

import pytest

from services.fidelity_kinds import DIFFERENT_WORD, ENDING, FIGURE, classify
from services.numbers import NUMBER_WORDS, value_of

# Every substitution in the four takes, with the kind it is. `publishes` heard as
# `pushes` is a different word, not an ending: both happen to end in `es`, and what
# changed is the verb. `events` heard as `even` is an ending: the word is there and its
# end is gone.
REAL_PAIRS: list[tuple[str, str, str]] = [
    ("calls", "call", ENDING),
    ("pile", "peels", DIFFERENT_WORD),
    ("up", "out", DIFFERENT_WORD),
    ("cost", "caused", DIFFERENT_WORD),
    ("eleven", "11", FIGURE),
    ("checkout", "outs", DIFFERENT_WORD),
    ("anybody", "nobody", DIFFERENT_WORD),
    ("we're", "are", ENDING),
    ("event", "evan", DIFFERENT_WORD),
    ("bus", "voss", DIFFERENT_WORD),
    ("services", "service", ENDING),
    ("publishing", "publish", ENDING),
    ("ten", "10", FIGURE),
    ("the", "they", DIFFERENT_WORD),
    ("events", "even", ENDING),
    ("publishes", "pushes", DIFFERENT_WORD),
    ("notifications", "notification", ENDING),
    ("four", "for", DIFFERENT_WORD),
    ("fewer", "few", ENDING),
    ("like", "light", DIFFERENT_WORD),
    ("we'd", "have", ENDING),
    ("the", "to", DIFFERENT_WORD),
    ("off", "trait", DIFFERENT_WORD),
    ("is", "of", DIFFERENT_WORD),
    ("or", "of", DIFFERENT_WORD),
]


@pytest.mark.parametrize(("expected", "heard", "kind"), REAL_PAIRS)
def test_every_real_difference_is_sorted_the_way_a_person_would(expected, heard, kind):
    assert classify(expected, heard) == kind


def test_the_four_takes_split_eight_fifteen_and_two():
    kinds = [classify(expected, heard) for expected, heard, _ in REAL_PAIRS]

    assert len(kinds) == 25
    assert kinds.count(ENDING) == 8
    assert kinds.count(DIFFERENT_WORD) == 15
    assert kinds.count(FIGURE) == 2


def test_a_number_said_correctly_is_not_a_difference_whichever_side_wrote_it():
    assert classify("eleven", "11") == FIGURE
    assert classify("11", "eleven") == FIGURE
    assert classify("fourth", "4th") == FIGURE


def test_a_number_against_a_different_number_is_still_a_difference():
    assert classify("eleven", "12") == DIFFERENT_WORD
    assert classify("four", "for") == DIFFERENT_WORD


def test_an_ending_is_the_same_difference_read_from_either_side():
    assert classify("call", "calls") == ENDING
    assert classify("calls", "call") == ENDING


def test_two_short_words_that_start_alike_are_not_one_word():
    # "the" and "they" share three characters, which is not a stem.
    assert classify("the", "they") == DIFFERENT_WORD
    assert classify("up", "out") == DIFFERENT_WORD


def test_a_word_is_never_sorted_against_nothing():
    assert classify("", "call") == DIFFERENT_WORD
    assert classify("call", "") == DIFFERENT_WORD


def test_a_number_word_is_worth_what_it_says_and_a_word_is_worth_nothing():
    assert value_of("eleven") == 11
    assert value_of("11") == 11
    assert value_of("11th") == 11
    assert value_of("TEN") == 10
    assert value_of("often") is None
    assert value_of("") is None


def test_the_harness_and_this_table_agree_about_which_words_are_numbers():
    """The evaluation harness asks a different question with the same list of words.

    It cannot import this module — it must not depend on the system it measures — so the
    two lists are separate and this is what stops them drifting apart in silence.
    """
    from tests.eval_out import load_harness

    harness = load_harness("scoring")
    for word in NUMBER_WORDS:
        assert harness.names_a_figure(f"it was {word} of them") == word, word
