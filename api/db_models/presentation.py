"""A script of the learner's own, its sections, and every take of each one.

**Tables of their own, like spoken answers and for the same reason.** A rehearsal is one
recording of a text the learner wrote, repeated as often as they like. It is not a
conversation, so it has no persona and no turns; and it is not a sample of how they speak
in the wild, so nothing here is rolled into the weekly figures. Practising one paragraph
forty times would otherwise move every trend on the progress page while the speaker was
doing the one thing trends are least able to describe.

**The script is kept whole as well as split.** `presentations.script` is what was pasted
and `presentation_sections` is the split of it; keeping both is what allows the split to
be redone without asking the learner for the text again.

**A take may have no audio.** Read-aloud refuses to score an account that does not retain
audio, because rescoring needs the waveform. A take is scored once, as it arrives, so the
waveform is only kept when the account keeps waveforms — `audio_asset_id` is nullable, and
a take without one cannot be replayed or rescored. That is the whole cost, and it is the
account's own setting.
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
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db_models.attempt import ATTEMPT_STATUS
from db_models.base import Base


class Presentation(Base):
    """One script, as pasted, with the sections it was split into."""

    __tablename__ = "presentations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    title: Mapped[str] = mapped_column(Text, nullable=False)

    # The whole text, kept so the split can be redone without asking for it again.
    script: Mapped[str] = mapped_column(Text, nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False)

    # The listener's brief, when one has been written. Null while nobody has asked for
    # one, which is every presentation until the learner wants questions put to them.
    audience_brief: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Touched by the service whenever a section or a take changes, so that the list can
    # be ordered by what was last worked on rather than by when it was pasted.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    sections: Mapped[list["PresentationSection"]] = relationship(
        back_populates="presentation",
        cascade="all, delete-orphan",
        order_by="PresentationSection.idx",
    )

    __table_args__ = (
        Index("ix_presentations_user_id_created_at", "user_id", "created_at"),
    )


class PresentationSection(Base):
    """One rehearsable piece of a script, about a paragraph long."""

    __tablename__ = "presentation_sections"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    presentation_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("presentations.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Position in the talk, from zero. Unique with the presentation, because two sections
    # in the same place is a split that cannot be rendered or navigated.
    idx: Mapped[int] = mapped_column(Integer, nullable=False)

    body: Mapped[str] = mapped_column(Text, nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False)

    # The time the learner means this section to take. Null is the ordinary state: a pace
    # is reported whether or not anyone said what it should be.
    target_seconds: Mapped[int | None] = mapped_column(Integer)

    # Whether every word can be turned into phones, decided when the script is saved.
    # False costs the section its per-phone scores and nothing else.
    scorable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )

    # The words that cost it, spelled as they were written, so they can be found and
    # respelled. Named rather than skipped: a word quietly dropped is a sound never
    # scored, and nothing on screen would say so.
    unscorable_words: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )

    presentation: Mapped["Presentation"] = relationship(back_populates="sections")
    takes: Mapped[list["Rehearsal"]] = relationship(
        back_populates="section", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint(
            "presentation_id",
            "idx",
            name="uq_presentation_sections_presentation_id_idx",
        ),
    )


class Rehearsal(Base):
    """One take of one section: what was heard, how it was said, and its sounds."""

    __tablename__ = "rehearsals"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    section_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("presentation_sections.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Carried on the row as well as reachable through the section, so that ownership is
    # one predicate rather than a three-table join on every request.
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # Null when the account does not retain audio. The take is scored on the way in, so
    # the absence costs it the replay and nothing else.
    audio_asset_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("audio_assets.id")
    )

    transcript: Mapped[str] = mapped_column(Text, nullable=False)
    words: Mapped[list[dict]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    asr_confidence: Mapped[float | None] = mapped_column(Float)
    asr_model: Mapped[str | None] = mapped_column(Text)

    # Against the section text, not against a passage: the reference is what the learner
    # wrote, which is the only thing a rehearsal can be compared with.
    wer: Mapped[float] = mapped_column(Float, nullable=False)

    # The aligned steps behind that rate — which words were missed, changed or added, and
    # which the recogniser was unsure of. Stored rather than recomputed, because the
    # recogniser is not deterministic across versions and the page must show what was
    # actually heard on the day.
    alignment: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Speech rate, pauses and fillers, from the word timings.
    delivery: Mapped[dict] = mapped_column(JSONB, nullable=False)

    pron_status: Mapped[str] = mapped_column(
        ATTEMPT_STATUS, nullable=False, server_default="pending"
    )

    # Why there are no phones, when there are none: a section whose words cannot be
    # converted, or a scorer that was not reachable. An absent reason reads as an absent
    # feature.
    pron_detail: Mapped[str | None] = mapped_column(Text)
    pron_summary: Mapped[dict | None] = mapped_column(JSONB)

    scored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    section: Mapped["PresentationSection"] = relationship(back_populates="takes")
    phones: Mapped[list["RehearsalPhone"]] = relationship(
        back_populates="rehearsal", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_rehearsals_section_id_created_at", "section_id", "created_at"),
    )


class RehearsalPhone(Base):
    """One scored phone of one take. The same row `phoneme_scores` holds for a reading.

    Separate from that table rather than a nullable column beside it: a phone scored in a
    rehearsal is scored against text the learner wrote, and the phone trends on the
    progress page are built from the shipped passages, where every speaker reads the same
    words. Mixing the two would let a learner move their own baseline by choosing what to
    write.
    """

    __tablename__ = "rehearsal_phones"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    rehearsal_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("rehearsals.id", ondelete="CASCADE"), nullable=False
    )

    word: Mapped[str] = mapped_column(Text, nullable=False)
    word_idx: Mapped[int] = mapped_column(Integer, nullable=False)
    phone_idx: Mapped[int] = mapped_column(Integer, nullable=False)

    canonical_phone: Mapped[str] = mapped_column(Text, nullable=False)

    # Nullable for the reason it is nullable on a reading: the aligner can report a
    # segment with no clear winner, and naming a substitution nothing asserted would be a
    # pronunciation claim from something that did not hear one.
    recognized_phone: Mapped[str | None] = mapped_column(Text)

    start_ms: Mapped[int | None] = mapped_column(Integer)
    end_ms: Mapped[int | None] = mapped_column(Integer)

    gop: Mapped[float] = mapped_column(Float, nullable=False)
    posterior: Mapped[float | None] = mapped_column(Float)

    rehearsal: Mapped["Rehearsal"] = relationship(back_populates="phones")

    __table_args__ = (Index("ix_rehearsal_phones_rehearsal_id", "rehearsal_id"),)
