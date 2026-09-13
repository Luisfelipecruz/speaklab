"""spoken answers and the prompts they answer

**Two tables, and no change to `sessions`.** An answer is one recording to a prompt, with
no persona, no turns and no report, so it is not a kind of session. As a session it would
also be analysed like a conversation turn and counted into the weekly figures built from
turns, and a prepared monologue would move the conversation's speech rate without the
speaker changing.

`answer_prompts` is seeded content, keyed by slug like the scenarios; `make seed` fills
it. `answers` keeps the transcript, the word timings and what was counted from them —
never the recording. `again_of` links a second attempt to the answer it says again, and
is cleared rather than cascaded when that answer goes.

Revision ID: 0007
Revises: 0006
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "answer_prompts",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("cefr_band", sa.Text(), nullable=False),
        sa.Column("time_limit_s", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_answer_prompts"),
        sa.UniqueConstraint("slug", name="uq_answer_prompts_slug"),
    )

    op.create_table(
        "answers",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("prompt_id", sa.BigInteger(), nullable=False),
        sa.Column("again_of", sa.BigInteger(), nullable=True),
        sa.Column("transcript", sa.Text(), nullable=False),
        sa.Column(
            "words",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("asr_confidence", sa.Float(), nullable=True),
        sa.Column("asr_model", sa.Text(), nullable=True),
        sa.Column("delivery", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("structure", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("feedback", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_answers_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["prompt_id"],
            ["answer_prompts.id"],
            name="fk_answers_prompt_id_answer_prompts",
        ),
        sa.ForeignKeyConstraint(
            ["again_of"],
            ["answers.id"],
            name="fk_answers_again_of_answers",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_answers"),
    )
    op.create_index(
        "ix_answers_user_id_created_at", "answers", ["user_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_answers_user_id_created_at", table_name="answers")
    op.drop_table("answers")
    op.drop_table("answer_prompts")
