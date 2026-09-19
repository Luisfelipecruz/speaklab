"""Rehearsing a script: saving one, taking it apart, and what a take is worth.

**The comparison is against the learner's own words.** A reading is scored against a
passage this project wrote and every speaker reads; a take is scored against a script its
speaker typed an hour ago. That is why none of it reaches the progress snapshots, and why
the alignment is stored rather than recomputed: what matters on the page is what was
heard on the day, against the text as it stood.

**Scorability is decided when the script is saved, not when a take arrives.** A word the
converter cannot turn into phones costs the whole section its sounds, and the only person
who can fix it is the one who wrote it — before they have recorded anything. When the
pronunciation service is not running the question cannot be asked, so the sections are
saved as scorable and the page says the check did not happen. Guessing in either
direction would be worse: a section wrongly marked unscorable is never scored again, and
one wrongly marked scorable fails at every take with no reason a reader can act on.

**What to rehearse next is four counts and nothing else.** Each names its own
measurement — how many words, how many takes, how many instances — because a suggestion
that cannot show its working is advice, and advice is the one thing this product does not
give.
"""

from __future__ import annotations

import math

from sqlalchemy import distinct, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from config import (
    ASR_CONFIDENCE_FLOOR,
    PROGRESS_MIN_PHONE_SAMPLES,
    REHEARSAL_PACE_TOLERANCE,
    REHEARSAL_SCRIPT_MAX_WORDS,
    REHEARSAL_SECTION_MAX_WORDS,
    REHEARSAL_SECTION_MIN_WORDS,
)
from db_models import (
    Presentation,
    PresentationSection,
    Rehearsal,
    RehearsalPhone,
    User,
)
from models.answer import Delivery
from models.attempt import PhonemeScoreOut, PronSummary
from models.audio import Transcription
from models.presentation import (
    AlignedWord,
    Fidelity,
    NextUp,
    PresentationCreate,
    PresentationOut,
    PresentationPage,
    PresentationSummary,
    SectionOut,
    SplitPreview,
    TakeOut,
    TakeSummary,
)
from services import audio as audio_service
from services import fluency, sections, structure
from services.answers import delivery_of
from services.pron_client import PronError, PronUnavailable
from services.pron_client import phonemize as pron_phonemize
from services.wer import WerResult, align, normalise

# The confidence below which a heard word is marked as one the recogniser was unsure of.
# The same floor the drill and the error analysis use: a word the recogniser doubted is
# the likeliest place for a difference that is the microphone's rather than the speaker's.
_UNSURE_BELOW = math.log(ASR_CONFIDENCE_FLOOR)

# What `unsure_words` says when the recogniser's word list could not be lined up with the
# compared text — a word carrying punctuation, or one split in two. Not zero, because
# "none were uncertain" and "this could not be checked" are different answers.
UNSURE_UNKNOWN = -1

# A take is worth rehearsing again on fidelity at this rate or above: roughly one word in
# ten of the section not heard as written.
_FIDELITY_WORTH_SAYING = 0.10

# Fillers counted across a presentation before the commonest one is worth naming. Two
# could be one nervous take.
_FILLERS_WORTH_SAYING = 3


class NotFound(Exception):
    """No such presentation, section or take, or not this user's."""


class Invalid(ValueError):
    """The script or the split cannot be saved, and the message says why."""


# ── Saving a script ─────────────────────────────────────────────────────────


async def preview(script: str) -> SplitPreview:
    """The split this script would get, and the words in it that cannot be scored."""
    _refuse_a_script_that_is_too_long(script)
    pieces = sections.split_script(
        script, REHEARSAL_SECTION_MAX_WORDS, REHEARSAL_SECTION_MIN_WORDS
    )
    unscorable, reachable = await _unscorable_per_section(pieces)
    return SplitPreview(
        sections=pieces,
        word_counts=[sections.word_count(piece) for piece in pieces],
        unscorable=unscorable,
        pron="ok" if reachable else "unavailable",
    )


async def create(
    db: AsyncSession, user: User, payload: PresentationCreate
) -> Presentation:
    """Save a script and its sections. Raises `Invalid` with a message a writer can act on."""
    _refuse_a_script_that_is_too_long(payload.script)

    if payload.sections is None:
        pieces = sections.split_script(
            payload.script, REHEARSAL_SECTION_MAX_WORDS, REHEARSAL_SECTION_MIN_WORDS
        )
    else:
        pieces = [" ".join(piece.split()) for piece in payload.sections]
        _refuse_a_split_that_is_not_the_script(payload.script, pieces)

    if not pieces:
        raise Invalid("There is nothing to rehearse in that script.")

    targets = payload.target_seconds or []
    unscorable, _ = await _unscorable_per_section(pieces)

    presentation = Presentation(
        user_id=user.id,
        title=payload.title.strip(),
        script=payload.script,
        word_count=sections.word_count(payload.script),
    )
    presentation.sections = [
        PresentationSection(
            idx=idx,
            body=body,
            word_count=sections.word_count(body),
            target_seconds=targets[idx] if idx < len(targets) else None,
            scorable=not unscorable[idx],
            unscorable_words=unscorable[idx],
        )
        for idx, body in enumerate(pieces)
    ]

    db.add(presentation)
    await db.commit()
    await db.refresh(presentation, ["sections"])
    return presentation


def _refuse_a_script_that_is_too_long(script: str) -> None:
    counted = sections.word_count(script)
    if counted > REHEARSAL_SCRIPT_MAX_WORDS:
        raise Invalid(
            f"That script is {counted} words; the limit is "
            f"{REHEARSAL_SCRIPT_MAX_WORDS}. Rehearse it in more than one piece."
        )


def _refuse_a_split_that_is_not_the_script(script: str, pieces: list[str]) -> None:
    """The sections must be the script, in order, or they are a different talk.

    Checked word for word rather than by length: a boundary moved is fine, a sentence
    edited in the boundary editor is a script whose sections say something the stored
    text does not, and every count afterwards would be against the wrong words.
    """
    if " ".join(pieces).split() != script.split():
        raise Invalid(
            "Those sections do not add up to the script. Move the boundaries, but "
            "change the words in the script itself."
        )
    for piece in pieces:
        if not piece.strip():
            raise Invalid("A section cannot be empty.")
        if sections.word_count(
            piece
        ) > REHEARSAL_SECTION_MAX_WORDS and sections.splittable(piece):
            raise Invalid(
                f"A section of {sections.word_count(piece)} words is longer than the "
                f"{REHEARSAL_SECTION_MAX_WORDS} a section can be scored in one go. "
                "Split it at a sentence end."
            )


async def _unscorable_per_section(
    pieces: list[str],
) -> tuple[list[list[str]], bool]:
    """Which words of each section cannot be turned into phones, and whether it was asked.

    One call per section rather than one for the whole script: the answer is stored per
    section, and a section is what a reader sees the words named under.
    """
    unscorable: list[list[str]] = []
    for piece in pieces:
        try:
            answer = await pron_phonemize(piece)
        except PronUnavailable:
            return [[] for _ in pieces], False
        except PronError:
            # Answering with something unusable is the same as not answering, for this
            # question: the section is saved scorable and a take will say what happened.
            return [[] for _ in pieces], False
        unscorable.append(list(answer.unscorable))
    return unscorable, True


# ── Reading one back ────────────────────────────────────────────────────────


async def owned(db: AsyncSession, user: User, presentation_id: int) -> Presentation:
    """This user's presentation, or `NotFound`. Never 403: it is not theirs to know about."""
    presentation = await db.scalar(
        select(Presentation)
        .where(
            Presentation.id == presentation_id,
            Presentation.user_id == user.id,
        )
        .options(selectinload(Presentation.sections))
    )
    if presentation is None:
        raise NotFound(presentation_id)
    return presentation


async def section_at(
    db: AsyncSession, user: User, presentation_id: int, idx: int
) -> PresentationSection:
    presentation = await owned(db, user, presentation_id)
    for section in presentation.sections:
        if section.idx == idx:
            return section
    raise NotFound(idx)


async def owned_take(db: AsyncSession, user: User, take_id: int) -> Rehearsal:
    take = await db.scalar(
        select(Rehearsal).where(Rehearsal.id == take_id, Rehearsal.user_id == user.id)
    )
    if take is None:
        raise NotFound(take_id)
    return take


async def listing(
    db: AsyncSession, user: User, limit: int, offset: int
) -> tuple[list[PresentationSummary], int]:
    """The list page: one row per script, with its section and take counts."""
    total = await db.scalar(
        select(func.count())
        .select_from(Presentation)
        .where(Presentation.user_id == user.id)
    )
    rows = (
        await db.scalars(
            select(Presentation)
            .where(Presentation.user_id == user.id)
            .order_by(Presentation.updated_at.desc(), Presentation.id.desc())
            .limit(limit)
            .offset(offset)
            .options(selectinload(Presentation.sections))
        )
    ).all()

    takes = await _takes_per_section(db, [s.id for row in rows for s in row.sections])
    return [
        PresentationSummary(
            id=row.id,
            title=row.title,
            word_count=row.word_count,
            sections=len(row.sections),
            takes=sum(takes.get(section.id, (0, None))[0] for section in row.sections),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        for row in rows
    ], (total or 0)


async def page(db: AsyncSession, user: User, presentation_id: int) -> PresentationPage:
    """One script, its sections with how they have gone, and what to rehearse next."""
    presentation = await owned(db, user, presentation_id)
    section_ids = [section.id for section in presentation.sections]

    counted = await _takes_per_section(db, section_ids)
    latest_ids = [latest for _, latest in counted.values() if latest is not None]
    latest = {
        row.section_id: row
        for row in (
            await db.scalars(select(Rehearsal).where(Rehearsal.id.in_(latest_ids)))
        ).all()
    }

    out = PresentationOut(
        id=presentation.id,
        title=presentation.title,
        word_count=presentation.word_count,
        created_at=presentation.created_at,
        updated_at=presentation.updated_at,
        sections=[
            SectionOut(
                id=section.id,
                idx=section.idx,
                body=section.body,
                word_count=section.word_count,
                target_seconds=section.target_seconds,
                scorable=section.scorable,
                unscorable_words=list(section.unscorable_words or []),
                takes=counted.get(section.id, (0, None))[0],
                latest=(
                    summary_of(latest[section.id]) if section.id in latest else None
                ),
            )
            for section in presentation.sections
        ],
    )

    return PresentationPage(
        presentation=out,
        next_up=next_up(
            out.sections,
            await _phone_means(db, section_ids),
            await _fillers_said(db, section_ids),
        ),
    )


async def _takes_per_section(
    db: AsyncSession, section_ids: list[int]
) -> dict[int, tuple[int, int | None]]:
    """How many takes each section has, and the id of its latest. One query."""
    if not section_ids:
        return {}
    rows = await db.execute(
        select(
            Rehearsal.section_id,
            func.count(Rehearsal.id),
            func.max(Rehearsal.id),
        )
        .where(Rehearsal.section_id.in_(section_ids))
        .group_by(Rehearsal.section_id)
    )
    return {section_id: (count, latest) for section_id, count, latest in rows.all()}


async def _phone_means(
    db: AsyncSession, section_ids: list[int]
) -> list[tuple[str, float, int, int]]:
    """Mean GOP per phone over this script's takes: phone, mean, instances, takes.

    Stress is folded away, as it is everywhere else a phone is counted: /AH0/ and /AH1/
    are the same sound said in two places, and separating them would halve every count
    for no reader.
    """
    if not section_ids:
        return []
    phone = func.rtrim(RehearsalPhone.canonical_phone, "012").label("phone")
    rows = await db.execute(
        select(
            phone,
            func.avg(RehearsalPhone.gop),
            func.count(RehearsalPhone.id),
            func.count(distinct(RehearsalPhone.rehearsal_id)),
        )
        .join(Rehearsal, Rehearsal.id == RehearsalPhone.rehearsal_id)
        .where(Rehearsal.section_id.in_(section_ids))
        .group_by(phone)
    )
    return [
        (name, float(mean), int(instances), int(takes))
        for name, mean, instances, takes in rows.all()
    ]


async def _fillers_said(
    db: AsyncSession, section_ids: list[int]
) -> dict[str, tuple[int, int]]:
    """Each filler said in this script's takes: how many times, in how many takes.

    Counted from what was stored with each take rather than from its word list, so that
    opening a page is a few small objects per take instead of every word of every take
    anybody has ever recorded.
    """
    if not section_ids:
        return {}
    rows = (
        await db.scalars(
            select(Rehearsal.delivery).where(Rehearsal.section_id.in_(section_ids))
        )
    ).all()

    counted: dict[str, tuple[int, int]] = {}
    for delivery in rows:
        for word, times in (delivery or {}).get("fillers_said", {}).items():
            said, takes = counted.get(word, (0, 0))
            counted[word] = (said + int(times), takes + 1)
    return counted


# ── What to rehearse next ───────────────────────────────────────────────────


def next_up(
    section_list: list[SectionOut],
    phone_means: list[tuple[str, float, int, int]],
    fillers: dict[str, tuple[int, int]],
) -> list[NextUp]:
    """Four counts, each printing what it counted. Pure, so it is tested on its own."""
    items: list[NextUp] = []

    worst = max(
        (s for s in section_list if s.latest is not None),
        key=lambda s: s.latest.wer,
        default=None,
    )
    if worst is not None and worst.latest.wer >= _FIDELITY_WORTH_SAYING:
        items.append(
            NextUp(
                kind="fidelity",
                title=f"Section {worst.idx + 1}",
                reason=(
                    f"{worst.latest.missed} of {worst.word_count} words missed or "
                    "changed in the last take"
                ),
                measured=round(worst.latest.wer, 3),
                samples=1,
                section_id=worst.id,
            )
        )

    scored = [
        (name, mean, instances, takes)
        for name, mean, instances, takes in phone_means
        if takes >= 2 and instances >= PROGRESS_MIN_PHONE_SAMPLES
    ]
    if scored:
        name, mean, instances, takes = min(scored, key=lambda row: row[1])
        items.append(
            NextUp(
                kind="sound",
                title=f"the /{name}/ sound",
                reason=(
                    f"{instances} instances across {takes} takes, mean score {mean:.1f}"
                ),
                measured=round(mean, 2),
                samples=instances,
            )
        )

    over = [
        s
        for s in section_list
        if s.target_seconds
        and s.latest is not None
        and s.latest.duration_ms is not None
        and s.latest.duration_ms
        > s.target_seconds * 1000 * (1 + REHEARSAL_PACE_TOLERANCE)
    ]
    if over:
        section = max(over, key=lambda s: s.latest.duration_ms)
        items.append(
            NextUp(
                kind="pace",
                title=f"Section {section.idx + 1}",
                reason=(
                    f"{clock(section.latest.duration_ms)} against a target of "
                    f"{clock(section.target_seconds * 1000)}"
                ),
                measured=round(section.latest.duration_ms / 1000, 1),
                samples=1,
                section_id=section.id,
            )
        )

    if fillers:
        word, (said, takes) = max(fillers.items(), key=lambda row: row[1][0])
        if said >= _FILLERS_WORTH_SAYING:
            items.append(
                NextUp(
                    kind="filler",
                    title=f"the word {word!r}",
                    reason=f"{word!r} {said} times in {takes} takes",
                    measured=float(said),
                    samples=takes,
                )
            )

    return items


def clock(duration_ms: int | None) -> str:
    """`m:ss`, the way the answer page writes a length."""
    if duration_ms is None:
        return "—"
    seconds = round(duration_ms / 1000)
    return f"{seconds // 60}:{seconds % 60:02d}"


# ── One take ────────────────────────────────────────────────────────────────


async def take(
    db: AsyncSession,
    user: User,
    section: PresentationSection,
    data: bytes,
    filename: str,
    content_type: str | None,
    store_audio: bool,
) -> Rehearsal:
    """Transcribe a recording, compare it with the section, count it, and store it.

    The recording is kept only when the account keeps recordings. Everything else — the
    transcript, the alignment, the counts — is stored either way, and the phones are
    scored from the bytes this function was handed rather than from a file, which is what
    lets a take be scored on an account that keeps nothing.
    """
    if store_audio:
        asset, _, transcription = await audio_service.ingest_recording(
            db, user, data, filename=filename, content_type=content_type
        )
        asset_id = asset.id
    else:
        transcription = await audio_service.transcribe(
            data, filename=filename, content_type=content_type
        )
        asset_id = None

    if not structure.words_of(transcription.text):
        raise Invalid(
            "Nothing was heard in that recording, so there is nothing to compare."
        )

    alignment = alignment_of(section.body, transcription)
    measured = WerResult(
        substitutions=alignment["substitutions"],
        deletions=alignment["deletions"],
        insertions=alignment["insertions"],
        reference_words=alignment["reference_words"],
    )

    row = Rehearsal(
        section_id=section.id,
        user_id=user.id,
        audio_asset_id=asset_id,
        transcript=transcription.text,
        words=[word.model_dump() for word in transcription.words],
        duration_ms=transcription.source.duration_ms,
        asr_confidence=transcription.confidence,
        asr_model=transcription.model,
        wer=measured.rate,
        alignment=alignment,
        delivery=delivery_columns(transcription),
        pron_status="pending" if section.scorable else "scored",
        pron_detail=None if section.scorable else _unscorable_detail(section),
    )
    db.add(row)

    # Touched by statement rather than through the section's own relationship: the
    # section was loaded on its own, and reaching for its parent here would be a lazy
    # load inside a request that has already decided what it needs.
    await db.execute(
        update(Presentation)
        .where(Presentation.id == section.presentation_id)
        .values(updated_at=func.now())
    )
    await db.commit()
    await db.refresh(row)
    return row


def _unscorable_detail(section: PresentationSection) -> str:
    named = ", ".join(section.unscorable_words or [])
    return (
        "Some words in this section cannot be turned into sounds, so this take was not "
        f"scored sound by sound: {named}. Spelling them the way they are said — "
        '"twenty twenty-six", "A P I" — makes the section scorable.'
    )


def delivery_columns(transcription: Transcription) -> dict:
    """The fluency columns, and which filler words were said, for this take.

    The breakdown is stored because the page counts fillers across every take of a
    script, and re-reading every word of every take to count them again is a page that
    gets slower with practice.
    """
    words = [word.model_dump() for word in transcription.words]
    columns = fluency.analyse(words).as_columns()
    said: dict[str, int] = {}
    for word in words:
        token = (word.get("w") or "").strip(".,!?;:").lower()
        if token in fluency.FILLERS:
            said[token] = said.get(token, 0) + 1
    columns["fillers_said"] = said
    return columns


def alignment_of(reference: str, transcription: Transcription) -> dict:
    """The script against what was heard, word by word, with the counts that rate it.

    The recogniser's own words are attached by position, which holds while normalisation
    keeps one token per heard word. When it does not — a word with punctuation in it, or
    one the recogniser split — nothing is marked uncertain and `unsure_words` says the
    check could not be made, rather than reporting a confident zero.
    """
    ref = normalise(reference)
    hyp = normalise(transcription.text)
    heard = transcription.words
    attachable = len(heard) == len(hyp)

    words: list[dict] = []
    substitutions = deletions = insertions = 0
    unsure_words = 0

    for step in align(ref, hyp):
        unsure = False
        if step.hyp is not None and attachable:
            logprob = heard[step.hyp].logprob
            unsure = logprob is not None and logprob < _UNSURE_BELOW
            unsure_words += 1 if unsure else 0

        if step.ref is not None and step.hyp is not None:
            same = ref[step.ref] == hyp[step.hyp]
            substitutions += 0 if same else 1
            words.append(
                {
                    "kind": "match" if same else "substitution",
                    "expected": ref[step.ref],
                    "heard": hyp[step.hyp],
                    "unsure": unsure,
                }
            )
        elif step.ref is not None:
            deletions += 1
            words.append(
                {
                    "kind": "deletion",
                    "expected": ref[step.ref],
                    "heard": None,
                    "unsure": False,
                }
            )
        else:
            insertions += 1
            words.append(
                {
                    "kind": "insertion",
                    "expected": None,
                    "heard": hyp[step.hyp],
                    "unsure": unsure,
                }
            )

    return {
        "words": words,
        "substitutions": substitutions,
        "deletions": deletions,
        "insertions": insertions,
        "reference_words": len(ref),
        "unsure_words": unsure_words if attachable else UNSURE_UNKNOWN,
    }


# ── Wire shapes ─────────────────────────────────────────────────────────────


def fidelity_of(row: Rehearsal) -> Fidelity:
    raw = row.alignment or {}
    return Fidelity(
        wer=row.wer,
        reference_words=raw.get("reference_words", 0),
        substitutions=raw.get("substitutions", 0),
        deletions=raw.get("deletions", 0),
        insertions=raw.get("insertions", 0),
        words=[AlignedWord(**word) for word in raw.get("words", [])],
        unsure_words=raw.get("unsure_words", 0),
    )


def delivery_of_take(row: Rehearsal) -> Delivery:
    return delivery_of(row.delivery or {}, row.duration_ms)


def summary_of(row: Rehearsal) -> TakeSummary:
    delivery = row.delivery or {}
    summary = row.pron_summary or {}
    alignment = row.alignment or {}
    return TakeSummary(
        id=row.id,
        section_id=row.section_id,
        created_at=row.created_at,
        wer=row.wer,
        missed=alignment.get("substitutions", 0) + alignment.get("deletions", 0),
        duration_ms=row.duration_ms,
        speech_rate_wpm=delivery.get("speech_rate_wpm"),
        fillers=delivery.get("filler_count") or 0,
        pron_status=row.pron_status,
        median_gop=summary.get("median_gop"),
        audio_url=(
            f"/audio/{row.audio_asset_id}" if row.audio_asset_id is not None else None
        ),
    )


def to_out(
    row: Rehearsal,
    section: PresentationSection,
    phones: list[RehearsalPhone] | None = None,
) -> TakeOut:
    pronunciation, detail = _pronunciation_of(row, section)
    return TakeOut(
        **summary_of(row).model_dump(),
        transcript=row.transcript,
        asr_confidence=row.asr_confidence,
        fidelity=fidelity_of(row),
        delivery=delivery_of_take(row),
        pronunciation=pronunciation,
        pronunciation_detail=detail,
        phonemes=[PhonemeScoreOut.model_validate(phone) for phone in (phones or [])],
        summary=(
            PronSummary.model_validate(row.pron_summary) if row.pron_summary else None
        ),
        target_seconds=section.target_seconds,
        pace=pace_of(row.duration_ms, section.target_seconds),
    )


def _pronunciation_of(
    row: Rehearsal, section: PresentationSection
) -> tuple[str, str | None]:
    """What happened to the sounds, told apart from what happened to the take.

    A section with a word that cannot be converted, a scorer that is switched off, and a
    take still being scored are three different things to say, and none of them is a take
    that failed: the words and the timings are stored in every one of them.
    """
    if not section.scorable:
        return "unscorable", row.pron_detail or _unscorable_detail(section)
    if row.pron_status in ("pending", "scoring"):
        return "pending", None
    if row.pron_status == "failed":
        return "unavailable", row.pron_detail
    if row.pron_detail:
        return "unavailable", row.pron_detail
    return "ok", None


def pace_of(duration_ms: int | None, target_seconds: int | None) -> str | None:
    """Under, on, or over the time the learner set. Null when they set none."""
    if duration_ms is None or not target_seconds:
        return None
    target_ms = target_seconds * 1000
    if duration_ms > target_ms * (1 + REHEARSAL_PACE_TOLERANCE):
        return "over"
    if duration_ms < target_ms * (1 - REHEARSAL_PACE_TOLERANCE):
        return "under"
    return "on"
