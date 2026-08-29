"""One scored phone. The narrowest row in the schema and the reason it exists.

The pair that makes a score actionable is `canonical_phone` and `recognized_phone`:
*"your /θ/ is weak"* is a grade, and *"you are producing /s/ where English wants /θ/"*
is an instruction. GOP alone gives the first; the phone that actually won the posterior
gives the second.

    GOP(p) = log P(p | O_segment) − max over q of log P(q | O_segment)

so GOP is ≤ 0 by construction, near zero when the target sound won cleanly, and large
and negative when something else did. The m0 spike measured a drop of 8.14 nats between
a produced and an unproduced phone, Cohen's d = 8.26 — the separation this table is
built to record.

Two indexes, because there are two questions: everything about one attempt (the result
screen), and one phone's history for this user (the trend under it).
"""

from sqlalchemy import BigInteger, Float, ForeignKey, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db_models.base import Base


class PhonemeScore(Base):
    __tablename__ = "phoneme_scores"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    attempt_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("attempts.id", ondelete="CASCADE"), nullable=False
    )

    # The word and its position, so the result screen can tint the passage text
    # in place without re-aligning anything.
    word: Mapped[str] = mapped_column(Text, nullable=False)
    word_idx: Mapped[int] = mapped_column(Integer, nullable=False)
    phone_idx: Mapped[int] = mapped_column(Integer, nullable=False)

    canonical_phone: Mapped[str] = mapped_column(Text, nullable=False)

    # Nullable: the aligner can report a segment with no clear winner, and inventing a
    # substitution that the acoustic model did not actually assert would be exactly the
    # kind of claim invariant I2 exists to forbid.
    recognized_phone: Mapped[str | None] = mapped_column(Text)

    start_ms: Mapped[int | None] = mapped_column(Integer)
    end_ms: Mapped[int | None] = mapped_column(Integer)

    # Not nullable: a row here means a phone was scored. An unscored phone is an absent
    # row, not a row with a null score that averages into a trend as if it were data.
    gop: Mapped[float] = mapped_column(Float, nullable=False)
    posterior: Mapped[float | None] = mapped_column(Float)

    attempt: Mapped["Attempt"] = relationship(  # noqa: F821
        back_populates="phoneme_scores"
    )

    __table_args__ = (
        Index("ix_phoneme_scores_attempt_id", "attempt_id"),
        Index("ix_phoneme_scores_canonical_phone", "canonical_phone"),
    )
