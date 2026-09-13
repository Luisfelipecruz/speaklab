"""per-turn analysis bookkeeping

**No tables.** `fluency_metrics`, `grammar_usage` and `language_errors` were all created
complete by 0001, so the analysers have somewhere to write from the first row. What was
missing is the bookkeeping that makes writing there *safe to repeat*, which is five
columns and one enum type.

* **`turns.analysis_status`** — the difference between "analysed, and this speaker made
  no mistakes" and "not analysed yet". Without it those two are the same empty result
  set, a backfill cannot tell which turns it still owes, and a session report showing no
  errors cannot say whether that is good news. The `analyzing` value is a claim: two jobs
  launched for one turn must not both write.

  **Nullable, and NULL is a fact rather than a gap.** Only a user turn is analysed; the
  persona's replies are not. A default of `pending` on those would leave every assistant
  turn permanently owing work that nothing will ever do.

* **`turns.analyzed_at` / `analysis_error`** — when it was done, and why it was not. The
  same pair `attempts.scored_at` and `error_message` are, for the same reason: a retry
  needs a reason in order to mean anything.

* **`turns.analysis_rejects`** — the proposals refused for being outside the closed
  taxonomy, or pointing at words that are not in the transcript, with a reason each.
  Counted rather than discarded because the *rate* is the measurement that says whether
  the model doing the labelling is strong enough, and the text says whether the taxonomy
  is missing a category instead. Neither is recoverable later from the rows that passed.

* **`language_errors.asr_suspect`** — this error sits on a word the recogniser was unsure
  of. It is shown to the learner and kept out of accuracy trends: a mishearing scored as
  a grammar error is a correction nobody can act on, and deleting it instead would leave
  a transcript with a hole in it.

Existing user turns are set to `pending` so the backfill finds them; assistant turns are
left NULL. The table is not empty this time, which is why the backfill is here rather
than in the code that reads the column.

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ANALYSIS_STATUS = postgresql.ENUM(
    "pending",
    "analyzing",
    "analyzed",
    "failed",
    name="analysis_status",
    create_type=False,
)


def upgrade() -> None:
    ANALYSIS_STATUS.create(op.get_bind(), checkfirst=False)

    op.add_column("turns", sa.Column("analysis_status", ANALYSIS_STATUS, nullable=True))
    op.add_column(
        "turns",
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("turns", sa.Column("analysis_error", sa.Text(), nullable=True))
    op.add_column(
        "turns",
        sa.Column(
            "analysis_rejects", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
    )

    op.add_column(
        "language_errors",
        sa.Column(
            "asr_suspect",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    op.execute("UPDATE turns SET analysis_status = 'pending' WHERE role = 'user'")


def downgrade() -> None:
    op.drop_column("language_errors", "asr_suspect")

    op.drop_column("turns", "analysis_rejects")
    op.drop_column("turns", "analysis_error")
    op.drop_column("turns", "analyzed_at")
    op.drop_column("turns", "analysis_status")

    # The type outlives its last column unless it is dropped explicitly, and a re-run of
    # the upgrade would then fail on `create_type=False`.
    ANALYSIS_STATUS.drop(op.get_bind(), checkfirst=False)
