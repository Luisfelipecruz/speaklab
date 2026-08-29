"""The account, and the recordings it owns.

`AudioAsset` lives here rather than in a file of its own because audio has no meaning
apart from its owner: every path on the audio volume is reachable only through the user
who recorded it, and `GET /audio/{asset_id}` at m8 is an ownership check before it is
anything else.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db_models.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)

    # Argon2id, in argon2-cffi's encoded form: `$argon2id$v=19$m=...,t=...,p=...$salt$hash`.
    # The cost parameters travel inside each row, which is what lets them be raised later
    # without invalidating anything — `services/security.py` rehashes on the next
    # successful login. m3 resolved this: the requirements file shipped bcrypt and this
    # comment claimed argon2, and PRD FR-1 settled it in favour of argon2 (handoff Q6/D22).
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)

    # Selects the L1 phoneme priors at m8: which English sounds this speaker's first
    # language does not have is the difference between "your /v/ is weak" and a
    # prediction the system could have made before hearing anything.
    native_language: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="es"
    )
    cefr_self_assessed: Mapped[str | None] = mapped_column(Text)

    # FR-26. False means the waveform is deleted after scoring and only the derived
    # numbers survive — which is why every metric in the schema is stored, not
    # recomputed on demand from audio that may no longer exist.
    retain_audio: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    audio_assets: Mapped[list["AudioAsset"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class AudioAsset(Base):
    __tablename__ = "audio_assets"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # A path on the audio volume, never a blob. A 30-second recording is ~1 MB; putting
    # those in Postgres would put them in every backup and every pg_dump, and the
    # database would grow at the rate the user practises.
    path: Mapped[str] = mapped_column(Text, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    sample_rate: Mapped[int] = mapped_column(Integer, nullable=False)
    format: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)

    # PRD P4: GOP moves with microphone, room and distance from the mic. A trend that
    # cannot see the mic change reads a new headset as improvement.
    device_hint: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="audio_assets")

    __table_args__ = (
        # Same bytes from the same user twice is a double-submit, not a second attempt.
        # Scoped to the user rather than global: two people reading the same passage
        # are two attempts, even in the unlikely event the files are byte-identical.
        UniqueConstraint("user_id", "sha256", name="uq_audio_assets_user_id_sha256"),
    )
