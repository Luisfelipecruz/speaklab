"""One read-aloud reading of one passage.

Scoring is asynchronous — the pipeline is ffmpeg, faster-whisper, G2P, wav2vec2 and
forced alignment, which is seconds of work, not milliseconds — so an attempt is a row
with a lifecycle rather than a request that returns a score. `status` is that lifecycle,
and `error_message` is what lets a failed attempt say *why* it failed and be retried,
which is impossible if failure is only an absent score.
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db_models.base import Base

ATTEMPT_STATUS = ENUM(
    "pending", "scoring", "scored", "failed", name="attempt_status", create_type=False
)


class Attempt(Base):
    __tablename__ = "attempts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )

    # No ON DELETE on either of these. A passage is deactivated rather than deleted,
    # and an attempt without its audio cannot be rescored, so allowing the audio to
    # vanish would make rescoring a promise the schema could not keep.
    passage_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("passages.id"), nullable=False
    )
    audio_asset_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("audio_assets.id"), nullable=False
    )

    transcript: Mapped[str | None] = mapped_column(Text)

    # Word error rate against the passage body. It is the reading-accuracy number and
    # also the sanity check on the alignment: a WER near 1.0 means the speaker read
    # something else, and per-phoneme GOP against the wrong text is noise.
    wer: Mapped[float | None] = mapped_column(Float)

    status: Mapped[str] = mapped_column(
        ATTEMPT_STATUS, nullable=False, server_default="pending"
    )
    error_message: Mapped[str | None] = mapped_column(Text)
    scored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    phoneme_scores: Mapped[list["PhonemeScore"]] = relationship(  # noqa: F821
        back_populates="attempt", cascade="all, delete-orphan"
    )
