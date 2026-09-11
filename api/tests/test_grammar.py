"""Which forms the parser finds, on sentences whose answer a teacher would agree with.

The vocabulary here is closed for a reason that these tests are the guard on: scenarios
declare the forms they are built to elicit **in these exact names**, so "the scenario
asked for the present perfect and none was produced" is a set difference rather than a
judgement. A detector that renamed a feature would break that comparison silently — the
form would be counted, the scenario would still report it missing, and nothing would look
wrong.

The parse is loaded once for the module. It costs a second and a half and every test here
needs it.
"""

import pytest

from services import grammar
from services.grammar import FEATURES


@pytest.fixture(scope="module", autouse=True)
def parser():
    return grammar.load()


def features(text: str) -> dict[str, int]:
    return grammar.analyse(text)


# ── Tense and aspect ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "sentence,feature",
    [
        ("I work in a bank.", "present_simple"),
        ("I am working on the migration.", "present_continuous"),
        ("I finished the report yesterday.", "past_simple"),
        ("They were waiting outside when I arrived.", "past_continuous"),
        ("I have worked here since 2019.", "present_perfect"),
        ("She has been working here for two years.", "present_perfect_continuous"),
        ("I had finished the report before he called.", "past_perfect"),
        ("I had been waiting for an hour when she arrived.", "past_perfect_continuous"),
        ("I will send it tomorrow.", "future_will"),
        ("I am going to send it tomorrow.", "going_to_future"),
    ],
)
def test_each_tense_and_aspect_is_recognised(sentence, feature):
    assert features(sentence).get(feature), f"{feature} not found in {sentence!r}"


def test_going_to_the_office_is_not_the_going_to_future():
    """ "I'm going to work" and "I'm going to the office" differ by whether a verb
    follows. Counting the second as a future would credit a form nobody produced."""
    assert not features("I am going to the office.").get("going_to_future")
    assert features("I am going to the office.").get("present_continuous")


def test_a_going_to_future_is_counted_once():
    """It spans two verbs — the tensed `going` and the meaning-carrying complement — and
    a naive pass over verb phrases counts it from both ends."""
    assert (
        features("Then we are going to use this certificate.")["going_to_future"] == 1
    )


def test_an_ing_form_under_another_verb_is_not_the_continuous():
    """`start checking` is a non-finite complement. Progressive needs the auxiliary."""
    assert not features("We can start checking the endpoint.").get("present_continuous")


def test_a_modal_phrase_is_the_modal_and_not_also_a_tense():
    """ "would have told" is a modal perfect. Counting it as a present perfect too would
    put a form the speaker did not produce into their repertoire."""
    found = features("If I had known I would have told you.")
    assert found.get("modal_would")
    assert not found.get("present_perfect")


@pytest.mark.parametrize(
    "sentence,feature",
    [
        ("I don't have any blockers.", "present_simple"),
        ("Do you have more details about the price?", "present_simple"),
        ("She doesn't work on Fridays.", "present_simple"),
        ("I didn't finish the ticket.", "past_simple"),
        ("Did she leave, or did she stay?", "past_simple"),
    ],
)
def test_a_negative_or_a_question_is_counted_in_its_tense(sentence, feature):
    """The head is a bare infinitive and the tense is on `do`. Read from the head, every
    negative and every question in the simple tenses is a form nobody produced."""
    assert features(sentence).get(feature), f"{feature} not found in {sentence!r}"


def test_both_questions_joined_by_or_are_counted():
    assert features("Did she leave, or did she stay?")["past_simple"] == 2


def test_an_imperative_with_do_is_not_a_present_simple():
    """`Don't worry` has a finite `do` and no subject: it tells, it does not describe."""
    assert not features("Don't worry about the deposit.").get("present_simple")


@pytest.mark.parametrize(
    "sentence,feature,not_feature",
    [
        ("Is parking included in the price?", "present_simple", "past_simple"),
        ("The flat is located near the station.", "present_simple", "past_simple"),
        ("The flight has been cancelled.", "present_perfect", "past_perfect"),
        (
            "The kitchen is being painted this week.",
            "present_continuous",
            "past_simple",
        ),
        ("The house was built in 1990.", "past_simple", "present_simple"),
    ],
)
def test_a_passive_takes_its_tense_from_the_auxiliary(sentence, feature, not_feature):
    """The participle is past in form whatever the tense. Read from the head, every present
    passive is a past simple."""
    found = features(sentence)
    assert found.get(feature), f"{feature} not found in {sentence!r}"
    assert not found.get(not_feature), f"{not_feature} found in {sentence!r}"


def test_a_perfect_without_a_tense_is_not_a_perfect():
    """`Having finished` carries an aspect and no tense."""
    found = features("Having finished the report, I went home.")
    assert not found.get("present_perfect")
    assert found["past_simple"] == 1


def test_been_without_its_auxiliary_is_not_a_present_simple():
    """The tagger calls `been` a present-tense verb in `I been to Paris`."""
    assert not features("I been to Paris twice.").get("present_simple")


def test_a_verb_the_tagger_calls_an_auxiliary_still_heads_its_phrase():
    """`enjoy` in `I enjoy swimming` is tagged as the auxiliary of `swimming`."""
    found = features("I enjoy swimming in the sea.")
    assert found["present_simple"] == 1
    assert found["main_clause"] == 1


def test_the_phrases_are_the_forms_the_counts_count():
    """A correction is linked to a phrase; the phrase has to be one the repertoire counted."""
    text = (
        "Yesterday I finished the migration and I am going to deploy it tomorrow. "
        "I don't have any blockers, but the certificate has been uploaded and we "
        "could test it if you want. Did you see the dashboard?"
    )
    doc = grammar.parse(text)
    counted = {
        form: count
        for form, count in grammar.count(doc).items()
        if form in grammar.VERB_FORMS
    }
    phrased: dict[str, int] = {}
    for phrase in grammar.verb_phrases(doc):
        phrased[phrase.form] = phrased.get(phrase.form, 0) + 1
    assert phrased == counted


def test_a_going_to_phrase_holds_its_complement():
    """`going to deploy` is one future, and a correction to `deploy` is a correction to it."""
    doc = grammar.parse("I am going to deploy it tomorrow.")
    (phrase,) = grammar.verb_phrases(doc)
    assert phrase.form == "going_to_future"
    assert phrase.words == ("am", "going", "to", "deploy")


# ── Modality ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "sentence,feature",
    [
        ("Can I have a pet in the unit?", "modal_can"),
        ("Could you send me the contract?", "modal_could"),
        ("We should wait for the certificate.", "modal_should"),
        ("I would take the course.", "modal_would"),
        ("We must upload it today.", "modal_must"),
        ("It might rain later.", "modal_may_might"),
    ],
)
def test_each_modal_is_recognised(sentence, feature):
    assert features(sentence).get(feature)


# ── Structure ───────────────────────────────────────────────────────────────


def test_the_passive_is_counted_once_per_auxiliary():
    assert features("The certificate was uploaded by the team.")["passive_voice"] == 1


def test_coordinated_verbs_are_two_main_clauses():
    """The second one is a `conj`, not a ROOT. Missing it would understate the clause
    count that a subordination index is a ratio of."""
    found = features("I finished the ticket and I started the next one.")
    assert found["main_clause"] == 2
    assert found["past_simple"] == 2


def test_a_that_clause_is_subordinate():
    found = features("I think that we should wait.")
    assert found["main_clause"] == 1
    assert found["subordinate_clause"] == 1


def test_an_infinitive_complement_is_not_a_clause():
    """`to have a really good unit` has no tense. Counting every to-infinitive as
    subordination makes an infinitive-heavy sentence read as complex when it is not, and
    the subordination index is a ratio whose halves must mean the same thing."""
    found = features("It is difficult to have a really good unit here.")
    assert found.get("subordinate_clause", 0) == 0
    assert found["main_clause"] == 1


@pytest.mark.parametrize(
    "sentence,feature",
    [
        ("If it rains we will cancel the visit.", "conditional_1"),
        ("If I had more time I would take the course.", "conditional_2"),
        ("If I had known I would have told you.", "conditional_3"),
    ],
)
def test_the_three_conditionals_are_told_apart(sentence, feature):
    assert features(sentence).get(feature)


def test_an_if_clause_with_no_consequence_is_not_a_conditional():
    """ "if I can have one pet" inside a question is a question, not a conditional
    sentence — both halves have to be there."""
    found = features("I want to know if I can have one pet.")
    assert not any(found.get(f"conditional_{n}") for n in (1, 2, 3))


# ── Comparison, reported speech, duration, requests ─────────────────────────


def test_a_comparative_adjective_is_counted():
    assert features("This flat is more expensive than that one.")["comparatives"] == 1


def test_more_as_a_quantity_is_not_a_comparative():
    """ "I want to know more about the price" carries Degree=Cmp and compares nothing.
    Counting it would tell a scenario its comparative target was elicited when it was
    not."""
    assert not features("I want to know more about the price.").get("comparatives")


def test_at_least_is_not_a_superlative():
    """Superlative in form, an adverb of degree in use."""
    assert not features("We can test at least the endpoint.").get("superlatives")
    assert features("This is the best flat we have seen.").get("superlatives")


def test_reported_speech_needs_a_reporting_verb_and_a_clause():
    assert features("He said that the flat was available.").get("reported_speech")
    assert not features("He said hello.").get("reported_speech")


def test_duration_is_about_the_object_not_the_preposition():
    """ "for two years" is duration; "for us" is not, and both are the same word."""
    assert features("I have worked here for two years.").get("duration_for_since")
    assert not features("It could be great for us.").get("duration_for_since")


def test_a_polite_request_is_a_modal_question_addressed_to_you():
    assert features("Could you send me the contract?").get("polite_request")
    assert not features("Could I send you the contract?").get("polite_request")
    assert not features("She could send the contract.").get("polite_request")


# ── The vocabulary itself ───────────────────────────────────────────────────


def test_nothing_outside_the_declared_vocabulary_is_ever_produced():
    """A feature name the scenarios do not know is a form that can be counted and never
    matched against a target."""
    text = (
        "Yesterday I finished the migration and I am going to deploy it tomorrow. "
        "If I had more time I would have tested it, and the certificate was uploaded "
        "by the team, who said that it has been working for two years. Could you "
        "check the most recent one?"
    )
    produced = set(features(text))
    assert produced <= FEATURES, f"unknown features: {sorted(produced - FEATURES)}"


def test_every_form_a_seeded_scenario_declares_can_be_detected():
    """The set difference that makes "declared but never elicited" meaningful only works
    if the parser can produce every name a scenario uses."""
    import json
    from pathlib import Path

    seeds = Path(__file__).resolve().parents[1] / "seeds" / "scenarios.json"
    declared = {
        form
        for scenario in json.loads(seeds.read_text())
        for form in scenario.get("target_grammar", [])
    }
    assert declared <= FEATURES, f"no detector for: {sorted(declared - FEATURES)}"


def test_an_empty_transcript_produces_nothing():
    assert grammar.analyse("") == {}
    assert grammar.analyse("   ") == {}
