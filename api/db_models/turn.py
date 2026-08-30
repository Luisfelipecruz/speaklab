"""One utterance in a conversation, and the raw material every metric is derived from.

`words` is where §7.1 fluency comes from: `[{w, start_ms, end_ms, logprob}]` straight
off the ASR. It is JSONB rather than a `words` table because the array is read whole,
for exactly one purpose, and never queried across rows — a table would add ~150 rows per
turn and buy nothing. `language_errors` and `phoneme_scores` *are* tables precisely
because they are aggregated across rows, by category and by phone.

`asr_confidence` is the gate. PRD §7.5: a turn the recogniser was unsure of must not
contribute to an accuracy trend, because an ASR error scored as a grammar error is a
correction the user cannot act on and a trend line that moves for the wrong reason
(handoff trap 2).
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db_models.base import Base


class Turn(Base):
    __tablename__ = "turns"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )

    # Position in the conversation, unique within the session. The uniqueness is what
    # makes a retried turn overwrite rather than duplicate.
    idx: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)

    # Null for an assistant turn until m5 synthesises one, and null for a user turn
    # whose owner set retain_audio = false and whose waveform has been deleted.
    audio_asset_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("audio_assets.id")
    )
    transcript: Mapped[str | None] = mapped_column(Text)
    words: Mapped[list[dict] | None] = mapped_column(JSONB)
    asr_confidence: Mapped[float | None] = mapped_column(Float)

    # Which model produced the transcript. A WER comparison across a model upgrade is
    # meaningless without it, and "we changed the ASR in March" is exactly the kind of
    # thing that otherwise shows up as the user getting worse.
    asr_model: Mapped[str | None] = mapped_column(Text)

    # ── What produced an assistant turn (m6) ────────────────────────────────
    #
    # The same argument as `asr_model`, one row over. A reply written by `gemma3:4b`
    # and one written by whatever replaces it are different replies to the same
    # conversation, and a session report that compares this month against last month
    # needs to be able to see that the writer changed. Null on a user turn.
    llm_model: Mapped[str | None] = mapped_column(Text)

    # And which voice spoke it. Synthesis is non-deterministic (decision 0002), so the
    # audio cannot be re-derived from the text to find out after the fact — if this is
    # not recorded at the moment of synthesis it is not recoverable at all.
    tts_voice: Mapped[str | None] = mapped_column(Text)

    # Ollama's own count of what it read and what it wrote, taken from the response
    # rather than estimated. FR-8 bounds the history in tokens, and a bound nothing
    # ever measures is a bound nobody can show was respected: `services/conversation.py`
    # estimates the prompt size before the call because it must decide what to send,
    # and these two columns are what say afterwards how close that estimate was.
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)

    # Wall clock for the whole turn — upload to stored reply, not just the model call.
    # Recorded from the first turn ever served, because R3 is that latency regressions
    # are felt long before they are noticed.
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    session: Mapped["PracticeSession"] = relationship(  # noqa: F821
        back_populates="turns"
    )

    __table_args__ = (
        # Two values, so a CHECK rather than a native type — the enums in this schema
        # are the ones with three or more members and a real chance of growing.
        CheckConstraint("role IN ('user', 'assistant')", name="role"),
        UniqueConstraint("session_id", "idx", name="uq_turns_session_id_idx"),
    )
