"""captures for Say it in English, the person's own attempts, and what was wrong in them

**Four tables, and nothing changed elsewhere.** A capture is one time the person asked for
English — said, typed or copied — kept as text and never as a recording: what was said,
in which language, for which app, the versions written of it and which one was copied.
`capture_attempts` is the person writing it themselves later, and `written_errors` the
mistakes found in that, with the columns of `language_errors`, an attempt in place of a
turn, and no recogniser to doubt. They are a table of their own so that a written mistake
can never move a figure about speech. `capture_phrases` is the phrases worth keeping.

Every row goes with its account, and an attempt's errors with the attempt.

Revision ID: 0009
Revises: 0008
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "captures",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("via", sa.Text(), nullable=False),
        sa.Column("source_language", sa.Text(), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("app_name", sa.Text(), nullable=True),
        sa.Column("asr_model", sa.Text(), nullable=True),
        sa.Column("llm_model", sa.Text(), nullable=True),
        sa.Column("direct", sa.Text(), nullable=True),
        sa.Column("organized", sa.Text(), nullable=True),
        sa.Column("corrected", sa.Text(), nullable=True),
        sa.Column("polished", sa.Text(), nullable=True),
        sa.Column("rough", sa.Text(), nullable=True),
        sa.Column("chosen", sa.Text(), nullable=False),
        sa.Column(
            "fixes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column(
            "dropped",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "timings",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("box", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("mode IN ('translate', 'check')", name="ck_captures_mode"),
        sa.CheckConstraint(
            "via IN ('voice', 'typed', 'copied')", name="ck_captures_via"
        ),
        sa.CheckConstraint(
            "chosen IN ('direct', 'organized', 'corrected', 'polished', 'rough')",
            name="ck_captures_chosen",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_captures_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_captures"),
    )
    op.create_index(
        "ix_captures_user_id_created_at", "captures", ["user_id", "created_at"]
    )

    op.create_table(
        "capture_attempts",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("capture_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("word_count", sa.Integer(), nullable=False),
        sa.Column("compared_with", sa.Text(), nullable=True),
        sa.Column(
            "forms",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("box", sa.SmallInteger(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("rejects", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(
            ["capture_id"],
            ["captures.id"],
            name="fk_capture_attempts_capture_id_captures",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_capture_attempts"),
    )
    op.create_index(
        "ix_capture_attempts_capture_id_created_at",
        "capture_attempts",
        ["capture_id", "created_at"],
    )

    op.create_table(
        "written_errors",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("attempt_id", sa.BigInteger(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("subcategory", sa.Text(), nullable=True),
        sa.Column("span_start", sa.Integer(), nullable=True),
        sa.Column("span_end", sa.Integer(), nullable=True),
        sa.Column("original", sa.Text(), nullable=False),
        sa.Column("correction", sa.Text(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("detector", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.CheckConstraint(
            "detector IN ('llm', 'rule', 'dictionary')",
            name="ck_written_errors_detector",
        ),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["capture_attempts.id"],
            name="fk_written_errors_attempt_id_capture_attempts",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_written_errors"),
    )
    op.create_index("ix_written_errors_attempt_id", "written_errors", ["attempt_id"])

    op.create_table(
        "capture_phrases",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("capture_id", sa.BigInteger(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("english", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["capture_id"],
            ["captures.id"],
            name="fk_capture_phrases_capture_id_captures",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_capture_phrases"),
    )
    op.create_index("ix_capture_phrases_capture_id", "capture_phrases", ["capture_id"])


def downgrade() -> None:
    op.drop_index("ix_capture_phrases_capture_id", table_name="capture_phrases")
    op.drop_table("capture_phrases")
    op.drop_index("ix_written_errors_attempt_id", table_name="written_errors")
    op.drop_table("written_errors")
    op.drop_index(
        "ix_capture_attempts_capture_id_created_at", table_name="capture_attempts"
    )
    op.drop_table("capture_attempts")
    op.drop_index("ix_captures_user_id_created_at", table_name="captures")
    op.drop_table("captures")
