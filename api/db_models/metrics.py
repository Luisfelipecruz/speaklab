"""Everything measured. Four tables, one rule: none of it is written by an LLM.

Anything that moves on a chart is computed by deterministic code from the waveform or
the transcript, so the same audio produces the same number every time. `language_errors`
is the one table an LLM touches, and even there the `detector` column records which layer
produced the row: an LLM proposal that the rule layer validated, or a rule that fired on
its own. An out-of-taxonomy label is rejected and counted as a model-quality metric —
never stored here as if it were a finding.

`fluency_metrics` is keyed by `turn_id` rather than carrying its own id: there is
exactly one row per turn, forever, and a surrogate key would allow a second.
"""

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from db_models.base import Base


class FluencyMetrics(Base):
    __tablename__ = "fluency_metrics"

    turn_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("turns.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # Every one of these is a function of the word timings on the turn, which is why
    # they are stored next to nothing else: recomputing them means re-reading
    # `turns.words`, and that array outlives the audio it came from.
    speech_rate_wpm: Mapped[float | None] = mapped_column(Float)

    # Excludes pauses >= 250 ms, which is what separates "speaks quickly" from "speaks
    # without stopping to think" — two very different things that speech rate alone
    # reports as one number.
    articulation_rate: Mapped[float | None] = mapped_column(Float)
    pause_ratio: Mapped[float | None] = mapped_column(Float)
    mean_length_run: Mapped[float | None] = mapped_column(Float)
    filler_count: Mapped[int | None] = mapped_column(Integer)
    word_count: Mapped[int | None] = mapped_column(Integer)

    # Silence before the first word of the recording. A floor on response latency rather
    # than the measurement itself: the clock starts when the speaker pressed record, not
    # when the persona stopped talking. Closing that gap needs the browser to timestamp
    # the button against the end of the reply audio, which nothing does yet — so what is
    # stored is hesitation the speaker chose to record, which is still a fluency signal
    # the transcript cannot show.
    response_latency_ms: Mapped[int | None] = mapped_column(Integer)


class GrammarUsage(Base):
    """Breadth, measured separately from accuracy.

    A learner reaches a zero error rate by only ever using the present simple. Counting
    which forms were *used* is what makes that visible as the regression it is, instead
    of as improvement.
    """

    __tablename__ = "grammar_usage"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    turn_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("turns.id", ondelete="CASCADE"), nullable=False
    )
    feature: Mapped[str] = mapped_column(Text, nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        # One row per feature per turn: the count is a count, not a number of rows.
        UniqueConstraint("turn_id", "feature", name="uq_grammar_usage_turn_id_feature"),
    )


class LanguageError(Base):
    """One correction, with its span, its category, and who found it."""

    __tablename__ = "language_errors"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    turn_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("turns.id", ondelete="CASCADE"), nullable=False
    )

    # The closed error taxonomy. TEXT here and enforced in the application layer,
    # because unlike session mode and status this vocabulary is expected to be revised
    # as real transcripts are read — and a taxonomy revision should be a code change
    # with a test, not an ALTER TYPE that cannot be run inside a transaction.
    category: Mapped[str] = mapped_column(Text, nullable=False)
    subcategory: Mapped[str | None] = mapped_column(Text)

    # Character offsets into turns.transcript, so the UI underlines the words rather
    # than restating them.
    span_start: Mapped[int | None] = mapped_column(Integer)
    span_end: Mapped[int | None] = mapped_column(Integer)

    original: Mapped[str] = mapped_column(Text, nullable=False)
    correction: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str | None] = mapped_column(Text)

    # Which layer produced this row. It is what lets LLM precision be reported against
    # the rule layer instead of asserted, and what lets a bad prompt be found by
    # querying rather than by reading transcripts.
    detector: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)

    # At least one word under this error's span was one the recogniser was unsure of, so
    # the "error" may be a mishearing. The row is kept and shown — a transcript with a
    # hole in it is worse than one with a doubtful correction on it — and excluded from
    # every accuracy trend, because a trend that moves for the recogniser's reasons is
    # worse than both.
    asr_suspect: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=false()
    )

    __table_args__ = (
        CheckConstraint("detector IN ('llm', 'rule')", name="detector"),
        Index("ix_language_errors_turn_id_category", "turn_id", "category"),
    )


class ProgressSnapshot(Base):
    """Per-turn rows collapsed into one row per user per period.

    The progress page reads this and nothing else. A chart that aggregated raw turns on
    every page load would get slower every week the user practised, and the rollup is
    also where `sample_counts` is computed — which is what keeps a trend line off the
    screen until there is enough behind it to mean something: no phoneme trend is shown
    under 5 scored attempts.

    JSONB per family rather than fifty columns: the set of fluency measures is expected
    to change, and a schema migration per metric added is a tax on exactly the
    experimentation this project is for. Nothing here is queried by key across rows —
    it is read whole, for one user, for one window.
    """

    __tablename__ = "progress_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    period: Mapped[str] = mapped_column(Text, nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)

    fluency: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")

    # Errors per 100 words by category — a rate, not a count, so a long session does
    # not read as a bad one.
    accuracy: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    complexity: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")

    # Mean GOP per phone, z-scored against this user's own rolling baseline. Raw GOP
    # moves with the microphone and the room, which is why nothing is compared across
    # users and why the z-scoring happens before anything is plotted.
    pronunciation: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    sample_counts: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )

    # An estimate, labelled as one. It is not calibrated against human raters, and the
    # column exists so the estimate is recorded rather than recomputed differently by
    # each screen that shows it. Nothing writes it yet: a band assigned from a handful of
    # turns would be a confident answer to a question this data cannot settle.
    cefr_estimate: Mapped[str | None] = mapped_column(Text)

    # When this row was last computed. A materialised aggregate with no notion of its own
    # age cannot be asked whether it is current, and the two available answers without it
    # are both wrong: recompute on every page load, which is what a snapshot table exists
    # to avoid, or assume it is fresh, which is how a chart quietly stops moving. The
    # rows underneath carry their own timestamps, so "is there anything newer than this"
    # has an exact answer.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("period IN ('day', 'week')", name="period"),
        UniqueConstraint(
            "user_id",
            "period",
            "period_start",
            name="uq_progress_snapshots_user_id_period_period_start",
        ),
    )
