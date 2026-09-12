"""Spoken answers: counting one, and reading them back.

An answer is counted twice over, by two different pieces of arithmetic: how it was said,
from the word timings (`services/fluency.py`, the same numbers a conversation turn gets),
and how it was built, from the transcript (`services/structure.py`). Both are stored whole,
so a page drawn next year shows what was counted that day.

**Only the measures that cleared their bar are sent.** The structure counter stores every
count, including the ones it cannot yet make reliably; `structure.SHOWN` decides what
leaves this module, so a measure can be shown the day it clears its bar without the stored
answers changing.

**The history draws each answer as a point**, oldest first, in the progress page's shape
and by its rule: a direction only for a measure with a better end, and only once there are
enough points to compare. Fewer fillers and fewer words said twice have a better end.
Speech rate, pauses, sentence length and signposts do not, and are drawn and never judged —
an answer with more signposts is not a better answer.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import (
    ANSWER_HISTORY_LIMIT,
    ANSWERS_PER_PROMPT,
    PROGRESS_MIN_POINTS,
    PROGRESS_MIN_WORDS,
)
from db_models import Answer, AnswerPrompt, User
from models.answer import (
    AnswerOut,
    AnswersOut,
    Counted,
    Delivery,
    Feedback,
    PromptOut,
    PromptSummary,
    StructureOut,
)
from models.audio import Transcription
from models.progress import Gate, Point, Series
from services import fluency, structure
from services.answer_feedback import FEEDBACK_CAVEAT

STRUCTURE_CAVEAT = (
    "Counted from the transcript. Signposts are the words that show how an answer is "
    "built: a reason, an example, a step, a contrast, a summing up. More is not better — an "
    "answer needs the ones its idea needs. Sentences are where the recogniser put full "
    "stops, and a phrase started again is counted but not shown, because it is not yet "
    "counted reliably."
)

HISTORY_CAVEAT = (
    "One point per answer, whichever prompt it answered, and different prompts ask for "
    "different answers: a walk-through has more steps in it than a recommendation. Fewer "
    "fillers and fewer words said twice are marked as improving or slipping once there are "
    "three answers; nothing else is, because nothing else has a better end."
)

# Category order on the page: what happened, why, how, and what to do.
_CATEGORY_ORDER = {"explain": 0, "justify": 1, "walk-through": 2, "recommend": 3}

# The history: which number, what to call it, its unit, and which end is better.
_HISTORY: tuple[tuple[str, str, str, str | None, str | None], ...] = (
    ("speech_rate_wpm", "speech rate", "wpm", None, None),
    ("pause_ratio", "time spent paused", "ratio", None, None),
    ("fillers_per_100_words", "fillers", "per 100 words", "lower", None),
    (
        "repeats_per_100_words",
        "words said twice",
        "per 100 words",
        "lower",
        structure.REPEAT,
    ),
    ("words_per_sentence", "words per sentence", "words", None, structure.SENTENCES),
    ("signposts", "signposts", "per answer", None, None),
)

# Rates over this few words are arithmetic on a handful of events, and are left out.
_RATES = frozenset({"fillers_per_100_words", "repeats_per_100_words"})


class NotFound(Exception):
    """No such prompt or answer, or not this user's."""


def count(transcription: Transcription) -> tuple[dict, dict]:
    """How an answer was said and how it was built. CPU work: call it off the event loop."""
    words = [word.model_dump() for word in transcription.words]
    return (
        fluency.analyse(words).as_columns(),
        structure.analyse(transcription.text).as_dict(),
    )


async def prompt_by_slug(
    db: AsyncSession, slug: str, *, active_only: bool = True
) -> AnswerPrompt:
    query = select(AnswerPrompt).where(AnswerPrompt.slug == slug)
    if active_only:
        query = query.where(AnswerPrompt.is_active.is_(True))
    prompt = await db.scalar(query)
    if prompt is None:
        raise NotFound(slug)
    return prompt


async def owned_answer(db: AsyncSession, user: User, answer_id: int) -> Answer:
    answer = await db.scalar(
        select(Answer).where(Answer.id == answer_id, Answer.user_id == user.id)
    )
    if answer is None:
        raise NotFound(answer_id)
    return answer


# ── Wire shapes ─────────────────────────────────────────────────────────────


def to_out(answer: Answer, prompt: AnswerPrompt) -> AnswerOut:
    return AnswerOut(
        id=answer.id,
        prompt=PromptOut.model_validate(prompt),
        created_at=answer.created_at,
        again_of=answer.again_of,
        transcript=answer.transcript,
        asr_confidence=answer.asr_confidence,
        delivery=delivery_of(answer.delivery, answer.duration_ms),
        structure=structure_of(answer.structure),
        feedback=feedback_of(answer.feedback),
    )


def delivery_of(raw: dict, duration_ms: int | None) -> Delivery:
    words = raw.get("word_count") or 0
    fillers = raw.get("filler_count") or 0
    return Delivery(
        words=words,
        duration_ms=duration_ms,
        speech_rate_wpm=raw.get("speech_rate_wpm"),
        articulation_rate=raw.get("articulation_rate"),
        pause_ratio=raw.get("pause_ratio"),
        mean_length_run=raw.get("mean_length_run"),
        fillers=fillers,
        fillers_per_100_words=round(fillers * 100 / words, 1) if words else None,
    )


def structure_of(raw: dict) -> StructureOut:
    shown = structure.SHOWN
    return StructureOut(
        words=raw.get("words", 0),
        sentences=raw.get("sentences") if structure.SENTENCES in shown else None,
        words_per_sentence=(
            raw.get("words_per_sentence") if structure.SENTENCES in shown else None
        ),
        longest_sentence=(
            raw.get("longest_sentence") if structure.SENTENCES in shown else None
        ),
        signposts={
            kind: number
            for kind, number in (raw.get("signposts") or {}).items()
            if kind in shown
        },
        repeats=raw.get("repeats") if structure.REPEAT in shown else None,
        found=[
            Counted(**item) for item in raw.get("found", []) if item["kind"] in shown
        ],
        shown=sorted(shown),
        caveat=STRUCTURE_CAVEAT,
    )


def feedback_of(raw: dict | None) -> Feedback | None:
    if raw is None:
        return None
    return Feedback(
        status=raw["status"],
        model=raw.get("model"),
        lead=raw.get("lead"),
        gaps=raw.get("gaps") or [],
        rewrite=raw.get("rewrite"),
        rewrite_sentences=raw.get("rewrite_sentences"),
        invented=raw.get("invented") or [],
        detail=raw.get("detail"),
        caveat=FEEDBACK_CAVEAT,
    )


# ── The page ────────────────────────────────────────────────────────────────


async def page(db: AsyncSession, user: User, slug: str | None) -> AnswersOut:
    """Every prompt, this user's answers — to one prompt or the latest — and the history.

    Raises `NotFound` for a slug that names no prompt.
    """
    prompts = sorted(
        (await db.scalars(select(AnswerPrompt))).all(),
        key=lambda p: (_CATEGORY_ORDER.get(p.category, 9), p.cefr_band, p.title),
    )
    tallies = {
        prompt_id: (number, last)
        for prompt_id, number, last in (
            await db.execute(
                select(Answer.prompt_id, func.count(), func.max(Answer.created_at))
                .where(Answer.user_id == user.id)
                .group_by(Answer.prompt_id)
            )
        ).all()
    }
    by_id = {prompt.id: prompt for prompt in prompts}

    selected = None
    query = (
        select(Answer)
        .where(Answer.user_id == user.id)
        .order_by(Answer.created_at.desc(), Answer.id.desc())
    )
    if slug is not None:
        selected = next((p for p in prompts if p.slug == slug), None)
        if selected is None:
            raise NotFound(slug)
        query = query.where(Answer.prompt_id == selected.id).limit(ANSWERS_PER_PROMPT)
    else:
        query = query.limit(3)
    listed = (await db.scalars(query)).all()

    recent = (
        await db.scalars(
            select(Answer)
            .where(Answer.user_id == user.id)
            .order_by(Answer.created_at.desc(), Answer.id.desc())
            .limit(ANSWER_HISTORY_LIMIT)
        )
    ).all()

    return AnswersOut(
        prompts=[
            PromptSummary(
                **PromptOut.model_validate(prompt).model_dump(),
                answers=tallies.get(prompt.id, (0, None))[0],
                last_answered_at=tallies.get(prompt.id, (0, None))[1],
            )
            for prompt in prompts
            if prompt.is_active or prompt.id in tallies
        ],
        prompt=PromptOut.model_validate(selected) if selected else None,
        answers=[to_out(answer, by_id[answer.prompt_id]) for answer in listed],
        answered=sum(number for number, _ in tallies.values()),
        history=history(list(reversed(recent))),
        caveat=HISTORY_CAVEAT,
    )


def history(answers: list[Answer]) -> list[Series]:
    """One series per measure, one point per answer, oldest first."""
    series = []
    for key, label, unit, better, needs in _HISTORY:
        if needs is not None and needs not in structure.SHOWN:
            continue
        points = [_point(answer, key) for answer in answers]
        measured = [point for point in points if point.value is not None]
        if measured:
            gate = Gate(shown=True, have=len(measured), need=1)
        elif answers:
            gate = Gate(
                shown=False,
                reason=f"No answer yet has {PROGRESS_MIN_WORDS} words in it.",
                have=max((point.samples for point in points), default=0),
                need=PROGRESS_MIN_WORDS,
            )
        else:
            gate = Gate(shown=False, reason="No answers yet.", have=0, need=1)

        change = direction = None
        if better and len(measured) >= PROGRESS_MIN_POINTS:
            change = round(measured[-1].value - measured[0].value, 3)
            if change == 0:
                direction = "flat"
            else:
                improving = (change > 0) == (better == "higher")
                direction = "improving" if improving else "slipping"
        series.append(
            Series(
                metric=key,
                label=label,
                unit=unit,
                better=better,
                points=points,
                gate=gate,
                change=change,
                direction=direction,
            )
        )
    return series


def _point(answer: Answer, key: str) -> Point:
    delivery = answer.delivery or {}
    built = answer.structure or {}
    words = delivery.get("word_count") or 0
    day = answer.created_at.date()
    if key in _RATES and words < PROGRESS_MIN_WORDS:
        return Point(
            start=day,
            samples=words,
            withheld=f"fewer than {PROGRESS_MIN_WORDS} words",
        )
    if key == "fillers_per_100_words":
        value = round((delivery.get("filler_count") or 0) * 100 / words, 2)
    elif key == "repeats_per_100_words":
        value = round((built.get("repeats") or 0) * 100 / words, 2)
    elif key == "signposts":
        value = float(sum((built.get("signposts") or {}).values()))
    elif key == "words_per_sentence":
        value = built.get("words_per_sentence")
    else:
        value = delivery.get(key)
    return Point(
        start=day,
        value=value,
        samples=words,
        withheld=None if value is not None else "not measured in this answer",
    )
