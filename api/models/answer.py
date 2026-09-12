"""Spoken answers: the prompts, what was counted, and what the model said about it.

**Three kinds of statement, kept apart the way the session report keeps them.** `delivery`
is arithmetic over word timings and `structure` is counted from the transcript; both are
deterministic, and only they are drawn over time. `feedback` is a language model's reading
of the transcript, beside the counts and never in place of them, and it carries its own
status so a missing explanation is never mistaken for an answer with nothing to say.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from models.common import CEFRBand, ORMModel, SeedModel, Slug
from models.progress import Series

PromptCategory = Literal["explain", "justify", "walk-through", "recommend"]


class PromptSeed(SeedModel):
    """One record in `seeds/prompts.json`."""

    slug: Slug
    title: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    category: PromptCategory
    cefr_band: CEFRBand
    # Long enough for two or three points with a reason each, short enough that the
    # answer is one idea said once rather than a talk.
    time_limit_s: int = Field(ge=60, le=120)
    is_active: bool = True


class PromptOut(ORMModel):
    slug: str
    title: str
    prompt: str
    category: str
    cefr_band: CEFRBand
    time_limit_s: int


class PromptSummary(PromptOut):
    """A prompt in the list, with how often this learner has answered it."""

    answers: int = 0
    last_answered_at: datetime | None = None


class Delivery(BaseModel):
    """How it was said, from the word timings — the arithmetic a conversation turn gets."""

    words: int
    duration_ms: int | None = None
    speech_rate_wpm: float | None = None
    articulation_rate: float | None = None
    pause_ratio: float | None = None
    mean_length_run: float | None = None
    fillers: int = 0
    fillers_per_100_words: float | None = None


class Counted(BaseModel):
    """One thing counted in the transcript: a signpost by what it does, or a repeat."""

    kind: str
    start: int
    end: int
    text: str


class StructureOut(BaseModel):
    """How it was built. Only the measures in `shown` cleared their bar; the rest are null."""

    words: int
    sentences: int | None = None
    words_per_sentence: float | None = None
    longest_sentence: int | None = None
    signposts: dict[str, int] = Field(default_factory=dict)
    repeats: int | None = None
    found: list[Counted] = Field(default_factory=list)
    shown: list[str] = Field(default_factory=list)
    caveat: str


FeedbackStatus = Literal["ok", "refused", "unavailable", "unparseable", "skipped"]


class Feedback(BaseModel):
    """What the language model said, and what the code checked of it.

    `refused` is a rewrite that added content words the speaker never said, over the limit:
    it is withheld and the words are listed, so the refusal is visible rather than silent.
    """

    status: FeedbackStatus
    model: str | None = None
    lead: str | None = None
    gaps: list[str] = Field(default_factory=list)
    rewrite: str | None = None
    rewrite_sentences: int | None = None
    invented: list[str] = Field(default_factory=list)
    detail: str | None = None
    caveat: str


class AnswerOut(BaseModel):
    """One spoken answer, counted, with the model's feedback beside the counts."""

    id: int
    prompt: PromptOut
    created_at: datetime
    again_of: int | None = None
    transcript: str
    asr_confidence: float | None = None
    delivery: Delivery
    structure: StructureOut
    feedback: Feedback | None = None


class AnswersOut(BaseModel):
    """The answers page: every prompt, this learner's answers, and their history."""

    prompts: list[PromptSummary] = Field(default_factory=list)
    # Set when the page was asked about one prompt; `answers` are then that prompt's.
    prompt: PromptOut | None = None
    answers: list[AnswerOut] = Field(default_factory=list)
    answered: int = 0
    # One point per answer, oldest first. The same shape as the progress page's series,
    # with the same rule: a direction only where one end is better and three points exist.
    history: list[Series] = Field(default_factory=list)
    caveat: str
