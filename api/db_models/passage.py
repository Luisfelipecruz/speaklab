"""A read-aloud passage, written to force a sound rather than to mention it.

`phoneme_focus` is a promise about the text: a passage declaring `["TH"]` is engineered
so a speaker who substitutes /s/ for /θ/ cannot get through it unnoticed. That is the
difference between a passage that contains "think" once and one that scores a phoneme
with enough samples to mean something: no phoneme trend is shown under 5 attempts, and
a passage with only two instances of its target sound wastes an attempt.

`word_count` is stored rather than computed on read because it is a property of the
seed content that a test can check against `body`, which is how a passage that was
edited without its count being updated becomes a red test instead of a wrong estimate
of how long the reading takes.
"""

from sqlalchemy import BigInteger, Boolean, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from db_models.base import Base


class Passage(Base):
    __tablename__ = "passages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    cefr_band: Mapped[str] = mapped_column(Text, nullable=False)

    # ARPAbet, uppercase, unstressed — ["TH", "V", "IH"]. The 39-symbol set is named in
    # api/models/common.py, and infra/pron/phone_map.py asserts its keys equal it.
    phoneme_focus: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    word_count: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
