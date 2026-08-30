"""Everything measured. Four tables, one rule: none of it is written by an LLM.

Invariant I1 — anything that moves on a chart is computed by deterministic code from
the waveform or the transcript, so the same audio produces the same number every time.
`language_errors` is the one table an LLM touches, and even there the `detector` column
records which layer produced the row: an LLM proposal that the rule layer validated, or
a rule that fired on its own. An out-of-taxonomy label is rejected and counted as a
model-quality metric — never stored here as if it were a finding (invariant I3).

`fluency_metrics` is keyed by `turn_id` rather than carrying its own id: there is
exactly one row per turn, forever, and a surrogate key would allow a second.
"""

from datetime import date

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
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

    # PRD §7.1. Every one of these is a function of the word timings on the turn, which
    # is why they are stored next to nothing else: recomputing them means re-reading
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

    # Time from the end of the persona's audio to the start of speech. A fluency signal
    # the transcript cannot show.
    response_latency_ms: Mapped[int | None] = mapped_column(Integer)


class GrammarUsage(Base):
    """Breadth, separately from accuracy (PRD P3).

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

    # The closed taxonomy of PRD §7.2. TEXT here and enforced in the application layer
    # at m9, because unlike session mode and status this vocabulary is expected to be
    # revised as real transcripts are read — and a taxonomy revision should be a code
    # change with a test, not an ALTER TYPE that cannot be run inside a transaction.
    category: Mapped[str] = mapped_column(Text, nullable=False)
    subcategory: Mapped[str | None] = mapped_column(Text)

    # Character offsets into turns.transcript, so the UI underlines the words rather
    # than restating them.
    span_start: Mapped[int | None] = mapped_column(Integer)
    span_end: Mapped[int | None] = mapped_column(Integer)

    original: Mapped[str] = mapped_column(Text, nullable=False)
    correction: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str | None] = mapped_column(Text)

    # Which layer produced this row. It is what lets m11 report LLM precision against
    # the rule layer instead of asserting it, and what lets a bad prompt be found by
    # querying rather than by reading transcripts.
    detector: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)

    __table_args__ = (
        CheckConstraint("detector IN ('llm', 'rule')", name="detector"),
        Index("ix_language_errors_turn_id_category", "turn_id", "category"),
    )


class ProgressSnapshot(Base):
    """Per-turn rows collapsed into one row per user per period.

    The progress page reads this and nothing else. A chart that aggregated raw turns on
    every page load would get slower every week the user practised, and the rollup is
    also where `sample_counts` is computed — which is what keeps a trend line off the
    screen until there is enough behind it to mean something (PRD P4: no phoneme trend
    under 5 scored attempts).

    JSONB per family rather than fifty columns: the set of fluency measures will change
    as m9 and m10 land, and a schema migration per metric added is a tax on exactly the
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
    # moves with the microphone and the room; PRD P4 is why nothing is compared across
    # users and why the z-scoring happens before anything is plotted.
    pronunciation: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    sample_counts: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )

    # An estimate, labelled as one. Out of scope to calibrate against human raters
    # (PRD §12), and the column exists so the estimate is recorded rather than
    # recomputed differently by each screen that shows it.
    cefr_estimate: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint("period IN ('day', 'week')", name="period"),
        UniqueConstraint(
            "user_id",
            "period",
            "period_start",
            name="uq_progress_snapshots_user_id_period_period_start",
        ),
    )
