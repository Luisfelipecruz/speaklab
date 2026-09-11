"""The grammar page: your own sentences, the corrections proposed for them, and the verb
forms they were in.

One operation, scoped to the caller and taking no user id, like everything under
`/progress`. It is not under `/progress` because it answers a different question: that
page says whether you are getting better, from snapshots; this one says what to practise,
from the corrections themselves.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from db_models import User
from dependencies import current_user
from models.grammar import GrammarOut
from routers.progress import DaysQuery
from services import corrections as corrections_service

router = APIRouter(prefix="/grammar", tags=["grammar"])


@router.get("", response_model=GrammarOut)
async def get_grammar(
    days: int = DaysQuery,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> GrammarOut:
    """Your corrections by kind, the verb forms they changed, and the form to practise.

    Every correction comes in the sentence it was made in, because none was checked by a
    person and a learner can only disagree with one they can read. The verb forms carry
    counts and no percentage, and one is named for practice only once it has come up
    often enough and been corrected often enough that the corrections are unlikely all to
    be the detector's mistakes.
    """
    return await corrections_service.build(db, user, days)
