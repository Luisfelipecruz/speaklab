"""One practice sitting.

The class is `PracticeSession`, not `Session`. The table is `sessions` and the domain
word is "session", but this module is imported into files that also import
`AsyncSession` and SQLAlchemy's own `Session`, and a bare `Session` there is a genuine
trap rather than a stylistic one.

`mode` and `status` are native Postgres enums. The alternative — TEXT with a CHECK, or
TEXT with nothing — puts the vocabulary in application code, where a typo in a string
literal writes a row nobody queries for again. As a type, `'compelted'` is rejected by
the database on the way in.
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import ENUM, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db_models.base import Base

# create_type=False everywhere: the types are created once, explicitly, by the Alembic
# revision. Left at the default, every CREATE TABLE referencing one would try to create
# it again and the second would fail.
SESSION_MODE = ENUM(
    "conversation", "read_aloud", name="session_mode", create_type=False
)
SESSION_STATUS = ENUM(
    "active", "completed", "abandoned", name="session_status", create_type=False
)


class PracticeSession(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # Nullable and with no ON DELETE: a read-aloud session has no scenario, and a
    # retired scenario is deactivated rather than deleted precisely so this reference
    # stays valid for the history that used it.
    scenario_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("scenarios.id")
    )

    mode: Mapped[str] = mapped_column(SESSION_MODE, nullable=False)
    status: Mapped[str] = mapped_column(
        SESSION_STATUS, nullable=False, server_default="active"
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # The end-of-session report (FR-9), stored as produced. It is a document read whole
    # by exactly one screen and never queried across rows; the numbers inside it are
    # also in fluency_metrics, grammar_usage and language_errors, which is where the
    # trends are computed from. Nothing on a chart is read from here (invariant I1).
    report: Mapped[dict | None] = mapped_column(JSONB)

    # ── The conversation's memory (m6, FR-8) ────────────────────────────────
    #
    # A running prose summary of the turns that no longer fit in the token budget.
    # FR-8 says oldest turns are *summarised rather than dropped*, and this column is
    # the difference between the two: without it, a scenario forgets the user's name at
    # turn twelve, which is not practice.
    context_digest: Mapped[str | None] = mapped_column(Text)

    # The highest `turns.idx` already folded into `context_digest`. It is what makes
    # summarisation incremental — without it every summarisation would either re-read
    # the whole conversation or double-count the turns it already covered, and the
    # digest would slowly restate the same three facts.
    #
    # -1 rather than NULL for "nothing summarised yet" is tempting and wrong: turn
    # indices start at 0, and a nullable column that means "before the first turn" is
    # honest about a session that has never needed summarising at all.
    digest_through_idx: Mapped[int | None] = mapped_column(Integer)

    turns: Mapped[list["Turn"]] = relationship(  # noqa: F821
        back_populates="session", cascade="all, delete-orphan"
    )

    __table_args__ = (
        # The history query: this user's sessions, newest first.
        #
        # Plan §5 writes this as `(user_id, started_at DESC)`. Ascending here, on
        # purpose: Postgres scans a btree in either direction, so for a single sort
        # column the DESC buys nothing — it matters only when columns are ordered in
        # opposite directions. What it would cost is real: a DESC index is an
        # expression index to SQLAlchemy, which `compare_metadata` cannot diff, so
        # test_migrations would stop being able to check this index at all.
        Index("ix_sessions_user_id_started_at", "user_id", "started_at"),
    )
