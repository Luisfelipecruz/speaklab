"""Serving a stored recording back to the person who made it.

One operation, and it is an ownership check before it is anything else. `audio_assets`
has an integer primary key, so `GET /audio/41` is a guess anybody can make; the only
thing between a stranger and somebody's voice is `get_owned_or_404`, which folds
existence and ownership into a single `WHERE` so the check cannot be half-applied. A
row belonging to another account is **404, not 403** — a 403 would confirm the recording
exists, which is the fact the guesser was probing for.

There is no upload endpoint here, and that is not an omission. Audio enters the system
attached to something: a conversation turn (`POST /sessions/{id}/turns`) or a read-aloud
attempt (`POST /attempts`). A bare `POST /audio` would be a recording that belongs to
nothing, with no scenario, no passage and no reason to have been made — and something
would then have to decide what to do with the orphans. The pipeline those two endpoints
call is `services/audio.ingest_recording`.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from db_models import AudioAsset, User
from dependencies import current_user, get_owned_or_404
from services.audio import AudioPathError, resolve_path

router = APIRouter(prefix="/audio", tags=["audio"])

# ffmpeg's demuxer name to a media type. Explicit rather than `mimetypes.guess_type`,
# which works on file extensions — and the stored files deliberately have none.
# Anything not listed is served as a download rather than guessed at.
MEDIA_TYPES = {
    "wav": "audio/wav",
    "flac": "audio/flac",
    "ogg": "audio/ogg",
    "mp3": "audio/mpeg",
    "matroska,webm": "audio/webm",
    "mov,mp4,m4a,3gp,3g2,mj2": "audio/mp4",
}


@router.get(
    "/{asset_id}",
    response_class=FileResponse,
    responses={
        200: {"content": {"audio/*": {}}, "description": "The recording."},
        404: {"description": "No such recording, or it belongs to somebody else."},
    },
)
async def get_audio(
    asset_id: int,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    """Stream one recording. The caller must own it."""
    asset = await get_owned_or_404(db, AudioAsset, asset_id, user)

    try:
        path = resolve_path(asset)
    except AudioPathError as exc:
        # The row points outside the audio volume. Nothing in this codebase can write
        # such a row — the path is built from a digest this API computed — so reaching
        # here means the database was edited by something else. 500, loudly, rather
        # than reading the file and finding out what it was.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Stored path is outside the audio volume",
        ) from exc

    if not path.is_file():
        # The row survived its file. That is a normal state, not a corruption: an
        # account can turn off audio retention, after which the waveform is deleted and
        # only the derived numbers remain. 404 is the honest answer — the recording is
        # genuinely not there — and the row stays, because the metrics computed from it
        # still are.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"The recording for asset {asset_id} is no longer stored",
        )

    return FileResponse(
        path,
        media_type=MEDIA_TYPES.get(asset.format, "application/octet-stream"),
        # The stored file has no extension, so a client that saves this needs a name
        # from somewhere. The digest is the name it has.
        filename=f"{asset.sha256[:16]}",
    )
