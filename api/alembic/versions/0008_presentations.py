"""a script of the learner's own, its sections and its takes

**Four tables, and nothing changed elsewhere.** A rehearsal is one recording of a text the
learner wrote, repeated as often as they like: no persona, no turns, and nothing that
feeds the weekly figures, which are built from conversation and from the shipped passages.
Practising one paragraph forty times would otherwise move every trend on the progress page.

`presentations` keeps the script whole as well as split, so the split can be redone.
`presentation_sections` is the split, with the words the converter cannot turn into phones
recorded per section. `rehearsals` is one take — the transcript, the alignment against the
section, the delivery counts and the state of its phone scoring — and its `audio_asset_id`
is nullable, because an account that does not retain audio still gets everything except
the replay. `rehearsal_phones` is the same row `phoneme_scores` holds for a reading, kept
apart so that text a learner chose cannot move the phone baselines built from the passages
everybody reads.

`attempt_status` is reused for the scoring lifecycle rather than a second enum with the
same four values; it is created in `0001` and is not created or dropped here.

Revision ID: 0008
Revises: 0007
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "presentations",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("script", sa.Text(), nullable=False),
        sa.Column("word_count", sa.Integer(), nullable=False),
        sa.Column("audience_brief", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_presentations_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_presentations"),
    )
    op.create_index(
        "ix_presentations_user_id_created_at",
        "presentations",
        ["user_id", "created_at"],
    )

    op.create_table(
        "presentation_sections",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("presentation_id", sa.BigInteger(), nullable=False),
        sa.Column("idx", sa.Integer(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("word_count", sa.Integer(), nullable=False),
        sa.Column("target_seconds", sa.Integer(), nullable=True),
        sa.Column("scorable", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "unscorable_words",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["presentation_id"],
            ["presentations.id"],
            name="fk_presentation_sections_presentation_id_presentations",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_presentation_sections"),
        sa.UniqueConstraint(
            "presentation_id",
            "idx",
            name="uq_presentation_sections_presentation_id_idx",
        ),
    )

    op.create_table(
        "rehearsals",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("section_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("audio_asset_id", sa.BigInteger(), nullable=True),
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
        sa.Column("wer", sa.Float(), nullable=False),
        sa.Column("alignment", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("delivery", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "pron_status",
            postgresql.ENUM(
                "pending",
                "scoring",
                "scored",
                "failed",
                name="attempt_status",
                create_type=False,
            ),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("pron_detail", sa.Text(), nullable=True),
        sa.Column(
            "pron_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("scored_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["section_id"],
            ["presentation_sections.id"],
            name="fk_rehearsals_section_id_presentation_sections",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_rehearsals_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["audio_asset_id"],
            ["audio_assets.id"],
            name="fk_rehearsals_audio_asset_id_audio_assets",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_rehearsals"),
    )
    op.create_index(
        "ix_rehearsals_section_id_created_at",
        "rehearsals",
        ["section_id", "created_at"],
    )

    op.create_table(
        "rehearsal_phones",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("rehearsal_id", sa.BigInteger(), nullable=False),
        sa.Column("word", sa.Text(), nullable=False),
        sa.Column("word_idx", sa.Integer(), nullable=False),
        sa.Column("phone_idx", sa.Integer(), nullable=False),
        sa.Column("canonical_phone", sa.Text(), nullable=False),
        sa.Column("recognized_phone", sa.Text(), nullable=True),
        sa.Column("start_ms", sa.Integer(), nullable=True),
        sa.Column("end_ms", sa.Integer(), nullable=True),
        sa.Column("gop", sa.Float(), nullable=False),
        sa.Column("posterior", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(
            ["rehearsal_id"],
            ["rehearsals.id"],
            name="fk_rehearsal_phones_rehearsal_id_rehearsals",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_rehearsal_phones"),
    )
    op.create_index(
        "ix_rehearsal_phones_rehearsal_id", "rehearsal_phones", ["rehearsal_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_rehearsal_phones_rehearsal_id", table_name="rehearsal_phones")
    op.drop_table("rehearsal_phones")
    op.drop_index("ix_rehearsals_section_id_created_at", table_name="rehearsals")
    op.drop_table("rehearsals")
    op.drop_table("presentation_sections")
    op.drop_index("ix_presentations_user_id_created_at", table_name="presentations")
    op.drop_table("presentations")
