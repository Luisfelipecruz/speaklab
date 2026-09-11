"""Say it again: one of your corrections, practised aloud.

Two operations on one correction. `GET` is the sentence to say — the one you said, with
the correction in it — and `POST` is a recording of you saying it, compared word by word
with what the recogniser heard.

**Nothing is stored.** The recording is transcribed and compared, and neither it nor the
comparison is kept, whatever the account's retention setting: a repetition is not a
conversation, nothing is rescored later, and no page counts drills.

**Ownership runs through the turn.** A correction has no owner column; it belongs to a
turn, which belongs to a session, which has one. The join is in the query, and a
correction that is somebody else's is a 404 like one that does not exist.
"""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from config import MAX_UPLOAD_BYTES
from database import get_db
from db_models import User
from dependencies import current_user
from models.drill import DrillOut, DrillResult
from routers.turns import _transcribe
from services import drill as drill_service

router = APIRouter(prefix="/corrections", tags=["grammar"])


async def _drill(db: AsyncSession, user: User, error_id: int) -> DrillOut:
    try:
        return await drill_service.build(db, user, error_id)
    except drill_service.NotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No correction with id {error_id}",
        ) from None


@router.get(
    "/{error_id}/drill",
    response_model=DrillOut,
    responses={404: {"description": "No such correction, or not yours."}},
)
async def get_drill(
    error_id: int,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> DrillOut:
    """The sentence to say again, with every correction in it and the next one to practise.

    A correction that cannot be practised aloud — its words are not where its offsets say,
    or it changes only capitals or punctuation — comes back with no sentence and the
    reason, rather than as an error: it is still a correction worth reading.
    """
    return await _drill(db, user, error_id)


@router.post(
    "/{error_id}/drill",
    response_model=DrillResult,
    responses={
        404: {"description": "No such correction, or not yours."},
        409: {"description": "This correction cannot be practised aloud."},
        413: {"description": "The recording is over MAX_UPLOAD_BYTES."},
        422: {"description": "The recording could not be decoded."},
        502: {"description": "The recogniser answered with something unparseable."},
        503: {"description": "The recogniser is not available."},
    },
)
async def say_it_again(
    error_id: int,
    file: UploadFile = File(
        ..., description="You, saying the sentence. Any container ffmpeg reads."
    ),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> DrillResult:
    """Say the sentence; see what the recogniser heard, word by word and per correction."""
    drill = await _drill(db, user, error_id)
    if drill.unavailable:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=drill.unavailable
        )

    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"upload is {len(data)} bytes; the limit is {MAX_UPLOAD_BYTES}",
        )

    # Everything the comparison needs is in memory. The connection goes back to the pool
    # before the recogniser's second or so, as it does for a turn.
    await db.commit()
    transcription = await _transcribe(data, file)
    return drill_service.score(drill.pieces, transcription)
