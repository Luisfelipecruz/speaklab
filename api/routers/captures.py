"""Say it in English, and the Notebook it fills.

`POST /captures` is the panel: a recording or a text in, the English out, ready for the
clipboard. What was said in the account's own language is written in English, Organized
or Direct; English, said or typed, is checked, Corrected or Polished. The capture is kept
unless saving is paused — `201` with its row, or `200` with `id` null and nothing stored.
The other version and the phrases worth keeping are written behind the reply.

The rest is the Notebook: the list, one capture as the moment it was, a version written on
demand, the person writing it themselves and saying it aloud, deletion, and a warm-up the
app sends when fn goes down, so a model unloaded after a pause loads while they speak.

**Never the recording.** It is heard and dropped, whatever the account's audio setting,
because the moment kept is the words.
"""

import asyncio

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from config import (
    CAPTURE_PAGE_MAX,
    CAPTURE_PAGE_SIZE,
    MAX_UPLOAD_BYTES,
    SAY_MAX_TEXT_CHARS,
)
from database import get_db
from db_models import User
from dependencies import current_user
from models.capture import AttemptIn, AttemptOut, CaptureList, CaptureOut, SaidOut
from routers.turns import _transcribe
from services import captures as notebook
from services.asr_client import AsrProtocolError, AsrRejected, AsrUnavailable
from services.llm import LlmProvider, get_provider

router = APIRouter(prefix="/captures", tags=["notebook"])

MODES = ("auto", "translate", "check")
CHOSEN = ("organized", "direct", "corrected", "polished")

# Held for their lifetime, so a warm-up is not collected before it lands.
_warming: set[asyncio.Task] = set()


def _not_found(capture_id: int) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail=f"No capture with id {capture_id}"
    )


async def _owned(db: AsyncSession, user: User, capture_id: int):
    try:
        return await notebook.owned(db, user, capture_id)
    except notebook.NotFound:
        raise _not_found(capture_id) from None


@router.post(
    "",
    response_model=CaptureOut,
    status_code=status.HTTP_201_CREATED,
    responses={
        200: {"description": "Saving is paused: the English, and nothing kept."},
        413: {"description": "The recording is over MAX_UPLOAD_BYTES."},
        422: {
            "description": "Nothing was heard or typed, or the request is malformed."
        },
        502: {"description": "The recogniser answered with something unparseable."},
        503: {"description": "The recogniser, or for a typed text the model, is down."},
    },
)
async def make_capture(
    response: Response,
    audio: UploadFile | None = File(
        None, description="What was said. Any container the recogniser decodes."
    ),
    text: str | None = Form(None, description="What was typed or copied."),
    mode: str = Form(
        "auto",
        description="`translate` or `check` to say which; `auto` decides by the "
        "recogniser, or by the words for a text.",
    ),
    version: str | None = Form(
        None,
        description="The version to copy: organized, direct, corrected or polished; or "
        "one for each mode, comma-separated, such as `direct,polished`, for a recording "
        "whose language is not known yet.",
    ),
    app: str | None = Form(None, description="The app in front, as macOS names it."),
    via: str | None = Form(None, description="`typed` or `copied`, for a text."),
    save: bool = Form(True, description="False when saving is paused."),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    provider: LlmProvider = Depends(get_provider),
    writer: notebook.Writer = Depends(notebook.get_writer),
) -> CaptureOut:
    """Say it, type it or copy it; get the English, ready to paste.

    What is in the account's own language is translated, Organized or Direct; English is
    checked, Corrected or Polished, with every fix listed. The version asked for is written
    now and the other behind the reply. Saved unless `save` is false.
    """
    if (audio is None) == (text is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Send a recording or a text, one of them.",
        )
    if mode not in MODES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"mode is one of {', '.join(MODES)}",
        )
    wanted = tuple(v.strip() for v in (version or "").split(",") if v.strip())
    if any(v not in CHOSEN for v in wanted):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"version is one of {', '.join(CHOSEN)}, or one for each mode",
        )
    given = notebook.Given(mode=mode, versions=wanted, app=app, save=save)
    if audio is not None:
        data = await audio.read()
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"upload is {len(data)} bytes; the limit is {MAX_UPLOAD_BYTES}",
            )
        given.audio = data
        given.filename = audio.filename or "recording"
        given.content_type = audio.content_type
        given.via = "voice"
    else:
        if len(text) > SAY_MAX_TEXT_CHARS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"The text is {len(text)} characters; the limit is "
                f"{SAY_MAX_TEXT_CHARS}.",
            )
        if via not in (None, "typed", "copied"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="via is typed or copied, for a text",
            )
        given.text = text
        given.via = via or "typed"

    try:
        made = await notebook.make(db, user, given, provider)
    except notebook.NothingGiven as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    except notebook.ModelDown as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except AsrRejected as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"The recording could not be read: {exc.detail}",
        ) from exc
    except AsrUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The recogniser for your own language is not answering. Nothing was "
            "saved.",
        ) from exc
    except AsrProtocolError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The recogniser answered in a shape this API does not understand.",
        ) from exc

    if not save:
        response.status_code = status.HTTP_200_OK
        return notebook.made_out(made)
    row = notebook.store(db, user, made)
    await db.commit()
    await db.refresh(row)
    writer.launch(row.id)
    return await notebook.capture_out(db, row, notes=made.notes, language=made.language)


@router.get("", response_model=CaptureList)
async def list_captures(
    state: str | None = Query(
        None,
        pattern="^(to_practise|practised|due)$",
        description="Never written yourself, practised and not due yet, or due again.",
    ),
    mode: str | None = Query(
        None,
        pattern="^(translate|check)$",
        description="Only the translations, or only the checks.",
    ),
    app: str | None = Query(None, description="Only those said in this app."),
    q: str | None = Query(None, max_length=200, description="Text to look for."),
    limit: int = Query(CAPTURE_PAGE_SIZE, ge=1, le=CAPTURE_PAGE_MAX),
    offset: int = Query(0, ge=0),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> CaptureList:
    """The Notebook: your captures, newest first, with this week's counts."""
    return await notebook.listing(db, user, state, app, q, limit, offset, mode)


@router.post(
    "/warm",
    status_code=status.HTTP_202_ACCEPTED,
    responses={202: {"description": "Asked; the model loads behind the reply."}},
)
async def warm(
    user: User = Depends(current_user),
    provider: LlmProvider = Depends(get_provider),
) -> dict:
    """Ask the language model to load now, so the English is not kept waiting for it.

    Answers at once. The app sends it when fn goes down, so a model unloaded after a
    pause loads while the person is still speaking.
    """
    task = asyncio.create_task(provider.warm())
    _warming.add(task)
    task.add_done_callback(_warming.discard)
    return {"warming": provider.model}


@router.get(
    "/{capture_id}",
    response_model=CaptureOut,
    responses={404: {"description": "No such capture, or not yours."}},
)
async def get_capture(
    capture_id: int,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> CaptureOut:
    """One capture as the moment it was.

    What was said, where and when, every version, the phrases worth keeping, and what has
    been practised since.
    """
    capture = await _owned(db, user, capture_id)
    return await notebook.capture_out(db, capture)


@router.post(
    "/{capture_id}/versions/{version}",
    response_model=CaptureOut,
    responses={
        404: {"description": "No such capture, or not yours."},
        409: {"description": "A version this capture cannot have."},
        503: {"description": "The language model is not answering."},
    },
)
async def write_version(
    capture_id: int,
    version: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    writer: notebook.Writer = Depends(notebook.get_writer),
) -> CaptureOut:
    """Write a version now, if it is not written yet.

    The one being written behind the reply is waited for rather than asked for twice, so
    a click on the other version never waits on more than that version.
    """
    capture = await _owned(db, user, capture_id)
    try:
        capture = await writer.version(db, capture, version)
    except notebook.NotOffered:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A capture to {capture.mode} has no {version} version.",
        ) from None
    except notebook.ModelDown as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    return await notebook.capture_out(db, capture)


@router.delete(
    "/{capture_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"description": "No such capture, or not yours."}},
)
async def delete_capture(
    capture_id: int,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Delete one capture, with what you wrote of it and the mistakes found in that."""
    capture = await _owned(db, user, capture_id)
    await notebook.delete_one(db, capture)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("", status_code=status.HTTP_200_OK)
async def delete_captures(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Delete every capture of yours, with everything written of them."""
    return {"deleted": await notebook.delete_all(db, user)}


@router.post(
    "/{capture_id}/attempts",
    response_model=AttemptOut,
    status_code=status.HTTP_201_CREATED,
    responses={
        404: {"description": "No such capture, or not yours."},
        422: {"description": "Nothing was written."},
    },
)
async def write_it_yourself(
    capture_id: int,
    body: AttemptIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    provider: LlmProvider = Depends(get_provider),
) -> AttemptOut:
    """Write it in English yourself, and get the correction a conversation gets.

    Spelling from the dictionary, then the grammar rules and the model's proposals inside
    the closed taxonomy, the forms you used, your English beside the closer version, and
    when it comes back: a box up with no counted mistake, back to the first with any.
    """
    if len(body.text) > SAY_MAX_TEXT_CHARS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"The text is {len(body.text)} characters; the limit is "
            f"{SAY_MAX_TEXT_CHARS}.",
        )
    capture = await _owned(db, user, capture_id)
    try:
        return await notebook.attempt(db, user, capture, body.text, provider)
    except notebook.NothingGiven as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    except notebook.NotFound:
        raise _not_found(capture_id) from None


@router.post(
    "/{capture_id}/say",
    response_model=SaidOut,
    responses={
        404: {"description": "No such capture, or not yours."},
        413: {"description": "The recording is over MAX_UPLOAD_BYTES."},
        422: {"description": "The recording could not be decoded."},
        502: {"description": "The recogniser answered with something unparseable."},
        503: {"description": "The recogniser is not available."},
    },
)
async def say_it_yourself(
    capture_id: int,
    file: UploadFile = File(..., description="You, saying the English."),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> SaidOut:
    """Say the English aloud; see what the recogniser heard against the version you used.

    Heard by the English recogniser and compared word by word, as a drill is. Nothing is
    stored.
    """
    capture = await _owned(db, user, capture_id)
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"upload is {len(data)} bytes; the limit is {MAX_UPLOAD_BYTES}",
        )
    await db.commit()
    transcription = await _transcribe(data, file)
    return notebook.said(capture, transcription.text)
