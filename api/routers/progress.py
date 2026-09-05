"""Whether you are getting better, and what to practise next.

Three operations, and the split between them is the design. `GET /progress` reads
materialised snapshots and computes nothing; `POST /progress/refresh` is the only thing
that recomputes them; `GET /progress/recommendations` ranks the same stored rows into
advice. A page load that aggregated raw turns would get slower every week the user
practised, and it would get slower fastest for the people with the most to look at.

**Reading is cheap and says when it is behind.** The read path answers `stale` rather than
quietly rebuilding, so a page can offer a refresh instead of paying for one on every visit.
The rollup itself runs when a session ends, so `stale` is normally false and the button is
normally unnecessary — it is there for read-aloud scoring, which finishes after the request
that started it, and for turns analysed by a backfill.

Everything here is scoped to the caller and nothing takes a user id: there is no shape of
this API in which one account reads another's progress.
"""

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from config import PROGRESS_TREND_DAYS
from database import get_db
from db_models import User
from dependencies import current_user
from models.progress import ProgressOut, RecommendationsOut
from services import progress as progress_service
from services import recommend as recommend_service
from services import rollup as rollup_service

router = APIRouter(prefix="/progress", tags=["progress"])
log = logging.getLogger("speaklab.progress")

PeriodQuery = Query(
    "week",
    pattern="^(day|week)$",
    description=(
        "Granularity of the series. Weeks by default: a day is one evening's practice, "
        "and a trend drawn on daily points is mostly the gaps between them."
    ),
)

DaysQuery = Query(
    PROGRESS_TREND_DAYS,
    ge=7,
    le=365,
    description="How far back to look, in days.",
)


@router.get("", response_model=ProgressOut)
async def get_progress(
    period: str = PeriodQuery,
    days: int = DaysQuery,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> ProgressOut:
    """Trends for fluency, accuracy, breadth and pronunciation.

    Every series carries its own gate. A period with too little speech in it is a hole
    with a reason rather than a point, and a series with no periods above the floor comes
    back suppressed and says what it is waiting for — because a chart that silently omits
    thin data looks exactly like a speaker who did not practise.
    """
    return await progress_service.build(db, user.id, period=period, days=days)


@router.get("/recommendations", response_model=RecommendationsOut)
async def get_recommendations(
    days: int = DaysQuery,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> RecommendationsOut:
    """What to practise next, each with the measurement that chose it.

    A transparent weighted score over three stored sources — corrected categories, unused
    forms, weak sounds — decayed by how old the evidence is. `confidence` says how much
    the ranking rests on, in the same units the charts are gated on.
    """
    return await recommend_service.build(db, user.id, days=days)


@router.post("/refresh", response_model=ProgressOut)
async def refresh(
    period: str = PeriodQuery,
    days: int = DaysQuery,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> ProgressOut:
    """Recompute this account's snapshots, then return the page.

    Idempotent and bounded by how much this account has practised: periods whose newest
    turn is older than their snapshot are skipped, so calling it twice does the work once.
    It rewrites rather than merges, which is what lets a deleted session take its
    contribution back off the chart.
    """
    written = await rollup_service.rebuild_user(db, user.id)
    log.info("refresh rebuilt %d periods for user %s", len(written), user.id)
    return await progress_service.build(db, user.id, period=period, days=days)
