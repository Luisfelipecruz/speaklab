"""What the grammar page reads: the learner's own corrections, grouped, and the verb forms
they were in.

**Evidence rather than a score.** Every figure here comes with the sentences it was
counted from, because every correction was proposed by grammar rules or a language model
and none was checked by a person. A learner can read a correction and disagree with it; a
percentage gives them nothing to disagree with. So the forms carry counts and the
corrections behind them, and no proportion.
"""

from datetime import date, datetime

from pydantic import BaseModel, Field

from models.progress import Gate


class CorrectionExample(BaseModel):
    """One correction, in the sentence it was made in."""

    id: int
    session_id: int
    turn_id: int
    said_at: datetime
    scenario_title: str | None = None
    # The sentence around the correction, from the transcript. `quote` is the
    # transcript's own words under it — null when the stored offsets do not hold the
    # words the correction quotes, and then `before` and `after` are empty, because a
    # sentence cut around the wrong words would put the correction on something the
    # speaker got right.
    before: str = ""
    quote: str | None = None
    after: str = ""
    original: str
    correction: str
    explanation: str | None = None
    subcategory: str | None = None
    detector: str
    counted: bool
    asr_suspect: bool
    form: str | None = None
    corrected_form: str | None = None


class CategoryCorrections(BaseModel):
    """Every correction of one kind in the window, and the newest few in full."""

    category: str
    label: str
    description: str
    counted: int
    # Shown and not counted: on words the recogniser was unsure of, or hedged by the
    # model that proposed them.
    not_counted: int
    per_100_words: float | None = None
    by_detector: dict[str, int] = Field(default_factory=dict)
    examples: list[CorrectionExample] = Field(default_factory=list)


class FormCorrection(BaseModel):
    """A correction that changed a verb form: what was said, and what it should have been."""

    id: int
    session_id: int
    original: str
    correction: str
    form: str | None = None
    corrected_form: str | None = None


class FormPractice(BaseModel):
    """One verb form: said, said wrongly, needed where another was said.

    `right` is used minus wrong, so a mistake nobody flagged counts as right.
    """

    form: str
    label: str
    used: int = 0
    right: int = 0
    wrong: int = 0
    missed: int = 0
    corrections: list[FormCorrection] = Field(default_factory=list)


class WeakestForm(BaseModel):
    """The verb form to practise, the counts that chose it, and where to practise it."""

    form: str
    label: str
    used: int
    right: int
    wrong: int
    missed: int
    reason: str
    scenario_slug: str | None = None
    scenario_title: str | None = None


class GrammarTotals(BaseModel):
    """How much practice the page rests on."""

    sessions: int = 0
    turns: int = 0
    words: int = 0
    corrections: int = 0
    counted: int = 0


class GrammarOut(BaseModel):
    """The whole grammar page, in one response."""

    since: date
    until: date
    totals: GrammarTotals
    categories: list[CategoryCorrections] = Field(default_factory=list)
    forms: list[FormPractice] = Field(default_factory=list)
    weakest: WeakestForm | None = None
    # Why no form is named, when none is, and how far the nearest one is from the floor.
    weakest_gate: Gate
    # Set whenever there is a correction to qualify.
    caveat: str | None = None
