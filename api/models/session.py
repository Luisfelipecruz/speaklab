"""Session wire shapes.

`GET /sessions` is paginated where `GET /scenarios` is not, and the asymmetry is not an
inconsistency: eight seeded scenarios are eight seeded scenarios forever, while session
history is the one list in this system that grows without bound. An envelope with a total
and an offset is a promise about growth, and this is the endpoint that has to keep it.
"""

from datetime import datetime

from pydantic import BaseModel, Field

from models.common import ORMModel, Slug
from models.turn import TurnOut


class SessionCreate(BaseModel):
    """Starting a conversation. FR-6.

    A slug rather than an id, for the same reason `GET /scenarios/{slug}` takes one: the
    id is a database detail, and a client that has just read the catalogue is holding
    slugs. There is no `mode` field — every session this endpoint creates is a
    conversation. Read-aloud sessions are built around a passage and arrive with m8,
    and inventing the parameter now would mean shipping a value that is accepted and
    ignored.
    """

    scenario_slug: Slug


class SessionSummary(ORMModel):
    """One row of the history list.

    The scenario's slug and title are denormalised into the row rather than nested,
    because a list that renders "Job interview — backend engineer, 12 turns" should be
    one query and one flat object. `scenario_slug` is nullable for the same reason the
    column is: a read-aloud session has no scenario at all.
    """

    id: int
    scenario_slug: str | None
    scenario_title: str | None
    mode: str
    status: str
    started_at: datetime
    ended_at: datetime | None
    turn_count: int = Field(ge=0)


class SessionDetail(SessionSummary):
    """One session, opened: the full transcript. FR-10.

    The whole transcript, unpaginated, and that is a decision rather than an oversight.
    A conversation is bounded by the thing it is a conversation about — the seeded
    rubrics ask for eight to twelve turns — so this is tens of rows, not thousands, and
    paginating a transcript would make "reload the page and carry on" (FR-10) into a
    scroll-and-fetch problem for no measurable benefit.
    """

    turns: list[TurnOut]
    report: dict | None = None


class SessionPage(BaseModel):
    """A page of history, with enough to render a pager.

    `total` is a second query, and it is worth it: without it a client cannot tell the
    difference between the last page and a page that happened to come back short, which
    is the bug where the final few sessions become unreachable.
    """

    items: list[SessionSummary]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
