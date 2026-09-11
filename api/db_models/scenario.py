"""A scenario: seeded content, not a prompt string.

The field that earns this table its existence is `target_grammar` — the forms the
scenario was *designed* to elicit. It is what lets the system ask a question no chat
app can answer: did this scenario actually make you produce present perfect, and were
you right when you did? A scenario whose declared forms never appear in any transcript
is a broken scenario, and the eval harness is what says so.

`persona_prompt` is deliberately never serialised to a client — see api/models/scenario.py.
"""

from sqlalchemy import BigInteger, Boolean, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from db_models.base import Base


class Scenario(Base):
    __tablename__ = "scenarios"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    # The seed key. Everything about a scenario can be edited in seeds/scenarios.json
    # and reloaded except this: the slug is what makes the load idempotent, and what a
    # user's session history points at across a content edit.
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    cefr_band: Mapped[str] = mapped_column(Text, nullable=False)

    # The system prompt for the conversation loop. Server-side only.
    persona_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    goal: Mapped[str] = mapped_column(Text, nullable=False)

    # JSONB rather than TEXT[] because these are read whole and filtered with the
    # containment operator (`@>`), which JSONB indexes with GIN when the seed set
    # grows past the point where a sequential scan over a dozen rows is free.
    target_grammar: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    target_functions: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    # Error taxonomy categories the scenario is built to draw out. `target_grammar` is in
    # the parser's vocabulary and cannot name an article or a false friend.
    target_errors: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    rubric: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")

    # Retiring a scenario must not orphan the sessions that used it, so content is
    # deactivated rather than deleted; sessions.scenario_id has no ON DELETE for the
    # same reason.
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
