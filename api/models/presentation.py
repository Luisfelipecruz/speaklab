"""Rehearsal wire shapes: a script, its sections, and one take of one section.

**Three kinds of statement, kept apart, as the answer page keeps them.** `fidelity` is an
alignment against the words the learner wrote, `delivery` is arithmetic over word timings,
and the phones come from a model that processed the waveform. There is no fourth kind
here: nothing on a take was written by a language model, and no number on this page is a
mark. `caveat` is where each shape says what it does not know.

`pace` is the one judgement, and it is a comparison with a time the learner typed
themselves — over, under, or on it — never with a time anybody else took.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from models.answer import Delivery
from models.attempt import PhonemeScoreOut, PronSummary
from models.common import ORMModel

FIDELITY_CAVEAT = (
    "Compared with your script word by word, by the same arithmetic as a reading. "
    "A word marked as missed may have been said and misheard: the recogniser's own "
    "uncertainty is marked where it is known."
)

TAKE_CAVEAT = (
    "Counted from this recording alone. Nothing here is a mark, and nothing here is "
    "added to your progress: a script you wrote is practice, not a sample of how you "
    "speak unprepared."
)


class PresentationCreate(BaseModel):
    """A script to rehearse, with the split the writer accepted, if they moved it."""

    title: str = Field(min_length=1, max_length=120)
    script: str = Field(min_length=1)

    # The writer's own boundaries, after seeing the preview. When given they replace the
    # automatic split, and are checked against the script word for word: a split whose
    # sections do not add up to the text is refused rather than saved as the talk.
    sections: list[str] | None = None
    target_seconds: list[int | None] | None = None


class TakeSummary(ORMModel):
    """One take as a row in a table: when, how close, how fast, how long."""

    id: int
    section_id: int
    created_at: datetime
    wer: float

    # Words of the section this take did not say as written. Beside the rate rather than
    # instead of it: a rate is comparable between sections of different lengths, and a
    # count is the thing a reader can go and look at.
    missed: int = 0
    duration_ms: int | None = None
    speech_rate_wpm: float | None = None
    fillers: int = 0
    pron_status: str
    median_gop: float | None = None
    audio_url: str | None = None


class SectionOut(ORMModel):
    """One section of the script, and how it has gone."""

    id: int
    idx: int
    body: str
    word_count: int
    target_seconds: int | None = None

    # False when a word in it cannot be turned into phones. The section is still
    # rehearsed, compared and counted; only its sounds are missing.
    scorable: bool = True
    unscorable_words: list[str] = Field(default_factory=list)

    takes: int = 0
    latest: TakeSummary | None = None


class PresentationOut(ORMModel):
    """A script with its sections."""

    id: int
    title: str
    word_count: int
    created_at: datetime
    updated_at: datetime
    sections: list[SectionOut] = Field(default_factory=list)


class PresentationSummary(ORMModel):
    """A script in the list: enough to choose one, without its text."""

    id: int
    title: str
    word_count: int
    sections: int = 0
    takes: int = 0
    created_at: datetime
    updated_at: datetime


class PresentationList(BaseModel):
    """`GET /presentations` — newest activity first, bounded server-side."""

    items: list[PresentationSummary] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class SplitPreview(BaseModel):
    """What the split would be, before anything is saved."""

    sections: list[str] = Field(default_factory=list)
    word_counts: list[int] = Field(default_factory=list)

    # One list per section, so the page can name the words under the section they are in.
    unscorable: list[list[str]] = Field(default_factory=list)

    # ok | unavailable. Which words cannot be scored is a question only the pronunciation
    # service can answer; when it is not running the split is still shown, and the page
    # says the check did not happen rather than implying every word is fine.
    pron: str = "ok"


class AlignedWord(BaseModel):
    """One step of the alignment between the script and what was heard."""

    kind: Literal["match", "substitution", "deletion", "insertion"]
    expected: str | None = None
    heard: str | None = None

    # What kind of difference this is, on a substitution: `figure`, `ending` or
    # `different-word`. None on a match, and on a take recorded before differences were
    # sorted at all — which is why it is optional rather than a fourth `kind`.
    kind_of_difference: str | None = None

    # The recogniser's own confidence in this word was under the floor. Shown because a
    # word it was unsure of is the likeliest place for a mistake that is the microphone's
    # rather than the speaker's.
    unsure: bool = False


class Fidelity(BaseModel):
    """How close the take was to the script, and where it differed."""

    wer: float
    reference_words: int
    substitutions: int
    deletions: int
    insertions: int

    # Substituted words that are the same number written two ways. Counted on their own
    # and left out of `substitutions` and `wer`, because a number said correctly and
    # written as a digit is not something the speaker did.
    figures: int = 0
    words: list[AlignedWord] = Field(default_factory=list)

    # -1 when the recogniser's words could not be lined up with the compared text, so
    # that "none were uncertain" and "uncertainty could not be attached" are different
    # answers rather than the same zero.
    unsure_words: int = 0
    caveat: str = FIDELITY_CAVEAT


class TakeOut(TakeSummary):
    """One take with everything: the alignment, the counts and the sounds."""

    transcript: str
    asr_confidence: float | None = None
    fidelity: Fidelity
    delivery: Delivery

    # ok | pending | unavailable | unscorable | rejected | protocol | misconfigured
    #
    # Separate from the lifecycle, because "this section has a word that cannot be turned
    # into phones" and "the scorer is switched off" are different facts, and neither is a
    # take that failed.
    pronunciation: str = "pending"
    pronunciation_detail: str | None = None
    phonemes: list[PhonemeScoreOut] = Field(default_factory=list)
    summary: PronSummary | None = None

    target_seconds: int | None = None

    # under | on | over, when the section carries a target. Null when it does not: a pace
    # with nothing to compare it against is a number, not a judgement.
    pace: str | None = None
    caveat: str = TAKE_CAVEAT


class TakeList(BaseModel):
    """A section's takes, newest first."""

    items: list[TakeOut] = Field(default_factory=list)


class NextUp(BaseModel):
    """One thing to rehearse next, with the measurement that chose it.

    `measured` and `samples` are printed beside the title on purpose: an item that cannot
    show what it counted is advice, and this page does not give advice.
    """

    kind: Literal["fidelity", "sound", "pace", "filler"]
    title: str
    reason: str
    measured: float | None = None
    samples: int = 0
    section_id: int | None = None


NEXT_UP_CAVEAT = (
    "Counted from your takes of this script only. Nothing here comes from a language "
    "model, and none of it moves your progress."
)


class SoundOut(BaseModel):
    """One sound across this script's takes, named in words rather than in code.

    `words` are the speaker's own — up to three words of their script the sound was
    scored inside — because a sound is practised in words, and theirs are the ones they
    are about to say again.
    """

    phone: str
    name: str
    instances: int
    takes: int
    mean_gop: float
    words: list[str] = Field(default_factory=list)


SOUNDS_CAVEAT = (
    "Scored from your takes of this script. A low score is a sound worth listening to, "
    "not a mistake: it is how far the recording sat from what the model expected."
)


class PresentationPage(BaseModel):
    """The presentation's own page: its sections, what to rehearse next, its sounds."""

    presentation: PresentationOut
    next_up: list[NextUp] = Field(default_factory=list)
    sounds: list[SoundOut] = Field(default_factory=list)
    caveat: str = NEXT_UP_CAVEAT
    sounds_caveat: str = SOUNDS_CAVEAT


class SectionTarget(BaseModel):
    """The time the learner means a section to take, in seconds. Null clears it."""

    target_seconds: int | None = Field(default=None, ge=1, le=600)
