"""Say it in English and the Notebook: what a capture looks like on the wire.

**One shape for the panel and the page.** `POST /captures` answers with the capture as the
Notebook will show it — with `id` null when saving is paused, because then nothing was
kept — so the panel and the moment page cannot disagree about what happened.

**Every version is named, and the one copied is said.** `text` is what went on the
clipboard; `versions` holds every one written so far, null while one is still being
written behind the reply. `dropped` lists, per version, what the keep check could not find
in it. Nothing is ever swapped for another behind the person's back.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from models.drill import DrillWord

Version = Literal["direct", "organized", "corrected", "polished", "rough"]
Mode = Literal["translate", "check"]
Via = Literal["voice", "typed", "copied"]
State = Literal["to_practise", "due", "practised"]


class CaptureFix(BaseModel):
    """One mistake found in what the person wrote or said, and its correction."""

    category: str
    label: str
    subcategory: str | None = None
    span_start: int | None = None
    span_end: int | None = None
    original: str
    correction: str
    explanation: str | None = None
    # `dictionary`, `rule` or `llm`.
    detector: str
    # Whether it may reach a rate: the same floor a conversation's corrections meet, and
    # only for English the person wrote. A spoken check is shown, never counted.
    counted: bool = False


class Phrase(BaseModel):
    """A phrase the person said, the English used for it, and how often that English is
    in their other captures — counted by code, so the phrases they keep needing show."""

    source: str
    english: str
    elsewhere: int = 0


class LanguageChoice(BaseModel):
    """Which language the capture was taken to be in, and what decided it."""

    language: str
    # `recogniser` for speech, `words` for a text by its common words, `switch` when the
    # person said which.
    by: Literal["recogniser", "words", "switch"]
    scores: dict[str, float] = Field(default_factory=dict)


class AttemptSummary(BaseModel):
    """One time the person wrote it themselves, as the moment page lists it."""

    id: int
    created_at: datetime
    word_count: int
    counted: int
    box: int


class CaptureOut(BaseModel):
    """One capture, as the panel shows it and as the Notebook keeps it."""

    id: int | None = None
    saved: bool = True
    created_at: datetime
    mode: Mode
    via: Via
    source_language: str
    source_text: str
    duration_ms: int | None = None
    app: str | None = None
    chosen: Version
    text: str
    versions: dict[str, str | None] = Field(default_factory=dict)
    dropped: dict[str, list[str]] = Field(default_factory=dict)
    # What every version had to keep, as written in what was said: the names, numbers,
    # links and addresses the keep check looked for, with the names the account has used.
    kept: list[str] = Field(default_factory=list)
    fixes: list[CaptureFix] = Field(default_factory=list)
    phrases: list[Phrase] = Field(default_factory=list)
    # What the person should know about how this one was made, in plain words: the
    # recogniser's rough English standing in for the model's, a check with the model down.
    notes: list[str] = Field(default_factory=list)
    language: LanguageChoice | None = None
    state: State = "to_practise"
    practised: int = 0
    box: int = 0
    due_at: datetime | None = None
    attempts: list[AttemptSummary] = Field(default_factory=list)
    asr_model: str | None = None
    llm_model: str | None = None
    timings: dict[str, int] = Field(default_factory=dict)


class CaptureSummary(BaseModel):
    """One capture in the Notebook's list."""

    id: int
    created_at: datetime
    mode: Mode
    via: Via
    app: str | None = None
    source_text: str
    chosen: Version
    text: str
    state: State
    practised: int = 0
    box: int = 0
    due_at: datetime | None = None


class NotebookCounts(BaseModel):
    """The figures over the Notebook's list, each a count of rows."""

    total: int = 0
    this_week: int = 0
    practised_this_week: int = 0
    # Attempts this week with no counted mistake.
    clean_this_week: int = 0
    due: int = 0
    to_practise: int = 0


class CaptureList(BaseModel):
    items: list[CaptureSummary] = Field(default_factory=list)
    # How many match the filters, before the page is cut.
    matching: int = 0
    limit: int
    offset: int = 0
    counts: NotebookCounts
    apps: list[str] = Field(default_factory=list)


class AttemptIn(BaseModel):
    text: str = Field(min_length=1, description="The English, written your way.")


class WrittenWord(BaseModel):
    """One step of the comparison with the closer version: its word, yours, or both."""

    expected: str | None = None
    written: str | None = None


class AttemptOut(BaseModel):
    """One attempt, checked: the mistakes in it, the forms used, the closer version
    compared word by word, and when the capture comes back."""

    id: int
    capture_id: int
    created_at: datetime
    text: str
    word_count: int
    errors: list[CaptureFix] = Field(default_factory=list)
    counted: int = 0
    per_100_words: float | None = None
    forms: dict[str, int] = Field(default_factory=dict)
    compared_with: Version | None = None
    compared_text: str | None = None
    words: list[WrittenWord] = Field(default_factory=list)
    box_before: int
    box: int
    due_at: datetime
    detail: str | None = None


class SaidOut(BaseModel):
    """Saying the English aloud, heard and compared with the version used. Nothing is
    stored."""

    heard: str
    compared_with: Version
    expected: str
    words: list[DrillWord] = Field(default_factory=list)
    expected_words: int = 0
    matched: int = 0
    substituted: int = 0
    missed: int = 0
    added: int = 0
    caveat: str
