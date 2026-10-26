"""English the person wrote, checked: the dictionary, the rules and the model together,
every fix located in the person's own words, and Corrected built from all of them."""

from services.check import SPELLING, check
from tests.say_provider import SayProvider

# "dont" becomes "don't", one character longer, so everything after it moves: the
# grammar is found in the respelled text and has to land back on the person's words.
TEXT = "I dont know, and she work in a bank. I send it to Laura."


def labelled(model: SayProvider) -> SayProvider:
    model.replies_by_kind["errors"] = {
        "errors": [
            {
                "category": "VERB_TENSE",
                "subcategory": "missing_past_marker",
                "original": "I send it",
                "correction": "I sent it",
                "explanation": "It happened already.",
                "confidence": 0.9,
            },
            # The rule's own correction, which the model makes too: superseded, not
            # counted twice.
            {
                "category": "SUBJECT_VERB_AGREEMENT",
                "subcategory": "third_person_s",
                "original": "she work",
                "correction": "she works",
                "explanation": "Third person takes -s.",
                "confidence": 0.9,
            },
        ]
    }
    return model


async def test_spelling_grammar_rules_and_the_model_each_fix_what_is_theirs():
    checked = await check(labelled(SayProvider()), TEXT)

    assert [(f.original, f.correction, f.detector) for f in checked.fixes] == [
        ("dont", "don't", "dictionary"),
        ("she work", "she works", "rule"),
        ("I send it", "I sent it", "llm"),
    ]
    assert checked.fixes[0].category == SPELLING
    assert (
        checked.corrected
        == "I don't know, and she works in a bank. I sent it to Laura."
    )


async def test_every_fix_points_at_the_persons_own_words():
    checked = await check(labelled(SayProvider()), TEXT)

    for fix in checked.fixes:
        assert TEXT[fix.span_start : fix.span_end] == fix.original


async def test_the_model_sees_the_text_with_its_spelling_already_fixed():
    model = labelled(SayProvider())

    await check(model, TEXT)

    marked = model.calls[-1][-1].content
    assert "don't" in marked
    assert "dont" not in marked


async def test_a_proposal_a_rule_already_made_is_kept_out_and_recorded():
    checked = await check(labelled(SayProvider()), TEXT)

    assert sum(1 for f in checked.fixes if f.original == "she work") == 1
    assert [r["reason"] for r in checked.rejects] == ["superseded_by_rule"]


async def test_with_the_model_down_the_dictionary_and_the_rules_still_check_and_say_so():
    model = SayProvider()
    model.down.add("errors")

    checked = await check(model, TEXT)

    assert [f.detector for f in checked.fixes] == ["dictionary", "rule"]
    assert (
        checked.corrected
        == "I don't know, and she works in a bank. I send it to Laura."
    )
    assert "did not answer" in checked.detail


async def test_clean_english_comes_back_as_it_was():
    checked = await check(
        SayProvider(), "  I finished the report and sent it this morning.  "
    )

    assert checked.fixes == []
    assert checked.corrected == "I finished the report and sent it this morning."
    assert checked.forms
