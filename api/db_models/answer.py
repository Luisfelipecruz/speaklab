"""Spoken answers: a prompt to answer out loud, and what the learner said.

**Tables of their own, not a kind of session.** A session is a conversation — a persona,
turns that alternate, a report at the end — and an answer is one recording with none of
those. Written as a session, every answer would also flow into the analysis that runs
behind each turn and into the weekly figures built from turns, and a prepared monologue
would start moving the conversation's speech rate and error rate without the speaker
changing at all.

**The recording is not kept.** The transcript, the word timings and what was counted from
them are, because they are what the page and the history are drawn from; the waveform is
transcribed and dropped, whatever the account's audio setting.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from db_models.base import Base


class AnswerPrompt(Base):
    """Seeded content, keyed by slug, like the scenarios and passages."""

    __tablename__ = "answer_prompts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)

    # What the learner reads before answering: the situation and who is asking.
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    cefr_band: Mapped[str] = mapped_column(Text, nullable=False)

    # How long the answer may run. The recorder stops itself here.
    time_limit_s: Mapped[int] = mapped_column(Integer, nullable=False)

    # Deactivated rather than deleted, so an answer's prompt is always there to show.
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )


class Answer(Base):
    """One spoken answer to a prompt, and everything counted from it."""

    __tablename__ = "answers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    prompt_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("answer_prompts.id"), nullable=False
    )

    # The answer this one says again, when it does. Two answers to the same prompt are
    # compared side by side; this is which two.
    again_of: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("answers.id", ondelete="SET NULL")
    )

    transcript: Mapped[str] = mapped_column(Text, nullable=False)
    words: Mapped[list[dict]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    asr_confidence: Mapped[float | None] = mapped_column(Float)
    asr_model: Mapped[str | None] = mapped_column(Text)

    # Speech rate, pauses and fillers, from the word timings.
    delivery: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Signposts, sentences, repeats and restarts, from the transcript.
    structure: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # What the language model said about the answer, with the check on its rewrite and
    # its own status. Null until it has been asked; never read by anything that draws a
    # line over time.
    feedback: Mapped[dict | None] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        # This learner's answers, newest first: the history and the side-by-side.
        Index("ix_answers_user_id_created_at", "user_id", "created_at"),
    )
