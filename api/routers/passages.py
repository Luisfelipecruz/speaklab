"""Browsing the seeded read-aloud passages. FR-11.

Same shape as `scenarios.py`, one filter different: `phoneme_focus` instead of category
and grammar. That filter is what m10's recommendation endpoint will use — "picked
because your /θ/ is the worst phone in your last thirty attempts" is a sentence that
needs a way to ask for passages that exercise /θ/ (FR-24).
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from db_models import Passage
from models.common import CEFRBand
from models.passage import PassageDetail, PassageSummary

router = APIRouter(prefix="/passages", tags=["passages"])


@router.get("", response_model=list[PassageSummary])
async def list_passages(
    db: AsyncSession = Depends(get_db),
    band: CEFRBand | None = Query(None, description="Exact CEFR band."),
    phoneme_focus: str | None = Query(
        None,
        description=(
            "An ARPAbet phone the passage was written to exercise, uppercase and "
            "unstressed — `TH`, not `th` and not `TH1`. The 39 valid symbols are the "
            "ones the pronunciation service scores."
        ),
    ),
) -> list[Passage]:
    query = select(Passage).where(Passage.is_active.is_(True))

    if band is not None:
        query = query.where(Passage.cefr_band == band.value)
    if phoneme_focus is not None:
        query = query.where(Passage.phoneme_focus.contains([phoneme_focus]))

    query = query.order_by(Passage.cefr_band, Passage.title)
    return list((await db.scalars(query)).all())


@router.get("/{slug}", response_model=PassageDetail)
async def get_passage(slug: str, db: AsyncSession = Depends(get_db)) -> Passage:
    """One passage, with its body.

    This is the endpoint a read-aloud attempt is scored against: the WER at m8 compares
    the transcript with `body` as returned here, so whatever the user reads on screen
    and whatever the reference text is are the same string by construction.
    """
    passage = await db.scalar(select(Passage).where(Passage.slug == slug))
    if passage is None:
        raise HTTPException(status_code=404, detail=f"No passage with slug '{slug}'")
    return passage
