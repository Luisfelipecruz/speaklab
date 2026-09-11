"""The spoken drill: one of your own sentences with its correction in it, and what the
recogniser heard when you said it again.

**No score, no pass mark.** What comes back is what was heard: each correction's words,
and what stood in their place — the corrected words, the words as first said, something
else, or nothing — and the sentence word by word. The recogniser can hear a correct form
where a wrong one was said, and the corrections themselves are often wrong, so a pass mark
would be two machines' opinion presented as the learner's grammar.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class DrillPiece(BaseModel):
    """A stretch of the sentence: as it was said, and as it is to be said.

    The two are the same outside a correction. Inside one, `said` is the transcript's words
    and `say` is the correction.
    """

    said: str
    say: str
    correction_id: int | None = None


class DrillCorrection(BaseModel):
    """A correction the sentence carries, so the learner can read it before saying it."""

    id: int
    category: str
    label: str
    subcategory: str | None = None
    original: str
    correction: str
    explanation: str | None = None
    detector: str
    counted: bool
    asr_suspect: bool


class DrillOut(BaseModel):
    """One correction to practise, in the sentence it was made in."""

    id: int
    session_id: int
    turn_id: int
    said_at: datetime
    scenario_title: str | None = None
    # Every correction applied to the sentence, in the order they appear in it; the one
    # being practised is among them. More than one when the sentence held several: saying
    # it with only one of them fixed would be practising the others.
    corrections: list[DrillCorrection] = Field(default_factory=list)
    # Empty when the correction cannot be practised aloud: its words are not where its
    # offsets say, or it changes nothing speech carries — capitals or punctuation.
    pieces: list[DrillPiece] = Field(default_factory=list)
    unavailable: str | None = None
    cut_before: bool = False
    cut_after: bool = False
    # The next correction of the same kind, newest first, that is not already in this
    # sentence. Null after the last.
    next_id: int | None = None
    caveat: str


class DrillWord(BaseModel):
    """One step of the comparison: a word of the sentence, a word heard, or both."""

    expected: str | None = None
    heard: str | None = None


class DrillVerdict(BaseModel):
    """What was heard where one correction's words belong."""

    id: int
    verdict: Literal["corrected", "original", "other", "unheard"]
    expected: str
    heard: str
    # A word heard there was one the recogniser was unsure of.
    unsure: bool = False


class DrillResult(BaseModel):
    """What the recogniser heard, compared with the sentence. Nothing is stored."""

    heard: str
    words: list[DrillWord] = Field(default_factory=list)
    verdicts: list[DrillVerdict] = Field(default_factory=list)
    expected_words: int = 0
    matched: int = 0
    substituted: int = 0
    missed: int = 0
    added: int = 0
