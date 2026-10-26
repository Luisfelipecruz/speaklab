"""Say it in English: each capture, what the person wrote of it later, and the mistakes in that.

**A capture is a moment, kept as text.** What was said or typed, in which language, for
which app and when; the English versions written of it, and which one was copied. Never
the recording, whatever the account's audio setting says: the moment is the words, and a
waveform kept for it would be a recording of somebody's working day held for nothing.

**Written mistakes are a table of their own.** `written_errors` has the columns of
`language_errors` but hangs off an attempt rather than a turn, and has no recogniser to
doubt. Kept apart so that a mistake typed can never move a figure about speech: the two
are different skills, and the progress page counts them on different lines. It also holds
the one category speech never has, `SPELLING`, found by a dictionary.

**Practice comes back on a schedule.** `box` and `due_at` are the capture's place in it:
written with no counted mistake it moves up a box, with any it goes back to the first.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db_models.base import Base

# Every version a capture can carry. `rough` is the recogniser's own English, kept when
# the language model did not answer.
VERSIONS = ("direct", "organized", "corrected", "polished", "rough")


class Capture(Base):
    """One time the person asked for English, or for their English to be checked."""

    __tablename__ = "captures"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # `translate` from the person's own language; `check` for English they wrote or said.
    mode: Mapped[str] = mapped_column(Text, nullable=False)
    # Said, typed in the panel, or copied from wherever it was written.
    via: Mapped[str] = mapped_column(Text, nullable=False)
    source_language: Mapped[str] = mapped_column(Text, nullable=False)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer)

    # The app in front when it began, as macOS names it. Null in a browser, which cannot
    # know, and the only thing kept about the person's screen.
    app_name: Mapped[str | None] = mapped_column(Text)

    asr_model: Mapped[str | None] = mapped_column(Text)
    llm_model: Mapped[str | None] = mapped_column(Text)

    direct: Mapped[str | None] = mapped_column(Text)
    organized: Mapped[str | None] = mapped_column(Text)
    corrected: Mapped[str | None] = mapped_column(Text)
    polished: Mapped[str | None] = mapped_column(Text)
    rough: Mapped[str | None] = mapped_column(Text)
    # The version that went on the clipboard.
    chosen: Mapped[str] = mapped_column(Text, nullable=False)

    # For a check, the fixes the panel showed, to show them again. They are counted only
    # through the capture's first attempt, which a typed or copied check has and a spoken
    # one does not.
    fixes: Mapped[list[dict]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )

    # Per version, what the keep check found missing from it: names, numbers, links.
    dropped: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")

    # Milliseconds per stage, as the API saw them: recognition, generation, the whole.
    timings: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")

    box: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    attempts: Mapped[list["CaptureAttempt"]] = relationship(
        back_populates="capture",
        cascade="all, delete-orphan",
        order_by="CaptureAttempt.created_at",
    )
    phrases: Mapped[list["CapturePhrase"]] = relationship(
        back_populates="capture",
        cascade="all, delete-orphan",
        order_by="CapturePhrase.id",
    )

    __table_args__ = (
        CheckConstraint("mode IN ('translate', 'check')", name="mode"),
        CheckConstraint("via IN ('voice', 'typed', 'copied')", name="via"),
        CheckConstraint(
            "chosen IN ('direct', 'organized', 'corrected', 'polished', 'rough')",
            name="chosen",
        ),
        Index("ix_captures_user_id_created_at", "user_id", "created_at"),
    )


class CaptureAttempt(Base):
    """The person writing a capture's English themselves."""

    __tablename__ = "capture_attempts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    capture_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("captures.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    text: Mapped[str] = mapped_column(Text, nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False)

    # The version it is closest to, which the word-by-word comparison is drawn against.
    compared_with: Mapped[str | None] = mapped_column(Text)

    # The verb forms and structures the parser counted in it, as `grammar_usage` counts
    # them in a turn.
    forms: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")

    # The capture's box once this attempt was counted.
    box: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    # What the check could not do, when it could not: the language model was down, so its
    # proposals are missing and only the dictionary's and the rules' are here.
    detail: Mapped[str | None] = mapped_column(Text)
    # The model's proposals that were not stored, each with its reason, as a turn keeps
    # them: the rate at which they are refused measures the model.
    rejects: Mapped[list[dict] | None] = mapped_column(JSONB)

    capture: Mapped["Capture"] = relationship(back_populates="attempts")
    errors: Mapped[list["WrittenError"]] = relationship(
        back_populates="attempt",
        cascade="all, delete-orphan",
        order_by="WrittenError.span_start",
    )

    __table_args__ = (
        Index("ix_capture_attempts_capture_id_created_at", "capture_id", "created_at"),
    )


class WrittenError(Base):
    """One mistake in something the person wrote, with its span, category and source."""

    __tablename__ = "written_errors"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    attempt_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("capture_attempts.id", ondelete="CASCADE"),
        nullable=False,
    )

    # The closed taxonomy, and SPELLING, which only written text can have.
    category: Mapped[str] = mapped_column(Text, nullable=False)
    subcategory: Mapped[str | None] = mapped_column(Text)

    # Character offsets into the attempt's text.
    span_start: Mapped[int | None] = mapped_column(Integer)
    span_end: Mapped[int | None] = mapped_column(Integer)

    original: Mapped[str] = mapped_column(Text, nullable=False)
    correction: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str | None] = mapped_column(Text)

    # `dictionary` for spelling, beside the conversation detector's `llm` and `rule`.
    detector: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)

    attempt: Mapped["CaptureAttempt"] = relationship(back_populates="errors")

    __table_args__ = (
        CheckConstraint("detector IN ('llm', 'rule', 'dictionary')", name="detector"),
        Index("ix_written_errors_attempt_id", "attempt_id"),
    )


class CapturePhrase(Base):
    """A phrase the person said and the English the version used for it.

    Picked by the language model and kept only when both halves are found, word for word,
    in the texts they are quoted from. How often the English turns up in the person's
    other captures is counted when the page is read, by plain code.
    """

    __tablename__ = "capture_phrases"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    capture_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("captures.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[str] = mapped_column(Text, nullable=False)
    english: Mapped[str] = mapped_column(Text, nullable=False)

    capture: Mapped["Capture"] = relationship(back_populates="phrases")

    __table_args__ = (Index("ix_capture_phrases_capture_id", "capture_id"),)
