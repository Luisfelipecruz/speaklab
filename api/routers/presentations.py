"""Rehearse a script of your own: save one, record a section, see the takes together.

Nine operations. The script is pasted, split where a reader would split it, and saved
with the words that cannot be turned into phones already named. A take is one recording
of one section: transcribed, compared with the section word by word, counted like a
spoken answer, and scored sound by sound in the background like a reading.

**The recording is kept only when the account keeps recordings.** Read-aloud refuses
without audio retention, because a reading can be scored again later and that needs the
waveform. A take is scored once, as it arrives, from the bytes in the request — so an
account that keeps nothing still gets every number, and loses only the replay.
"""

import logging

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import MAX_UPLOAD_BYTES, REHEARSAL_TAKES_PER_SECTION
from database import get_db
from db_models import PresentationSection, Rehearsal, RehearsalPhone, User
from dependencies import current_user
from models.presentation import (
    PresentationCreate,
    PresentationList,
    PresentationOut,
    PresentationPage,
    SectionOut,
    SectionTarget,
    SplitPreview,
    TakeList,
    TakeOut,
)
from services import rehearsals
from services.asr_client import AsrProtocolError, AsrRejected, AsrUnavailable
from services.audio import AudioTooLarge, delete_unreferenced_assets
from services.rehearsal_scoring import RehearsalScorer, get_rehearsal_scorer

router = APIRouter(prefix="/presentations", tags=["presentations"])
log = logging.getLogger("speaklab.presentations")


@router.post(
    "/preview",
    response_model=SplitPreview,
    responses={422: {"description": "The script is longer than a script may be."}},
)
async def preview_split(
    payload: PresentationCreate,
    user: User = Depends(current_user),
) -> SplitPreview:
    """See where a script would be split, and which words cannot be scored, before saving."""
    try:
        return await rehearsals.preview(payload.script)
    except rehearsals.Invalid as exc:
        raise _unprocessable(exc) from None


@router.post(
    "",
    response_model=PresentationOut,
    status_code=status.HTTP_201_CREATED,
    responses={
        422: {
            "description": "The script is too long, or the sections are not the script."
        }
    },
)
async def create_presentation(
    payload: PresentationCreate,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> PresentationOut:
    """Save a script and the sections it will be rehearsed in."""
    try:
        presentation = await rehearsals.create(db, user, payload)
    except rehearsals.Invalid as exc:
        raise _unprocessable(exc) from None

    page = await rehearsals.page(db, user, presentation.id)
    return page.presentation


@router.get("", response_model=PresentationList)
async def list_presentations(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> PresentationList:
    """Your scripts, the one worked on most recently first."""
    items, total = await rehearsals.listing(db, user, limit, offset)
    return PresentationList(items=items, total=total, limit=limit, offset=offset)


@router.get(
    "/{presentation_id}",
    response_model=PresentationPage,
    responses={404: {"description": "No script of yours with that id."}},
)
async def presentation_page(
    presentation_id: int,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> PresentationPage:
    """One script: its sections, how each has gone, and what to rehearse next."""
    try:
        return await rehearsals.page(db, user, presentation_id)
    except rehearsals.NotFound:
        raise _no_such_script(presentation_id) from None


@router.patch(
    "/{presentation_id}/sections/{idx}",
    response_model=SectionOut,
    responses={
        404: {"description": "No script of yours with that id, or no such section."},
        422: {"description": "A target time is between 1 and 600 seconds."},
    },
)
async def set_target(
    presentation_id: int,
    idx: int,
    payload: SectionTarget,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> SectionOut:
    """Set or clear the time you mean a section to take."""
    try:
        section = await rehearsals.section_at(db, user, presentation_id, idx)
    except rehearsals.NotFound:
        raise _no_such_script(presentation_id) from None

    section.target_seconds = payload.target_seconds
    await db.commit()
    await db.refresh(section)

    page = await rehearsals.page(db, user, presentation_id)
    return next(item for item in page.presentation.sections if item.idx == idx)


@router.delete(
    "/{presentation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"description": "No script of yours with that id."}},
)
async def delete_presentation(
    presentation_id: int,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a script, its takes, and any recording nothing else still points at.

    The sections and takes go by cascade. The audio does not — an asset is
    content-addressed and can be shared with a turn or a reading — so the assets this
    script's takes referenced are collected first and deleted only if nothing else still
    refers to them. Rows go before files, so a crash between the two wastes disk rather
    than leaving a row pointing at a recording that is gone.
    """
    try:
        presentation = await rehearsals.owned(db, user, presentation_id)
    except rehearsals.NotFound:
        raise _no_such_script(presentation_id) from None

    section_ids = [section.id for section in presentation.sections]
    asset_ids = {
        row
        for row in (
            await db.scalars(
                select(Rehearsal.audio_asset_id).where(
                    Rehearsal.section_id.in_(section_ids),
                    Rehearsal.audio_asset_id.isnot(None),
                )
            )
        ).all()
    }

    await db.delete(presentation)
    await db.flush()

    paths = await delete_unreferenced_assets(db, asset_ids)
    await db.commit()

    for path in paths:
        path.unlink(missing_ok=True)


@router.post(
    "/{presentation_id}/sections/{idx}/takes",
    response_model=TakeOut,
    status_code=status.HTTP_201_CREATED,
    responses={
        404: {"description": "No script of yours with that id, or no such section."},
        413: {"description": "The recording is over MAX_UPLOAD_BYTES."},
        422: {"description": "The recording could not be decoded, or held no speech."},
        502: {"description": "The recogniser answered with something unparseable."},
        503: {"description": "The recogniser is not available."},
    },
)
async def record_take(
    presentation_id: int,
    idx: int,
    file: UploadFile = File(..., description="You, saying the section out loud."),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    scorer: RehearsalScorer = Depends(get_rehearsal_scorer),
) -> TakeOut:
    """Say a section out loud and see it against the script, timed and counted."""
    try:
        section = await rehearsals.section_at(db, user, presentation_id, idx)
    except rehearsals.NotFound:
        raise _no_such_script(presentation_id) from None

    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"upload is {len(data)} bytes; the limit is {MAX_UPLOAD_BYTES}",
        )

    body = section.body
    scorable = section.scorable

    try:
        take = await rehearsals.take(
            db,
            user,
            section,
            data,
            filename=file.filename or "take",
            content_type=file.content_type,
            store_audio=bool(user.retain_audio),
        )
    except AudioTooLarge as exc:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail=str(exc)
        ) from exc
    except AsrRejected as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"The recording could not be read: {exc.detail}",
        ) from exc
    except AsrUnavailable as exc:
        log.warning("asr unavailable: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The speech recogniser is not responding. Your recording was not lost.",
        ) from exc
    except AsrProtocolError as exc:
        log.error("asr protocol skew: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The speech recogniser answered in a shape this API does not understand.",
        ) from exc
    except rehearsals.Invalid as exc:
        raise _unprocessable(exc) from None

    # Only a section whose every word converts is sent to the scorer. The rest have their
    # reason on the row already, and asking would earn a 422 the take cannot act on.
    if scorable:
        scorer.launch(take.id, data, body)

    return rehearsals.to_out(take, section)


@router.get(
    "/{presentation_id}/sections/{idx}/takes",
    response_model=TakeList,
    responses={
        404: {"description": "No script of yours with that id, or no such section."}
    },
)
async def list_takes(
    presentation_id: int,
    idx: int,
    limit: int = Query(REHEARSAL_TAKES_PER_SECTION, ge=1, le=50),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> TakeList:
    """Every take of one section, newest first, to read side by side."""
    try:
        section = await rehearsals.section_at(db, user, presentation_id, idx)
    except rehearsals.NotFound:
        raise _no_such_script(presentation_id) from None

    rows = (
        await db.scalars(
            select(Rehearsal)
            .where(Rehearsal.section_id == section.id)
            .order_by(Rehearsal.created_at.desc(), Rehearsal.id.desc())
            .limit(limit)
        )
    ).all()

    phones = await _phones_of(db, [row.id for row in rows])
    return TakeList(
        items=[rehearsals.to_out(row, section, phones.get(row.id, [])) for row in rows]
    )


@router.get(
    "/takes/{take_id}",
    response_model=TakeOut,
    responses={404: {"description": "No take of yours with that id."}},
)
async def get_take(
    take_id: int,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> TakeOut:
    """One take, polled while its sounds are still being scored."""
    try:
        take = await rehearsals.owned_take(db, user, take_id)
    except rehearsals.NotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No take with id {take_id}",
        ) from None

    section = await db.get(PresentationSection, take.section_id)
    phones = await _phones_of(db, [take.id])
    return rehearsals.to_out(take, section, phones.get(take.id, []))


async def _phones_of(
    db: AsyncSession, take_ids: list[int]
) -> dict[int, list[RehearsalPhone]]:
    if not take_ids:
        return {}
    rows = (
        await db.scalars(
            select(RehearsalPhone)
            .where(RehearsalPhone.rehearsal_id.in_(take_ids))
            .order_by(RehearsalPhone.word_idx, RehearsalPhone.phone_idx)
        )
    ).all()
    grouped: dict[int, list[RehearsalPhone]] = {}
    for row in rows:
        grouped.setdefault(row.rehearsal_id, []).append(row)
    return grouped


def _unprocessable(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
    )


def _no_such_script(presentation_id: int) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"No script with id {presentation_id}",
    )
