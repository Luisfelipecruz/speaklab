"""What the progress page reads: series, gates, and reasons.

**A point and a claim are different things, and this module keeps them apart.** A `Point`
is a measurement, or a hole where the data was too thin to make one. A `direction` is a
sentence about a speaker, and it is only ever filled in for a metric where one end of the
scale is defensibly better and where enough points exist to draw a line through. Speech
rate has no better end — faster is nerves as often as it is fluency — so its series
carries numbers and no verdict, and that absence is deliberate rather than unfinished.

**Every suppression says why.** A chart that silently omits a thin period looks like a
speaker who did not practise. `Gate` carries the reason in words a learner can read, and
the counts that would have to change for the point to appear.
"""

from datetime import date

from pydantic import BaseModel, Field

from config import PROGRESS_MIN_FORM_CONTEXTS

# Which end of a scale is better, where that is defensible at all. `None` is the honest
# answer for most fluency measures and it is the default: a metric with no stated
# direction is drawn and not judged.
Direction = str  # "higher" | "lower"


class Gate(BaseModel):
    """Whether a series may be drawn, and what it is waiting for."""

    shown: bool
    reason: str | None = None
    # What there is, and what it would take. Both, because "not enough readings yet" is
    # an instruction only when it says how many are missing.
    have: int = 0
    need: int = 0


class Point(BaseModel):
    """One period's value for one metric, or a hole with a reason."""

    start: date
    value: float | None = None
    # Words for a spoken metric, phone instances for a pronunciation one. It is what the
    # gate was applied to, carried so a chart can show the weight behind a point.
    samples: int = 0
    withheld: str | None = None


class Series(BaseModel):
    """One metric over the window."""

    metric: str
    label: str
    unit: str | None = None
    better: Direction | None = None
    points: list[Point] = Field(default_factory=list)
    gate: Gate

    # First measured point to last, and the direction that implies — filled in only when
    # `better` is set and there are enough points for the comparison to mean anything.
    change: float | None = None
    direction: str | None = None


class Family(BaseModel):
    """A group of series that answer the same question about a speaker."""

    name: str
    label: str
    description: str
    series: list[Series] = Field(default_factory=list)
    # Anything a reader has to know to read this family honestly. The accuracy family
    # carries the measured quality of the labelling behind it; the others are empty.
    caveat: str | None = None


class PhoneTrend(BaseModel):
    """One sound, against this speaker's own recent history.

    `z` is the whole point: raw goodness-of-pronunciation moves with the microphone and
    the room, so a number comparable across weeks has to be expressed as a distance from
    the same speaker's own baseline. Null means there was no baseline to compare against,
    which is the ordinary state of a first month.
    """

    phone: str
    mean_gop: float
    z: float | None = None
    baseline_mean: float | None = None
    baseline_readings: int = 0
    samples: int = 0


class FormAccuracy(BaseModel):
    """How one verb form was used in a period: said, said wrongly, needed and not said.

    `accuracy` is right over used plus missed, and it is withheld below the sample floor —
    the counts are the measurement there, and a percentage of three would overstate it. No
    page renders it even above the floor: the corrections under the count are the larger
    error, and a floor on the sample does nothing about them.
    """

    used: int = 0
    right: int = 0
    wrong: int = 0
    missed: int = 0
    accuracy: float | None = None


class Repertoire(BaseModel):
    """Which forms were used, how correctly, and whether the range of them is shrinking.

    Breadth is reported next to accuracy because either alone is misleading: a learner who
    retreats to the present simple makes fewer mistakes, and an error rate on its own
    calls that improvement.

    **Accuracy per form is for verb forms only.** A correction is joined to the verb
    phrase it changes, so the tenses, aspects and modals have one; a relative clause or a
    comparative does not, and is counted for breadth alone. Every correction that joins
    was proposed by the rule layer or the language model, so the panel carries a caveat
    of its own whenever it carries accuracy.
    """

    latest_period: date | None = None
    forms: dict[str, int] = Field(default_factory=dict)
    distinct_forms: int = 0
    previous_distinct_forms: int | None = None
    accuracy: dict[str, FormAccuracy] = Field(default_factory=dict)
    # Times a form was said or needed before its accuracy is given as a proportion, so a
    # client can tell a withheld proportion from a missing one. Sent with an empty panel too.
    accuracy_floor: int = PROGRESS_MIN_FORM_CONTEXTS
    # What the accuracy is counted from, and how far to trust it. Set whenever there is
    # accuracy to qualify, because this panel is read away from the error-rate chart.
    caveat: str | None = None
    # Set when the range of forms narrowed while the error rate also fell. It is the one
    # combination that reads as progress and is not.
    warning: str | None = None


class Recommendation(BaseModel):
    """One thing to practise next, and the measurement that chose it.

    `reason` is not decoration. A recommendation a learner cannot trace back to something
    the system measured is indistinguishable from a guess, and this product's whole claim
    is that it does not guess.
    """

    kind: str
    title: str
    reason: str
    # The number behind it and how much data that number rests on, so a suggestion made
    # from three observations can be told from one made from three hundred.
    measured: float | None = None
    samples: int = 0
    score: float = 0.0
    # Where to go and do something about it, when there is somewhere.
    scenario_slug: str | None = None
    passage_slug: str | None = None


class ProgressTotals(BaseModel):
    """How much practice the window rests on. The number every gate is really about."""

    sessions: int = 0
    turns: int = 0
    words: int = 0
    attempts: int = 0
    phones: int = 0
    periods: int = 0


class ProgressOut(BaseModel):
    """The whole progress page, in one response."""

    period: str
    since: date
    until: date
    totals: ProgressTotals
    families: list[Family] = Field(default_factory=list)
    phones: list[PhoneTrend] = Field(default_factory=list)
    phone_gate: Gate
    repertoire: Repertoire

    # Something has been analysed or scored since the last rollup, so these numbers are
    # behind the practice they describe. Reported rather than fixed on read: recomputing
    # inside a page load is what a snapshot table exists to avoid.
    stale: bool = False


class RecommendationsOut(BaseModel):
    items: list[Recommendation] = Field(default_factory=list)
    # Said out loud when there is not enough behind the suggestions to rank them well.
    # Recommending something is easy; being honest about how thin the evidence is is the
    # part that usually gets left out.
    confidence: str
    detail: str | None = None
