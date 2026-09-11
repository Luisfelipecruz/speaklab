"""The rule layer: errors a parse can decide, proposed with no model in the room.

**Both halves of a rule are tested, and the second half is the one that matters.** A rule
that fires on "she work" is easy to write; a rule that fires on "she work" and stays
silent on "the team are playing", "two years is a long time" and "let him go" is the
whole job, because the reason this layer exists is precision. A proposal from here goes
into a learner's history with a confidence of 1.0 and no gate in front of it, so every
false positive it makes is one the product states as fact.

None of the sentences below comes from the golden set. A rule tuned against the set it is
scored on would measure its own fixture.

**Native English is the false-positive floor.** The LibriSpeech references, the seeded
reading passages and the persona briefs are English written or read by native speakers,
and the rule layer must find nothing in any of them. That is asserted, not reported: the
layer is deterministic, so a proposal on native text is a defect with a sentence attached
to it rather than a sample from a distribution.
"""

import pytest

from services import grammar, rules
from services.taxonomy import TAXONOMY
from tests.native_text import native_texts


@pytest.fixture(scope="module", autouse=True)
def parser():
    return grammar.load()


def proposals(text: str) -> list[rules.RuleError]:
    return rules.propose(grammar.parse(text))


def one(text: str) -> rules.RuleError:
    found = proposals(text)
    assert len(found) == 1, (
        f"expected one proposal in {text!r}, got "
        f"{[(f.accepted.original, f.accepted.correction) for f in found]}"
    )
    return found[0]


# ── What fires ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "sentence,original,correction",
    [
        ("she work in a bank", "she work", "she works"),
        ("my brother live in Madrid", "my brother live", "my brother lives"),
        ("he have two cars", "he have", "he has"),
        ("she don't like coffee", "she don't", "she doesn't"),
        (
            "the building don't have parking",
            "the building don't",
            "the building doesn't",
        ),
        ("everyone know the answer", "everyone know", "everyone knows"),
        (
            "the manager say that the price is fixed",
            "the manager say",
            "the manager says",
        ),
        ("if he come tomorrow we can talk", "he come", "he comes"),
        ("the kitchen have a big window", "the kitchen have", "the kitchen has"),
        ("it depend on the price", "it depend", "it depends"),
        ("I think it depend on the price", "it depend", "it depends"),
        ("the price include the parking", "the price include", "the price includes"),
        ("she go to the gym every day", "she go", "she goes"),
        ("he watch the news every night", "he watch", "he watches"),
        ("she study English at night", "she study", "she studies"),
        ("my mother cook very well", "my mother cook", "my mother cooks"),
        ("this apartment have a balcony", "this apartment have", "this apartment has"),
        ("the people is very friendly", "the people is", "the people are"),
        ("they works in the office", "they works", "they work"),
        ("my friends lives near here", "my friends lives", "my friends live"),
        ("the rooms is quite big", "the rooms is", "the rooms are"),
        ("we was very tired after the trip", "we was", "we were"),
        ("I has a question about the lease", "I has", "I have"),
        ("they doesn't want to wait", "they doesn't", "they don't"),
        ("we only supports two platforms", "we only supports", "we only support"),
        # A clause under "when" or "whether" is not a subjunctive.
        (
            "when the user disagree ask for evidence",
            "the user disagree",
            "the user disagrees",
        ),
        ("ask whether anything make it worse", "anything make", "anything makes"),
        # A number in front of a noun that is not a unit is a count, not an amount.
        (
            "three thousand people passes through it",
            "three thousand people passes",
            "three thousand people pass",
        ),
        # An auxiliary is not ambiguous about tense, whatever else is in the sentence.
        ("the user have described what went wrong", "the user have", "the user has"),
        # A past verb inside the complement is being reported, not narrated.
        ("I still thinks we were interrupted", "I still thinks", "I still think"),
    ],
)
def test_a_verb_that_does_not_agree_with_its_subject_is_proposed(
    sentence, original, correction
):
    found = one(sentence)
    assert found.accepted.category == "SUBJECT_VERB_AGREEMENT"
    assert found.accepted.subcategory == "third_person_s"
    assert found.accepted.original == original
    assert found.accepted.correction == correction


def test_an_inverted_question_is_corrected_on_the_auxiliary():
    """The auxiliary carries the tense in a question, so it is the word that agrees."""
    found = one("what time do the train leave")
    assert found.accepted.original == "do the train"
    assert found.accepted.correction == "does the train"


@pytest.mark.parametrize(
    "sentence,original,correction",
    [
        (
            "there is many people in the park",
            "there is many people",
            "there are many people",
        ),
        (
            "there are a problem with the heating",
            "there are a problem",
            "there is a problem",
        ),
        (
            "there is two bedrooms and a kitchen",
            "there is two bedrooms",
            "there are two bedrooms",
        ),
        (
            "there was three meetings today",
            "there was three meetings",
            "there were three meetings",
        ),
    ],
)
def test_there_agrees_with_what_follows_it(sentence, original, correction):
    found = one(sentence)
    assert found.accepted.category == "SUBJECT_VERB_AGREEMENT"
    assert found.accepted.subcategory == "there_is_are"
    assert found.accepted.original == original
    assert found.accepted.correction == correction


@pytest.mark.parametrize(
    "sentence,original,correction",
    [
        ("I am engineer", "I am engineer", "I am an engineer"),
        ("she is teacher at the school", "she is teacher", "she is a teacher"),
        ("I'm software engineer", "I'm software engineer", "I'm a software engineer"),
        ("I work as teacher in a school", "work as teacher", "work as a teacher"),
        (
            "it is very good apartment",
            "it is very good apartment",
            "it is a very good apartment",
        ),
        ("this is big problem for me", "this is big problem", "this is a big problem"),
        ("it's nice place to live", "it's nice place", "it's a nice place"),
        ("it is interesting job", "it is interesting job", "it is an interesting job"),
        ("you are good teacher", "you are good teacher", "you are a good teacher"),
        ("it is useful tool", "it is useful tool", "it is a useful tool"),
        # A noun ending in -ing that is a thing, not an activity.
        ("it is small thing", "it is small thing", "it is a small thing"),
        ("it was good meeting", "it was good meeting", "it was a good meeting"),
    ],
)
def test_a_singular_noun_with_no_article_is_proposed(sentence, original, correction):
    found = one(sentence)
    assert found.accepted.category == "ARTICLE"
    assert found.accepted.subcategory == "missing_indefinite"
    assert found.accepted.original == original
    assert found.accepted.correction == correction


def test_a_superlative_takes_the_definite_article():
    """ "The best option" and not "a best option": the article a rule inserts is decided
    by the adjective, and inserting the wrong one would be a correction that is itself
    an error."""
    found = one("it is best option for us")
    assert found.accepted.subcategory == "missing_definite"
    assert found.accepted.correction == "it is the best option"


def test_two_errors_in_one_sentence_are_both_proposed():
    found = proposals("he is doctor and she is nurse")
    assert [f.accepted.correction for f in found] == [
        "he is a doctor",
        "she is a nurse",
    ]


# ── What stays silent ───────────────────────────────────────────────────────
#
# Grammatical English, most of it chosen because it looks like one of the patterns above
# to a rule written carelessly. Each group names the trap.

CORRECT = [
    # Agreement that is right.
    "she works in a bank",
    "my parents live in Madrid",
    "the kids play outside after school",
    "everybody knows the answer",
    "does she work here",
    "where do they live",
    "how much does it cost",
    "she has been working here for two years",
    "the price of the apartments is high",
    "I think the rent includes the parking",
    "you are right about that",
    "here are the keys",
    "here is the key",
    # Coordinated subjects are plural, and a few coordinations are singular idioms.
    "my brother and my sister live in Madrid",
    "fish and chips is my favourite meal",
    # Collective nouns: plural agreement is standard British English.
    "the team are playing well",
    "my family are coming for dinner",
    "the police are outside",
    "the staff are very helpful",
    # Partitives and quantities agree with what they measure.
    "a lot of people are here",
    "one of my friends lives here",
    "each of them has a key",
    "none of the rooms are ready",
    "most of the people are here",
    "the majority of people agree",
    "the number of rooms is small",
    # A plural measurement is one amount.
    "two years is a long time",
    "ten dollars is enough",
    # Nouns that end in s and are singular.
    "the news is good",
    "physics is hard",
    # Relative clauses: the relative pronoun agrees with a noun the rule does not chase.
    "the people who live here are friendly",
    "the thing that he likes is the view",
    "who lives in this unit",
    # Bare verbs after causatives and in the subjunctive are not agreement errors.
    "let him go",
    "make it work",
    "I suggest that he go home",
    "it is important that she be on time",
    "if he were rich he would buy it",
    "I wish it were true",
    # Past context: a bare verb here is a missing past marker, not a missing -s, and a rule
    # that cannot tell which must say nothing.
    "yesterday she go to the office",
    "I finished the report and she send it to the client",
    "last week my brother visit me",
    # There is, there are.
    "there is a kitchen and two bedrooms",
    "there are a kitchen and a bathroom",
    "there are a lot of options",
    "there is a lot of noise at night",
    "there were a couple of problems",
    "there's two bedrooms upstairs",
    "there is a problem with the heating",
    "there are many people in the park",
    # Articles that are right, or not needed.
    "I am an engineer",
    "we are a team",
    "they are good people",
    "it is a very good apartment",
    "it is my car",
    "it is Maria's car",
    "this is the kitchen",
    "he is the best",
    "it is best to wait",
    # Uncountable nouns take no article.
    "it is good news",
    "it is hard work",
    "that is good advice",
    "it is important information",
    "it is good practice",
    "it is great fun",
    "it's nice weather today",
    # After a noun subject an adjective does not settle countability.
    "the output may be simple text",
    "the rent is good value",
    "the contract is long term",
    "the flat is on the second floor",
    "the view is the main reason",
    # A gerund is an activity, and uncountable.
    "it is good training",
    "it was hard cleaning",
    # Nouns that are adjectives here, and time expressions.
    "it's going to be long term",
    "I work full time",
    "it is next week",
    "the meeting is next week",
    "it is time to go",
    # Roles that take no article.
    "I am part of the team",
    "he is head of the department",
    "she is president",
    "I work as part of a team",
    "I am home",
    "I am fine",
    "I am Spanish",
    "I'm Luis",
    "this is fun",
    "that is life",
    # Questions and requests from the scenarios.
    "Can you tell me more about the amenities?",
    "I want to know more about the price",
    "Could you send me the contract?",
    # Recogniser-shaped: lowercase, no punctuation, one long run.
    "good morning team my update for today is that I completed the user story and I am "
    "going to work on the next one",
    "whoever wants it can take it",
    "what matters is the price",
    # Shapes from native prose that read like errors to a careless rule.
    # A capitalised plural is a name, and a product takes a singular verb.
    "Requests is available on the package index",
    "Teams is where we have the standup",
    # A proper noun with "the" in front of it is modifying the next noun.
    "The Linux build files need to be produced in the container",
    # An adjective the tagger read as a noun.
    "It's super lightweight and works with any version",
    # A comma, or a conjunction, between a noun and a verb is two clauses run together.
    "the old color works with the new terminal, the classic terminal is limited",
    "Is there parking for my? Car or do I need a permit",
    # A curly apostrophe is still a contraction.
    "I’m sorry to hear that",
    # A capital on a verb after its subject is a sentence the tokeniser ran on into.
    "her real problem was the letter L. Collect the flowers and follow the trail",
]


@pytest.mark.parametrize("sentence", CORRECT)
def test_nothing_is_proposed_in_grammatical_english(sentence):
    found = proposals(sentence)
    assert not found, (
        f"{sentence!r} is grammatical and the rule layer proposed "
        f"{[(f.rule, f.accepted.original, f.accepted.correction) for f in found]}"
    )


# ── What every proposal carries ─────────────────────────────────────────────


def test_every_rule_files_under_a_label_the_taxonomy_has():
    """No gate stands in front of a rule's proposal, so the gate's first check is done
    here instead, once, over every label a rule can emit."""
    for category, subcategory in rules.LABELS:
        assert category in TAXONOMY
        assert subcategory in TAXONOMY[category]


def test_a_proposal_points_at_the_words_it_quotes():
    text = "Yesterday was fine. Now she work in a bank and it is very good job."
    for found in proposals(text):
        accepted = found.accepted
        assert text[accepted.span_start : accepted.span_end] == accepted.original
        assert accepted.confidence == 1.0
        assert accepted.explanation


def test_a_correction_keeps_the_speakers_capitals():
    found = one("My brother live in Madrid")
    assert found.accepted.correction == "My brother lives"


def test_the_word_a_correction_puts_in_is_named():
    """What a model's duplicate of this proposal has to contain for the two to be the
    same correction. See `services/errors.py`."""
    assert one("she work in a bank").replacement == "works"
    assert one("I am engineer").replacement == "an"


def test_an_empty_transcript_proposes_nothing():
    assert rules.propose(grammar.parse("")) == []
    assert rules.propose(None) == []


# ── Native English, asserted ────────────────────────────────────────────────


def test_native_english_produces_no_proposals():
    texts = native_texts()
    words = sum(len(text.split()) for _, text in texts)
    assert words > 1500, f"only {words} words of native text were found"

    fired = [
        (where, found.rule, found.accepted.original)
        for where, text in texts
        for found in proposals(text)
    ]
    assert not fired, f"proposals on native English, over {words} words: {fired}"
