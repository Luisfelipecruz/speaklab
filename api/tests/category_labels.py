"""Hand-labelled learner sentences for the three scenarios that draw out articles,
prepositions and false friends.

Each is something a learner could say in the scenario that declares its category, with one
mistake in it, marked: the words said, what they should have been, and the kind of mistake
a teacher would file it under. Everything else in the sentence is correct English, so a
proposal anywhere else in it is a false positive, and the corrected sentence should draw no
proposal at all.

They answer two questions a scenario's brief cannot: whether a mistake of that kind, said
aloud, reaches the transcript as it was said, and whether the detector finds it once it
has. A scenario can only show that it draws out a kind of mistake through the corrections
it produces, and a correction needs both.
"""

from __future__ import annotations

from dataclasses import dataclass

ARTICLE, PREPOSITION, LEXICAL = "ARTICLE", "PREPOSITION", "LEXICAL_CHOICE"


@dataclass(frozen=True)
class Case:
    scenario: str
    transcript: str
    quote: str
    correction: str
    category: str
    subcategory: str

    @property
    def span_start(self) -> int:
        assert self.transcript.count(self.quote) == 1, self.quote
        return self.transcript.index(self.quote)

    @property
    def span_end(self) -> int:
        return self.span_start + len(self.quote)

    @property
    def corrected(self) -> str:
        return (
            self.transcript[: self.span_start]
            + self.correction
            + self.transcript[self.span_end :]
        )


def _lost(transcript: str, quote: str, correction: str, subcategory: str) -> Case:
    return Case(
        "lost-property-office", transcript, quote, correction, ARTICLE, subcategory
    )


def _courier(transcript: str, quote: str, correction: str, subcategory: str) -> Case:
    return Case(
        "courier-directions", transcript, quote, correction, PREPOSITION, subcategory
    )


def _intake(transcript: str, quote: str, correction: str) -> Case:
    return Case(
        "training-programme-intake",
        transcript,
        quote,
        correction,
        LEXICAL,
        "false_friend",
    )


CASES = [
    # Describing a bag to a clerk who has several like it.
    _lost(
        "I lost black backpack on the train this morning.",
        "black backpack",
        "a black backpack",
        "missing_indefinite",
    ),
    _lost(
        "It is small suitcase with wheels and a long handle.",
        "small suitcase",
        "a small suitcase",
        "missing_indefinite",
    ),
    _lost(
        "Inside there is laptop and a charger.",
        "laptop",
        "a laptop",
        "missing_indefinite",
    ),
    _lost(
        "The laptop has sticker of a cat on the lid.",
        "sticker",
        "a sticker",
        "missing_indefinite",
    ),
    _lost(
        "I was sitting in second carriage, near the door.",
        "second carriage",
        "the second carriage",
        "missing_definite",
    ),
    _lost(
        "I took train from Madrid at eight.", "train", "the train", "missing_definite"
    ),
    _lost(
        "I always lose the things when I travel.", "the things", "things", "superfluous"
    ),
    _lost(
        "I need the laptop for the work tomorrow.", "the work", "work", "superfluous"
    ),
    _lost(
        "My brother is engineer and the laptop is his.",
        "engineer",
        "an engineer",
        "missing_indefinite",
    ),
    _lost(
        "It is a orange bag with a white stripe.",
        "a orange",
        "an orange",
        "wrong_choice",
    ),
    _lost(
        "There is umbrella in the side pocket.",
        "umbrella",
        "an umbrella",
        "missing_indefinite",
    ),
    _lost(
        "Yesterday I bought the new umbrella, and I left it on the train.",
        "the new umbrella",
        "a new umbrella",
        "wrong_choice",
    ),
    _lost(
        "I went to the home after that and I saw the bag was missing.",
        "went to the home",
        "went home",
        "superfluous",
    ),
    _lost(
        "In the morning I always have the breakfast at the station.",
        "the breakfast",
        "breakfast",
        "superfluous",
    ),
    _lost(
        "My phone number is on a label inside, and it is the same as on form.",
        "on form",
        "on the form",
        "missing_definite",
    ),
    _lost(
        "It looks like the one on top shelf, but mine is older.",
        "top shelf",
        "the top shelf",
        "missing_definite",
    ),
    _lost("The charger is a Apple one.", "a Apple", "an Apple", "wrong_choice"),
    _lost(
        "I am student and I need the laptop for my exams.",
        "student",
        "a student",
        "missing_indefinite",
    ),
    _lost(
        "My name is written on small card inside the front pocket.",
        "small card",
        "a small card",
        "missing_indefinite",
    ),
    _lost(
        "It has a key ring with a small bell, and the bell makes the noise when you "
        "move it.",
        "the noise",
        "a noise",
        "wrong_choice",
    ),
    # Talking a delivery driver from the street to the door, then agreeing a time.
    _courier(
        "The entrance is at the back of the building, next of the bins.",
        "next of",
        "next to",
        "wrong",
    ),
    _courier(
        "My flat is in the second floor.",
        "in the second floor",
        "on the second floor",
        "wrong",
    ),
    _courier(
        "When you arrive to the corner, turn left.", "arrive to", "arrive at", "wrong"
    ),
    _courier(
        "Turn right in the pharmacy and go straight on.",
        "in the pharmacy",
        "at the pharmacy",
        "wrong",
    ),
    _courier(
        "The door is in front the bakery and it is green.",
        "in front the",
        "in front of the",
        "missing",
    ),
    _courier("Please wait me outside the gate.", "wait me", "wait for me", "missing"),
    _courier(
        "You don't need to enter in the building because I will come down.",
        "enter in",
        "enter",
        "superfluous",
    ),
    _courier(
        "I will be at home in Tuesday morning.", "in Tuesday", "on Tuesday", "wrong"
    ),
    _courier(
        "I am usually at home at the evening.",
        "at the evening",
        "in the evening",
        "wrong",
    ),
    _courier(
        "Can you come on the afternoon?",
        "on the afternoon",
        "in the afternoon",
        "wrong",
    ),
    _courier("I am in home all day on Friday.", "in home", "at home", "wrong"),
    _courier(
        "It depends of the traffic, but I can wait for you.",
        "depends of",
        "depends on",
        "wrong",
    ),
    _courier(
        "Call me when you are in the corner of the street.",
        "in the corner",
        "at the corner",
        "wrong",
    ),
    _courier(
        "Go across of the park and you will see a blue door.",
        "across of",
        "across",
        "superfluous",
    ),
    _courier(
        "The shop closes at eight, so come before of that.",
        "before of",
        "before",
        "superfluous",
    ),
    _courier(
        "I am waiting you at the gate now.", "waiting you", "waiting for you", "missing"
    ),
    _courier(
        "My building is the one in the end of the street.",
        "in the end of",
        "at the end of",
        "wrong",
    ),
    _courier(
        "I will be back until five, so you can come after that.",
        "until five",
        "by five",
        "wrong",
    ),
    _courier(
        "Listen me carefully because the door is behind the shop.",
        "Listen me",
        "Listen to me",
        "missing",
    ),
    _courier(
        "The lift is in the right when you come in.",
        "in the right",
        "on the right",
        "wrong",
    ),
    # Telling a programme coordinator what you do, what you studied and what you have
    # been to — the words whose look-alike in another language means something else.
    _intake(
        "Last year I assisted to a conference about data in Lisbon.",
        "assisted to",
        "attended",
    ),
    _intake(
        "I studied the career of economics in Seville.",
        "the career of economics",
        "a degree in economics",
    ),
    _intake(
        "Two years ago I did a formation in project management.",
        "a formation",
        "a course",
    ),
    _intake("I work in a fabric that makes parts for cars.", "fabric", "factory"),
    _intake("I made a resume of the project for my manager.", "resume", "summary"),
    _intake(
        "Sometimes I have to discuss with clients who do not want to pay.",
        "discuss with",
        "argue with",
    ),
    _intake(
        "At work we handle a lot of sensible information about patients.",
        "sensible",
        "sensitive",
    ),
    _intake("I pretend to finish my master's next year.", "pretend", "intend"),
    _intake("I still record my first day in that job.", "record", "remember"),
    _intake(
        "I have five years of experience in attention to the client.",
        "attention to the client",
        "customer service",
    ),
    _intake("I keep all my certificates in a blue carpet.", "carpet", "folder"),
    _intake(
        "I bought the books for the course in a library near my house.",
        "library",
        "bookshop",
    ),
    _intake(
        "I missed two classes because I was constipated.",
        "was constipated",
        "had a cold",
    ),
    _intake(
        "My actual job is in a bank, and before that I was a teacher.",
        "actual",
        "current",
    ),
    _intake(
        "Last year I realised a big project with the sales team.",
        "realised",
        "carried out",
    ),
    _intake("In my job I have to support a lot of pressure.", "support", "deal with"),
    _intake(
        "I went to a conference of an expert in design.",
        "a conference of",
        "a talk by",
    ),
    _intake(
        "This programme is a good way to improve my curriculum.", "curriculum", "CV"
    ),
    _intake(
        "I have a big compromise with my team, so I cannot leave now.",
        "compromise",
        "commitment",
    ),
    _intake(
        "I finished my career three years ago and started working.", "career", "degree"
    ),
]
