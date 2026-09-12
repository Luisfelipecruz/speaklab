"""Make your point: a spoken answer to a work prompt, counted and explained.

Two operations. `GET /answers` is the page: every prompt, this learner's answers — to one
prompt when `?prompt=` names it — and their history. `POST /answers` is one recording of
an answer, transcribed, counted, stored, and given to the language model for feedback.

**The answer is stored before the model is asked**, in three phases like a turn: the reads
and the upload with the connection held, the recogniser with none, then the write — and
only then the model, again with no connection held. A model that is down or slow costs
the explanation; the counts are already stored, and the feedback says what happened.

**The recording itself is not kept**, whatever the account's audio setting: the
transcript and the word timings are everything the page and the history are drawn from.
"""

import asyncio

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from config import MAX_UPLOAD_BYTES
from database import get_db
from db_models import Answer, User
from dependencies import current_user
from models.answer import AnswerOut, AnswersOut
from routers.turns import _transcribe
from services import answer_feedback, answers
from services.llm import LlmProvider, get_provider
from services.structure import words_of

router = APIRouter(prefix="/answers", tags=["answers"])


@router.get(
    "",
    response_model=AnswersOut,
    responses={404: {"description": "No prompt with that slug."}},
)
async def answers_page(
    prompt: str | None = Query(
        None, description="A prompt's slug: its answers instead of the latest."
    ),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> AnswersOut:
    """Every prompt, your answers, and how they have gone over time."""
    try:
        return await answers.page(db, user, prompt)
    except answers.NotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"No prompt {prompt!r}"
        ) from None


@router.post(
    "",
    response_model=AnswerOut,
    status_code=status.HTTP_201_CREATED,
    responses={
        404: {"description": "No such prompt, or no such earlier answer of yours."},
        409: {"description": "The earlier answer was to a different prompt."},
        413: {"description": "The recording is over MAX_UPLOAD_BYTES."},
        422: {"description": "The recording could not be decoded, or held no speech."},
        502: {"description": "The recogniser answered with something unparseable."},
        503: {"description": "The recogniser is not available."},
    },
)
async def answer(
    prompt: str = Form(..., description="The slug of the prompt being answered."),
    again_of: int | None = Form(
        None, description="An earlier answer of yours to the same prompt, said again."
    ),
    file: UploadFile = File(
        ..., description="You, answering. Any container ffmpeg reads."
    ),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    provider: LlmProvider = Depends(get_provider),
) -> AnswerOut:
    """Answer out loud; see how it was said, how it was built, and what a model made of it."""
    try:
        chosen = await answers.prompt_by_slug(db, prompt)
    except answers.NotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"No prompt {prompt!r}"
        ) from None
    if again_of is not None:
        try:
            earlier = await answers.owned_answer(db, user, again_of)
        except answers.NotFound:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No answer with id {again_of}",
            ) from None
        if earlier.prompt_id != chosen.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="That earlier answer was to a different prompt.",
            )

    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"upload is {len(data)} bytes; the limit is {MAX_UPLOAD_BYTES}",
        )

    # The connection goes back to the pool before the recogniser's seconds.
    await db.commit()
    transcription = await _transcribe(data, file)
    if not words_of(transcription.text):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Nothing was heard in that recording, so there is nothing to count.",
        )

    delivery, built = await asyncio.to_thread(answers.count, transcription)
    row = Answer(
        user_id=user.id,
        prompt_id=chosen.id,
        again_of=again_of,
        transcript=transcription.text,
        words=[word.model_dump() for word in transcription.words],
        duration_ms=transcription.source.duration_ms,
        asr_confidence=transcription.confidence,
        asr_model=transcription.model,
        delivery=delivery,
        structure=built,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    row.feedback = await answer_feedback.ask(
        provider, chosen.prompt, transcription.text
    )
    await db.commit()
    return answers.to_out(row, chosen)
