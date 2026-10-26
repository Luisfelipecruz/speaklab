"""Spanish or English, by the words: the decision that sends a text to be translated or
checked. Plain counts, so every case can be worked out by hand."""

import pytest

from services.language import common, decide, words_of


def test_the_two_lists_share_no_word_and_hold_about_three_hundred_each():
    english, spanish = common("en"), common("es")

    assert english.isdisjoint(spanish)
    assert 250 <= len(english) <= 400
    assert 250 <= len(spanish) <= 400


@pytest.mark.parametrize(
    "text",
    [
        "Laura, te escribo para avisarte que el informe se va a retrasar.",
        "Ya hice el deploy del PR, revísalo cuando puedas.",
        "tambien esta bien, nos vemos manana",
        "Gracias",
    ],
)
def test_spanish_is_taken_for_the_accounts_language(text):
    assert decide(text, "es").language == "es"


@pytest.mark.parametrize(
    "text",
    [
        "Hi Laura, I'm writing to let you know the report will be late.",
        "Can you review my pull request when you have time?",
        "Thanks!",
    ],
)
def test_english_is_taken_for_english(text):
    assert decide(text, "es").language == "en"


def test_a_tie_goes_to_the_accounts_language():
    # No common word of either: a name, and an abbreviation.
    tie = decide("Laura OK", "es")

    assert tie.shares == {"en": 0.0, "es": 0.0}
    assert tie.language == "es"


def test_accents_are_folded_so_a_text_typed_without_them_counts_the_same():
    with_accents = decide("también está bien, mañana", "es")
    without = decide("tambien esta bien, manana", "es")

    assert with_accents.shares == without.shares


def test_a_language_with_no_list_is_told_from_english_by_the_english_share():
    assert decide("Olá, tudo bem com você", "pt").language == "pt"
    assert decide("Could you send me the report today", "pt").language == "en"


def test_an_english_account_is_always_checked():
    assert decide("Hola, ¿qué tal?", "en").language == "en"


def test_words_are_counted_without_digits_and_with_apostrophes_kept():
    assert words_of("I'm at 9:30 with Q3") == ["i'm", "at", "with", "q"]
