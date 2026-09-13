"""when a progress snapshot was last computed

**One column.** `progress_snapshots` was created complete by 0001 — the five JSONB
families, the CEFR estimate, the period check and the unique key are all already there,
because the shape of a rollup was decided with the schema rather than discovered later.

What was missing is the one thing a materialised aggregate cannot do without: a record
of *when* it was materialised. Without it there is no way to ask whether a snapshot is
still current. The rows it summarises carry their own timestamps — `turns.analyzed_at`,
`attempts.scored_at` — so "is there anything newer than this snapshot" is a question with
an exact answer, and this column is the other half of it. Lacking it, the only available
answers are "recompute everything on every page load", which is what a snapshot table
exists to avoid, and "assume it is fresh", which is how a chart quietly stops moving.

`server_default=now()` so the existing rows get a defensible value rather than NULL. On
this database there are none, which is why the default is about the next deployment
rather than this one.

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "progress_snapshots",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_column("progress_snapshots", "updated_at")
