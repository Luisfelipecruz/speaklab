"""the verb form each correction was said in, and the one it needs

**Two columns, and they are the join.** An error is filed under a taxonomy category and a
form is counted by the parser, and until now nothing connected the two: "your present
perfect is right seven times in ten" could not be computed from anything stored.
`language_errors.form` is the verb form of the words a correction changes, as the learner
said them, and `corrected_form` is the form the correction puts there. `I never went`
corrected to `I have never been` is `past_simple` and `present_perfect`.

**Nullable on both sides, and NULL is a finding.** `She going` has no finite form to be
said in; `enjoy to swim` corrects a complement no tense lives in; a preposition error is
not a correction of a verb at all. A default would claim a form the speaker did not use.

**TEXT, not an enum**, for the reason `category` is: the vocabulary is the parser's, it is
enforced in the application, and adding a form is a code change with a test rather than an
`ALTER TYPE`.

**Existing rows are left NULL here.** Filling them needs the parser, and a migration that
loads a language model is a migration that fails on a machine without one. `make reparse`
fills them from the stored transcripts and corrections, with no model call.

Revision ID: 0005
Revises: 0004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("language_errors", sa.Column("form", sa.Text(), nullable=True))
    op.add_column(
        "language_errors", sa.Column("corrected_form", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("language_errors", "corrected_form")
    op.drop_column("language_errors", "form")
