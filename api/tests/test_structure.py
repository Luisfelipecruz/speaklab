"""How an answer is built: the counter against sentences written for it.

The words with another use are the risk, so each has sentences that read it both ways
(`tests/answer_labels.py` `READINGS`). The development answers are asserted on a few
shapes the counter has to get right. How the counter does on the held-out answers is a
measurement, and it is in `tests/test_answer_measures.py`, which reports it to the
evaluation harness.
"""

import re

import pytest

from services import structure
from tests.answer_labels import DEVELOPMENT, HELD_OUT, KINDS, READINGS


def kinds_at(text: str, word: str) -> set[str]:
    """What the counter found overlapping the first occurrence of `word`."""
    match = re.search(r"(?<![\w'])" + re.escape(word) + r"(?![\w'])", text)
    assert match, (text, word)
    return {
        item.kind
        for item in structure.analyse(text).found
        if item.start < match.end()
        and match.start() < item.end
        and item.kind in structure.FUNCTIONS
    }


@pytest.mark.parametrize("sentence,word,expected", READINGS)
def test_a_word_with_another_use_is_read_from_the_parse(sentence, word, expected):
    found = kinds_at(sentence, word)
    assert found == ({expected} if expected else set()), (sentence, found)


def test_every_marked_stretch_is_where_the_label_says():
    for answer in DEVELOPMENT + HELD_OUT:
        for mark in answer.marks:
            assert mark.kind in KINDS
            mark.span(answer.transcript)


def test_the_held_out_set_can_decide_every_measure():
    """Each kind has enough marked instances for its bar to be a measurement."""
    for kind in KINDS:
        marked = sum(len(answer.of(kind)) for answer in HELD_OUT)
        assert marked >= structure.MIN_INSTANCES, (kind, marked)


# ── Sentences and words ─────────────────────────────────────────────────────


def test_a_sentence_is_the_recognisers_punctuation():
    text = "We rolled back. Why? Because the config was wrong! It took 2.5 hours"
    assert len(structure.sentences(text)) == 4


def test_a_stray_filler_is_not_a_sentence():
    assert len(structure.sentences("Um. We rolled back.")) == 1


def test_words_per_sentence_leaves_the_fillers_out():
    counted = structure.analyse("Um, we rolled back. Uh, it worked again.")
    assert counted.words == 6
    assert counted.sentences == 2
    assert counted.words_per_sentence == 3.0
    assert counted.longest_sentence == 3


def test_an_empty_answer_counts_nothing():
    counted = structure.analyse("")
    assert counted.words == counted.sentences == 0
    assert counted.words_per_sentence is None
    assert counted.found == ()
    assert set(counted.signposts) == set(structure.FUNCTIONS)


# ── The shapes the counter has to get right ─────────────────────────────────


def test_so_opening_an_answer_is_not_a_signpost():
    counted = structure.analyse("So the release failed. We rolled back.")
    assert counted.signposts[structure.REASON] == 0
    assert counted.signposts[structure.CLOSE] == 0


def test_so_before_a_close_is_counted_once():
    counted = structure.analyse("It failed. We fixed it. So overall, it was fine.")
    assert counted.signposts[structure.CLOSE] == 1
    assert counted.signposts[structure.REASON] == 0


def test_so_opening_the_last_sentence_sums_up():
    counted = structure.analyse(
        "Postgres is relational. We need transactions. So Postgres is the safer choice."
    )
    assert counted.signposts[structure.CLOSE] == 1


def test_so_opening_a_sentence_in_the_middle_is_a_result():
    counted = structure.analyse(
        "The field was missing. So every payment failed. We rolled back."
    )
    assert counted.signposts[structure.REASON] == 1
    assert counted.signposts[structure.CLOSE] == 0


def test_the_first_reason_is_a_step_and_not_a_reason():
    counted = structure.analyse(
        "The first reason is that the client changed the format."
    )
    assert counted.signposts[structure.SEQUENCE] == 1
    assert counted.signposts[structure.REASON] == 0


def test_a_word_said_twice_is_a_repeat():
    counted = structure.analyse(
        "We we changed the schema, and the the migration was slow."
    )
    assert counted.repeats == 2


def test_a_run_of_words_said_twice_is_one_repeat():
    counted = structure.analyse("I have a, I have a checklist.")
    assert counted.repeats == 1
    (repeat,) = [item for item in counted.found if item.kind == structure.REPEAT]
    assert repeat.text == "I have a, I have a"


def test_a_filler_between_the_copies_does_not_hide_a_repeat():
    assert structure.analyse("We, uh, we did not say anything.").repeats == 1


def test_a_grammatical_double_is_not_a_repeat_unless_there_is_a_pause():
    assert structure.analyse("I know that that is wrong.").repeats == 0
    assert structure.analyse("A column that, that was missing.").repeats == 1


def test_the_same_word_across_a_full_stop_is_not_a_repeat():
    assert structure.analyse("It failed. Failed badly.").repeats == 0


def test_a_phrase_broken_off_on_a_word_that_cannot_end_it_is_a_restart():
    counted = structure.analyse("Their API had no, there was no documentation.")
    assert counted.restarts == 1


def test_a_verb_that_comes_back_after_the_pause_is_a_restart():
    counted = structure.analyse("Then in the interview, Lee was, he was honest.")
    assert counted.restarts == 1


def test_two_complete_clauses_are_not_a_restart():
    counted = structure.analyse("We tested it, we shipped it, and it worked.")
    assert counted.restarts == 0


def test_an_ordinary_pause_after_a_signpost_is_not_a_restart():
    counted = structure.analyse(
        "First of all, because of that, the site was down. For example, the orders page."
    )
    assert counted.restarts == 0


def test_the_counts_are_the_found_items():
    for answer in DEVELOPMENT[:6]:
        counted = structure.analyse(answer.transcript)
        assert sum(counted.signposts.values()) + counted.repeats + counted.restarts == (
            len(counted.found)
        )
        for item in counted.found:
            assert answer.transcript[item.start : item.end] == item.text
