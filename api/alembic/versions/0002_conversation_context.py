"""conversation context and turn provenance

Six columns, no tables. `sessions` and `turns` were both created complete by 0001, so
this revision adds only what the conversation loop turned out to need:

* **`sessions.context_digest` / `digest_through_idx`** — the history is bounded in tokens
  and the turns that fall out of the window are *summarised, not dropped*. The
  digest is that summary and the index is how far it reaches, which is what makes
  summarising incremental rather than a full re-read every turn.

* **`turns.llm_model` / `tts_voice`** — the same provenance `asr_model` already records,
  for the reply writer and the voice. Synthesis is non-deterministic, so a voice not
  recorded at the moment it spoke is not recoverable afterwards.

* **`turns.prompt_tokens` / `completion_tokens`** — Ollama's own counts, so the token
  budget is a measured bound rather than an asserted one.

Revisions are numbered in the order they exist, not against any external list: this is
simply the revision after 0001.

Every column is nullable and none has a server default. There is no data to backfill —
`turns` and `sessions` are empty until this milestone writes the first row — and a
NOT NULL with a default here would invent a value for rows that describe a conversation
that never happened.

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("context_digest", sa.Text(), nullable=True))
    op.add_column(
        "sessions", sa.Column("digest_through_idx", sa.Integer(), nullable=True)
    )

    op.add_column("turns", sa.Column("llm_model", sa.Text(), nullable=True))
    op.add_column("turns", sa.Column("tts_voice", sa.Text(), nullable=True))
    op.add_column("turns", sa.Column("prompt_tokens", sa.Integer(), nullable=True))
    op.add_column("turns", sa.Column("completion_tokens", sa.Integer(), nullable=True))


def downgrade() -> None:
    # Reverse order of the adds, which costs nothing here and is the habit that matters
    # on a revision where the objects depend on each other.
    op.drop_column("turns", "completion_tokens")
    op.drop_column("turns", "prompt_tokens")
    op.drop_column("turns", "tts_voice")
    op.drop_column("turns", "llm_model")

    op.drop_column("sessions", "digest_through_idx")
    op.drop_column("sessions", "context_digest")
