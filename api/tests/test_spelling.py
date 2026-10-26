"""Spelling by a dictionary: what it corrects, and everything it must leave alone.

The dictionary is loaded once for the module, about a second.
"""

import pytest

from services.spelling import check


def corrections(text: str, known=()):
    return [(m.original, m.correction) for m in check(text, known)]


@pytest.mark.parametrize(
    ("typed", "meant"),
    [
        ("recieved", "received"),
        ("untill", "until"),
        ("tomorow", "tomorrow"),
        ("definately", "definitely"),
        ("seperate", "separate"),
        ("occured", "occurred"),
        ("neccessary", "necessary"),
        ("reccomend", "recommend"),
        # Where the commonest near word is the wrong one: a letter left out, or two
        # swapped, is the likelier mistake.
        ("realy", "really"),
        ("wich", "which"),
        ("finaly", "finally"),
        ("teh", "the"),
        ("wierd", "weird"),
        # From the table: typed without the apostrophe, or run together.
        ("dont", "don't"),
        ("alot", "a lot"),
        ("im", "I'm"),
    ],
)
def test_a_common_misspelling_is_found_with_the_word_it_meant(typed, meant):
    assert corrections(f"we said {typed} there") == [(typed, meant)]


def test_where_each_one_is_is_kept_as_an_offset_into_the_text():
    text = "I recieved it tomorow"
    found = check(text)

    assert [text[m.span_start : m.span_end] for m in found] == ["recieved", "tomorow"]


def test_a_capital_at_the_start_of_a_sentence_is_kept_in_the_correction():
    assert corrections("Dont worry. Teh plan is fine.") == [
        ("Dont", "Don't"),
        ("Teh", "The"),
    ]


def test_correctly_spelled_english_is_left_alone():
    text = (
        "I'm writing to let you know that the client report will be delayed until "
        "Thursday, because we're still waiting for the data."
    )
    assert corrections(text) == []


def test_the_words_of_software_and_office_work_are_known():
    text = (
        "We moved the backend and frontend repo config to async webhooks during "
        "onboarding, then fixed the dashboard; the hotfix and the rollback are in the "
        "changelog."
    )
    assert corrections(text) == []


def test_names_acronyms_and_mixed_case_are_never_checked():
    assert corrections("Ask Omar and Grafna on Jira about the API and GitHub.") == []


def test_a_name_that_opens_a_sentence_is_skipped_once_it_is_known():
    # Opening a sentence, a capital proves nothing; a name already seen does.
    assert corrections("Teh said yes.") == [("Teh", "The")]
    assert corrections("Teh said yes.", known=["Teh"]) == []


def test_links_addresses_handles_code_and_quotes_are_never_checked():
    text = (
        "See https://grafna.acme.io/d/latencia, mail luis.cruz@ejemplo.com, ping @omar, "
        'run `npm run lnt` and read "recieved" as written.'
    )
    assert corrections(text) == []


def test_words_with_digits_accents_or_two_letters_are_never_checked():
    assert corrections("Sofía is at the café at 10am, ot so.") == []
