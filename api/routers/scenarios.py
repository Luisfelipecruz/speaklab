"""Browsing the seeded scenarios. FR-5.

Two operations, three filters, no pagination. Eight rows do not need a cursor, and an
envelope with `total` and `next` on a list that fits on one screen is a promise about
growth that nothing here is going to keep — `GET /sessions` at m6 is paginated because
session history actually grows.

The filters are `AND`ed. `?band=B2&category=workplace` means both, which is what a
sentence in a UI would mean.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from db_models import Scenario
from models.common import CEFRBand
from models.scenario import ScenarioDetail, ScenarioSummary

router = APIRouter(prefix="/scenarios", tags=["scenarios"])


@router.get("", response_model=list[ScenarioSummary])
async def list_scenarios(
    db: AsyncSession = Depends(get_db),
    band: CEFRBand | None = Query(
        None, description="Exact CEFR band. Unknown bands are rejected, not ignored."
    ),
    category: str | None = Query(None, description="Exact match, e.g. `workplace`."),
    target_grammar: str | None = Query(
        None,
        description=(
            "A grammatical form the scenario is designed to elicit, e.g. "
            "`present_perfect`. Matches scenarios whose declared list contains it."
        ),
    ),
) -> list[Scenario]:
    """The chooser.

    Ordered by band then title so the list is stable across calls — an unordered list
    endpoint returns rows in whatever order Postgres finds them, which changes after an
    UPDATE and makes a UI reshuffle itself for no visible reason.
    """
    query = select(Scenario).where(Scenario.is_active.is_(True))

    if band is not None:
        query = query.where(Scenario.cefr_band == band.value)
    if category is not None:
        query = query.where(Scenario.category == category)
    if target_grammar is not None:
        # JSONB containment (`@>`), so this is one indexable predicate rather than a
        # row-by-row scan in Python.
        query = query.where(Scenario.target_grammar.contains([target_grammar]))

    query = query.order_by(Scenario.cefr_band, Scenario.title)
    return list((await db.scalars(query)).all())


@router.get("/{slug}", response_model=ScenarioDetail)
async def get_scenario(slug: str, db: AsyncSession = Depends(get_db)) -> Scenario:
    """One scenario, by slug.

    Inactive scenarios are still fetchable by slug while being absent from the list.
    That is deliberate: a session started last month points at a scenario that may since
    have been retired, and its history has to keep rendering.
    """
    scenario = await db.scalar(select(Scenario).where(Scenario.slug == slug))
    if scenario is None:
        raise HTTPException(status_code=404, detail=f"No scenario with slug '{slug}'")
    return scenario
