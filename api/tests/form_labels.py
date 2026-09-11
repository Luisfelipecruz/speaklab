"""Hand-labelled corrections, each with the verb form it was said in and the one it needs.

Every case names two forms: the one the learner's words were said in, and the one the
correction puts in their place. Either can be absent — `She going` says no finite form at
all, and `enjoy to swim` corrects a complement no tense lives in. The labels are what a
teacher would write, not what the parser happens to produce.

Three sets, and they are not the same kind of evidence:

- `LABELLED` is the development set. The join in `services/forms.py` was built against it,
  so every case in it passes, and that says nothing about text it has not seen.
- `HELD_OUT` has never changed the join. Half of it is written the way the recogniser
  writes — lower case, no punctuation, sentences run together — because that is what the
  join is given in the product. The rate on it is the measurement.
- `GOLDEN_FORMS` labels the golden error set's real learner turns.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from services import forms

PS, PC = "present_simple", "present_continuous"
PAST, PASTC = "past_simple", "past_continuous"
PP, PPC = "present_perfect", "present_perfect_continuous"
PASTP, PASTPC = "past_perfect", "past_perfect_continuous"
WILL, GOING = "future_will", "going_to_future"

VT, SVA, OM = "VERB_TENSE", "SUBJECT_VERB_AGREEMENT", "OMISSION"


@dataclass(frozen=True)
class Case:
    transcript: str
    quote: str
    correction: str
    category: str
    form: str | None
    corrected_form: str | None

    @property
    def span_start(self) -> int:
        assert self.transcript.count(self.quote) == 1, self.quote
        return self.transcript.index(self.quote)

    @property
    def span_end(self) -> int:
        return self.span_start + len(self.quote)

    @property
    def label(self) -> forms.Link:
        return forms.Link(self.form, self.corrected_form)


LABELLED = [
    # The tense the moment needs, and a different one said.
    Case("Yesterday I go to the cinema with my friends.", "go", "went", VT, PS, PAST),
    Case(
        "Last week we visit my grandmother in Seville.",
        "visit",
        "visited",
        VT,
        PS,
        PAST,
    ),
    Case("I complete the report two hours ago.", "complete", "completed", VT, PS, PAST),
    Case("I never went to London.", "never went", "have never been", VT, PAST, PP),
    Case(
        "Did you ever eat paella?",
        "Did you ever eat",
        "Have you ever eaten",
        VT,
        PAST,
        PP,
    ),
    Case("I live in Madrid since 2019.", "live", "have lived", VT, PS, PP),
    Case("I work here for five years now.", "work", "have worked", VT, PS, PP),
    Case("I am here since Monday.", "am", "have been", VT, PS, PP),
    Case("I have seen him yesterday at the station.", "have seen", "saw", VT, PP, PAST),
    Case(
        "We have finished the project last week.",
        "have finished",
        "finished",
        VT,
        PP,
        PAST,
    ),
    Case(
        "When have you arrived in Spain?",
        "have you arrived",
        "did you arrive",
        VT,
        PP,
        PAST,
    ),
    Case("I am knowing the answer.", "am knowing", "know", VT, PC, PS),
    Case("She is having two children.", "is having", "has", VT, PC, PS),
    Case(
        "I am working here since 2020.", "am working", "have been working", VT, PC, PPC
    ),
    Case("Right now I work on the new report.", "work", "am working", VT, PS, PC),
    Case(
        "At eight o'clock yesterday I watched TV, so I did not hear the phone.",
        "watched",
        "was watching",
        VT,
        PAST,
        PASTC,
    ),
    Case(
        "When I arrived, the film already started.",
        "already started",
        "had already started",
        VT,
        PAST,
        PASTP,
    ),
    Case(
        "I was studying for three hours when you called.",
        "was studying",
        "had been studying",
        VT,
        PASTC,
        PASTPC,
    ),
    # Conditionals and the future: the form each half of the sentence needs.
    Case("If I will have time, I will call you.", "will have", "have", VT, WILL, PS),
    Case(
        "If I would have known, I would have come.",
        "would have known",
        "had known",
        VT,
        "modal_would",
        PASTP,
    ),
    Case(
        "If it rains tomorrow, we would stay at home.",
        "would stay",
        "will stay",
        VT,
        "modal_would",
        WILL,
    ),
    Case(
        "I will going to visit my parents next weekend.",
        "will going",
        "am going",
        VT,
        WILL,
        GOING,
    ),
    Case(
        "Don't worry, I carry your bags for you.", "carry", "will carry", VT, PS, WILL
    ),
    Case("He told me that he is tired.", "is", "was", VT, PS, PAST),
    Case(
        "She said she will come to the party.",
        "will come",
        "would come",
        VT,
        WILL,
        "modal_would",
    ),
    # The right form, built wrongly: said and needed are the same form.
    Case(
        "I can to swim very well.",
        "can to swim",
        "can swim",
        VT,
        "modal_can",
        "modal_can",
    ),
    Case(
        "You must to wear a helmet here.",
        "must to wear",
        "must wear",
        VT,
        "modal_must",
        "modal_must",
    ),
    Case(
        "He should goes home now.",
        "should goes",
        "should go",
        VT,
        "modal_should",
        "modal_should",
    ),
    Case(
        "I could went with you.",
        "could went",
        "could go",
        VT,
        "modal_could",
        "modal_could",
    ),
    Case("I have went there twice.", "have went", "have gone", VT, PP, PP),
    Case("She has broke the window.", "has broke", "has broken", VT, PP, PP),
    Case(
        "I didn't went to school yesterday.", "didn't went", "didn't go", VT, PAST, PAST
    ),
    Case("Did you saw the film?", "Did you saw", "Did you see", VT, PAST, PAST),
    # A verb error that no tense lives in.
    Case(
        "I enjoy to swim in the sea.", "enjoy to swim", "enjoy swimming", VT, None, None
    ),
    Case(
        "She suggested to go to the beach.",
        "suggested to go",
        "suggested going",
        VT,
        None,
        None,
    ),
    Case("I look forward to see you soon.", "to see", "to seeing", VT, None, None),
    # Agreement is an error in the form the verb is in.
    Case(
        "My sister work in a bank near the station.",
        "My sister work",
        "My sister works",
        SVA,
        PS,
        PS,
    ),
    Case(
        "There is many people in the square.",
        "There is many",
        "There are many",
        SVA,
        PS,
        PS,
    ),
    Case("The people is very friendly here.", "people is", "people are", SVA, PS, PS),
    Case("She have two brothers and a sister.", "She have", "She has", SVA, PS, PS),
    Case(
        "My parents was at home all day.",
        "parents was",
        "parents were",
        SVA,
        PAST,
        PAST,
    ),
    Case("He don't know the answer.", "He don't", "He doesn't", SVA, PS, PS),
    Case(
        "Everybody know the rules of the game.",
        "Everybody know",
        "Everybody knows",
        SVA,
        PS,
        PS,
    ),
    Case(
        "I think that she go home early.",
        "think that she go",
        "think that she goes",
        SVA,
        PS,
        PS,
    ),
    # A missing auxiliary or copula: nothing finite said, a form needed.
    Case("She going to the shop now.", "She going", "She is going", OM, None, PC),
    Case("I been to Paris twice.", "I been", "I have been", OM, None, PP),
    Case("We waiting for the bus.", "We waiting", "We are waiting", OM, None, PC),
    Case("She very happy today.", "She very happy", "She is very happy", OM, None, PS),
    Case(
        "My brother a doctor in Valencia.",
        "My brother a doctor",
        "My brother is a doctor",
        OM,
        None,
        PS,
    ),
    Case(
        "What you want to eat tonight?", "What you want", "What do you want", OM, PS, PS
    ),
    # Errors near a verb that are not errors in its form.
    Case(
        "I did a mistake in the exam.",
        "did a mistake",
        "made a mistake",
        "LEXICAL_CHOICE",
        None,
        None,
    ),
    Case(
        "We arrived to Madrid at night.",
        "arrived to Madrid",
        "arrived in Madrid",
        "PREPOSITION",
        None,
        None,
    ),
    Case(
        "I don't know where is it.",
        "where is it",
        "where it is",
        "WORD_ORDER",
        None,
        None,
    ),
    Case(
        "Is raining a lot today.", "Is raining", "It is raining", "PRONOUN", None, None
    ),
    Case("She is teacher.", "is teacher", "is a teacher", "ARTICLE", None, None),
]


HELD_OUT = [
    Case(
        "so yesterday we have a meeting with the client and he was happy",
        "we have",
        "we had",
        VT,
        PS,
        PAST,
    ),
    Case(
        "i am living in barcelona since three years",
        "am living",
        "have been living",
        VT,
        PC,
        PPC,
    ),
    Case(
        "my manager say that the deadline is next friday",
        "my manager say",
        "my manager says",
        SVA,
        PS,
        PS,
    ),
    Case("last month i buy a new laptop for work", "buy", "bought", VT, PS, PAST),
    Case(
        "I have visited Rome in 2018 with my family.",
        "have visited",
        "visited",
        VT,
        PP,
        PAST,
    ),
    Case(
        "when i was child i play football every weekend", "play", "played", VT, PS, PAST
    ),
    Case("She don't like the new office.", "She don't", "She doesn't", SVA, PS, PS),
    Case(
        "I think it rain tomorrow afternoon.", "it rain", "it will rain", VT, PS, WILL
    ),
    Case("We was very tired after the trip.", "We was", "We were", SVA, PAST, PAST),
    Case(
        "He can speaks three languages.",
        "can speaks",
        "can speak",
        VT,
        "modal_can",
        "modal_can",
    ),
    Case("She is agree with the plan.", "is agree", "agrees", VT, PS, PS),
    Case("I didn't knew the answer.", "didn't knew", "didn't know", VT, PAST, PAST),
    Case("Have you ever went to Japan?", "went", "been", VT, PP, PP),
    Case("They has a big house near the beach.", "They has", "They have", SVA, PS, PS),
    Case(
        "if i won the lottery i will buy a boat",
        "i will buy",
        "i would buy",
        VT,
        WILL,
        "modal_would",
    ),
    Case("Tomorrow I will to call you.", "will to call", "will call", VT, WILL, WILL),
    Case(
        "the flat have two bedrooms and a balcony",
        "the flat have",
        "the flat has",
        SVA,
        PS,
        PS,
    ),
    Case("He working from home today.", "He working", "He is working", OM, None, PC),
    Case(
        "They already left when we arrived.",
        "already left",
        "had already left",
        VT,
        PAST,
        PASTP,
    ),
    Case(
        "I am studying English for two years.",
        "am studying",
        "have been studying",
        VT,
        PC,
        PPC,
    ),
    Case("Where you live now?", "Where you live", "Where do you live", OM, PS, PS),
    Case("my kids is at school until three", "my kids is", "my kids are", SVA, PS, PS),
    Case(
        "I was born in Lima and I live in Madrid since 2015.",
        "I live",
        "I have lived",
        VT,
        PS,
        PP,
    ),
    Case(
        "It is difficult to explain, I never saw anything like that.",
        "never saw",
        "have never seen",
        VT,
        PAST,
        PP,
    ),
    Case(
        "I will call you when I will arrive.",
        "when I will arrive",
        "when I arrive",
        VT,
        WILL,
        PS,
    ),
    Case(
        "We are going to meet yesterday but it was cancelled.",
        "are going to meet",
        "were going to meet",
        VT,
        GOING,
        GOING,
    ),
    Case(
        "The price include the bills?",
        "The price include",
        "Does the price include",
        OM,
        PS,
        PS,
    ),
    Case(
        "There are a problem with the heating.",
        "There are a problem",
        "There is a problem",
        SVA,
        PS,
        PS,
    ),
    Case(
        "I must went to the bank.",
        "must went",
        "must go",
        VT,
        "modal_must",
        "modal_must",
    ),
    Case(
        "He should to study more.",
        "should to study",
        "should study",
        VT,
        "modal_should",
        "modal_should",
    ),
    Case(
        "ok so the kitchen is small but the bedrooms is big and the price include the water",
        "the bedrooms is",
        "the bedrooms are",
        SVA,
        PS,
        PS,
    ),
    Case(
        "yes i finish the migration last week and now i am testing it",
        "i finish",
        "i finished",
        VT,
        PS,
        PAST,
    ),
    Case(
        "I have 30 years.",
        "have 30 years",
        "am 30 years old",
        "LEXICAL_CHOICE",
        None,
        None,
    ),
    Case(
        "Can you explain me the contract?",
        "explain me the contract",
        "explain the contract to me",
        "WORD_ORDER",
        None,
        None,
    ),
]

# Every golden label in a verb-form category, by turn and quote. A new label in one of
# those categories fails the golden test until it is given a line here.
GOLDEN_FORMS: dict[tuple[int, str], tuple[str | None, str | None]] = {
    (6, "appreciate to be here"): (None, None),
    (18, "I complete the user story"): (PS, PAST),
    (18, "for today is I complete"): (PS, PAST),
    (20, "we request"): (PS, PAST),
}

GOLDEN = next(
    (
        path
        for path in (
            Path("/app/eval/golden/errors"),
            Path(__file__).resolve().parents[2] / "eval" / "golden" / "errors",
        )
        if (path / "manifest.json").is_file()
    ),
    None,
)


def golden_cases() -> tuple[str | None, list[Case]]:
    """The golden set's verb-form labels as cases, and which manifest they came from.

    A label whose quote has no line in `GOLDEN_FORMS` is returned with no forms, and the
    golden test fails on it by name.
    """
    if GOLDEN is None:
        return None, []
    name = next(
        n for n in ("manifest.local.json", "manifest.json") if (GOLDEN / n).is_file()
    )
    cases = []
    for item in json.loads((GOLDEN / name).read_text())["items"]:
        transcript = item["transcript"]
        for label in item["labels"]:
            if label["category"] not in forms.FORM_CATEGORIES:
                continue
            quote = transcript[label["span_start"] : label["span_end"]]
            form, corrected = GOLDEN_FORMS.get((item["turn_id"], quote), ("?", "?"))
            cases.append(
                Case(
                    transcript,
                    quote,
                    label["correction"],
                    label["category"],
                    form,
                    corrected,
                )
            )
    return name, cases


Verdict = Literal["exact", "partial", "wrong"]


def verdict(case: Case, found: forms.Link) -> Verdict:
    """Whether the join agrees with the label.

    `partial` is a join that says less than the label and nothing against it — a side it
    could not find. `wrong` names a form the label does not: it would count an error
    against a form the learner did not get wrong.
    """
    if found == case.label:
        return "exact"
    for said, labelled in (
        (found.form, case.form),
        (found.corrected_form, case.corrected_form),
    ):
        if said is not None and said != labelled:
            return "wrong"
    return "partial"


def link_one(case: Case) -> forms.Link:
    return forms.link(case.transcript, [case])[0]
