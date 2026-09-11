"""the kinds of mistake a scenario is built to draw out

**A second declaration beside `target_grammar`, because the first cannot say it.** A
scenario declares the forms it elicits in the parser's vocabulary — tenses, modals,
clause types — and that vocabulary has no word for an article, a preposition or a false
friend: those exist only as the categories the detector files corrections under.
`scenarios.target_errors` holds those category names, so a scenario written to draw out
articles can say so, and a learner corrected on articles can be pointed at it.

**JSONB, like the two lists beside it**, read whole and matched by containment.

**Existing rows get an empty list here.** What each scenario declares is content, and
content lives in `seeds/scenarios.json`: `make seed` fills the column, as it fills every
other one.

Revision ID: 0006
Revises: 0005
Created: 2026-09-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "scenarios",
        sa.Column(
            "target_errors",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
    )


def downgrade() -> None:
    op.drop_column("scenarios", "target_errors")
