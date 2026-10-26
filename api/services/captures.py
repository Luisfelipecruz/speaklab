"""Say it in English: a capture made, kept, read back, practised and deleted.

**Made in one request, finished behind it.** `make` hears or reads what the person gave,
decides its language, writes the one version that goes on the clipboard and checks it,
and stores the capture unless saving is paused. Whatever else the Notebook shows — the
other version, the phrases worth keeping — is written by `write_rest` after the reply has
gone, so the panel waits for one model call and not three. A click on the other version
that comes first waits for the one being written, or writes it.

**The connection is let go across the model calls**, as a turn's is: read what is needed,
commit, call the models with no connection held, then write.

**Nothing here is counted by a model.** The language a typed text is in, the keep check,
the box a capture is in and every figure on the Notebook are plain code over stored rows.
The model writes English, proposes mistakes inside the closed taxonomy, and picks phrases
that are only kept when both halves are found where they are quoted from.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from difflib import SequenceMatcher
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from config import (
    ASR_MULTI_URL,
    ERROR_CONFIDENCE_FLOOR,
    PRACTICE_INTERVALS_DAYS,
    SAY_VERSION_WAIT_S,
)
from db_models import Capture, CaptureAttempt, CapturePhrase, User, WrittenError
from models.capture import (
    AttemptOut,
    AttemptSummary,
    CaptureFix,
    CaptureList,
    CaptureOut,
    CaptureSummary,
    LanguageChoice,
    NotebookCounts,
    Phrase,
    SaidOut,
    WordChange,
    WrittenWord,
)
from models.drill import DrillWord
from services import check as checker
from services import english, keep
from services import language as languages
from services.asr_client import transcribe
from services.llm import LlmError, LlmProvider, get_provider
from services.recommend import readable
from services.wer import align, normalise

log = logging.getLogger("speaklab.captures")

# The versions each mode writes, the default first: what goes on the clipboard unless the
# person chose otherwise. `rough` is never asked for; it stands in when the model is down.
OFFERED = {"translate": ("organized", "direct"), "check": ("corrected", "polished")}
WRITTEN_ON_DEMAND = {"direct", "organized", "polished"}

ROUGH_NOTE = (
    "The language model did not answer, so this is the recogniser's own English, rough "
    "and literal. Organized and Direct can be written once it answers."
)
POLISHED_DOWN = (
    "Polished needs the language model, which did not answer, so this is Corrected: your "
    "words with the dictionary's and the grammar rules' fixes."
)
SAID_CAVEAT = (
    "The recogniser was trained on fluent English, and it can hear correct English where "
    "you said something else. So this is what it heard, compared word by word with the "
    "English you used, and nothing on it is a grade. Nothing is stored."
)

# The capitalised words the keep check and the spelling check learn names from: the
# account's most recent captures, which is where its names are.
NAMES_FROM = 200


class NotFound(Exception):
    """No such capture, or not this account's."""


class NothingGiven(Exception):
    """Nothing was heard in the recording, or nothing was typed."""


class ModelDown(Exception):
    """The language model did not answer and there is nothing to stand in for it."""


class NotOffered(Exception):
    """A version this capture cannot have."""


@dataclass
class Given:
    """What the person handed over: a recording or a text, and how."""

    audio: bytes | None = None
    filename: str = "recording"
    content_type: str | None = None
    text: str | None = None
    mode: str = "auto"
    # The versions wanted on the clipboard, at most one per mode: the first one the mode
    # offers is used, and the mode's default when none is.
    versions: tuple[str, ...] = ()
    app: str | None = None
    via: str = "voice"
    save: bool = True


@dataclass
class Made:
    """A capture before or without its row: everything the panel needs."""

    mode: str
    via: str
    source_language: str
    source_text: str
    chosen: str
    versions: dict[str, str]
    language: LanguageChoice
    duration_ms: int | None = None
    app: str | None = None
    asr_model: str | None = None
    llm_model: str | None = None
    fixes: list[checker.Fix] = field(default_factory=list)
    forms: dict[str, int] = field(default_factory=dict)
    check_detail: str | None = None
    rejects: list[dict] = field(default_factory=list)
    dropped: dict[str, list[str]] = field(default_factory=dict)
    kept: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    timings: dict[str, int] = field(default_factory=dict)


def _ms(since: float) -> int:
    return round((time.perf_counter() - since) * 1000)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── What it knows of the account ────────────────────────────────────────────


async def known_names(db: AsyncSession, user_id: int) -> list[str]:
    """Names from the account's recent captures: what they said and the English they used."""
    rows = (
        await db.execute(
            select(Capture.source_text, Capture.organized, Capture.direct)
            .where(Capture.user_id == user_id)
            .order_by(Capture.created_at.desc())
            .limit(NAMES_FROM)
        )
    ).all()
    names: set[str] = set()
    for row in rows:
        for text in row:
            if text:
                names.update(keep.names_in(text))
    return sorted(names)


# ── Making one ──────────────────────────────────────────────────────────────


def _language_codes(mode: str, account: str) -> str:
    """What the recogniser is asked to hear: both languages unless the person said."""
    if account == "en" or mode == "check":
        return "en"
    if mode == "translate":
        return account
    return f"{account},en"


async def _hear(given: Given, account: str, made_timings: dict) -> tuple:
    started = time.perf_counter()
    heard = await transcribe(
        given.audio,
        filename=given.filename,
        content_type=given.content_type,
        language=_language_codes(given.mode, account),
        url=ASR_MULTI_URL,
    )
    made_timings["recognition_ms"] = _ms(started)
    text = heard.text.strip()
    if not re.search(r"\w", text):
        raise NothingGiven("Nothing was heard in that recording.")
    language = heard.language if heard.language in (account, "en") else account
    choice = LanguageChoice(
        language=language,
        by="recogniser" if given.mode == "auto" else "switch",
        scores=heard.language_scores or {},
        confidences=heard.language_confidences or {},
    )
    return text, language, choice, heard


async def make(
    db: AsyncSession, user: User, given: Given, provider: LlmProvider
) -> Made:
    """One capture, from a recording or a text, short of its row.

    Raises `NothingGiven`, `ModelDown`, and the recogniser's own errors for the router to
    answer. Commits the session before the first model call.
    """
    account = user.native_language or "es"
    timings: dict[str, int] = {}
    started = time.perf_counter()

    heard = None
    if given.audio is not None:
        text, language, choice, heard = await _hear(given, account, timings)
    else:
        text = (given.text or "").strip()
        if not re.search(r"\w", text):
            raise NothingGiven("Nothing was typed.")
        if given.mode == "auto":
            decision = languages.decide(text, account)
            language = decision.language
            choice = LanguageChoice(
                language=language, by="words", scores=decision.shares
            )
        else:
            language = "en" if given.mode == "check" else account
            choice = LanguageChoice(language=language, by="switch")

    mode = "check" if language == "en" else "translate"
    offered = OFFERED[mode]
    chosen = next((v for v in given.versions if v in offered), offered[0])
    names = await known_names(db, user.id)
    # Everything the models need is in memory; the connection goes back to the pool.
    await db.commit()

    made = Made(
        mode=mode,
        via="voice" if given.audio is not None else given.via,
        source_language=language,
        source_text=text,
        chosen=chosen,
        versions={},
        language=choice,
        duration_ms=heard.source.duration_ms if heard else None,
        app=(given.app or "").strip()[:120] or None,
        asr_model=heard.model if heard else None,
        timings=timings,
    )

    if mode == "translate":
        await _translate(made, given, provider, names)
    else:
        await _check(made, provider, names)

    for version, written in made.versions.items():
        made.dropped[version] = keep.missing(text, written, names)
    made.kept = _kept(text, names)
    made.timings["total_ms"] = _ms(started)
    return made


async def _translate(
    made: Made, given: Given, provider: LlmProvider, names: list[str]
) -> None:
    generation = time.perf_counter()
    try:
        written = await english.write(
            provider,
            made.chosen,
            made.source_text,
            made.source_language,
            made.app,
            typed=given.audio is None,
        )
    except (LlmError, TimeoutError) as exc:
        if given.audio is None:
            raise ModelDown(
                "The language model is not answering, and a typed text has no rough "
                "English to fall back on. Try again once it answers."
            ) from exc
        log.warning("no model for a translation, using the recogniser's: %s", exc)
        rough_started = time.perf_counter()
        rough = await transcribe(
            given.audio,
            filename=given.filename,
            content_type=given.content_type,
            language=made.source_language,
            task="translate",
            url=ASR_MULTI_URL,
        )
        made.timings["rough_ms"] = _ms(rough_started)
        made.chosen = "rough"
        made.versions["rough"] = rough.text.strip()
        made.notes.append(ROUGH_NOTE)
        return
    made.timings["generation_ms"] = _ms(generation)
    if written.load_ms:
        made.timings["load_ms"] = written.load_ms
    made.llm_model = written.model
    made.versions[made.chosen] = written.text


async def _check(made: Made, provider: LlmProvider, names: list[str]) -> None:
    generation = time.perf_counter()
    checked = await checker.check(provider, made.source_text, names)
    made.timings["check_ms"] = _ms(generation)
    made.versions["corrected"] = checked.corrected
    made.fixes = checked.fixes
    made.forms = checked.forms
    made.check_detail = checked.detail
    made.rejects = checked.rejects
    made.llm_model = checked.model
    if checked.detail:
        made.notes.append(checked.detail)
    if made.chosen != "polished":
        return
    if checked.detail and checked.model is None:
        made.chosen = "corrected"
        made.notes.append(POLISHED_DOWN)
        return
    try:
        written = await english.write(
            provider, "polished", made.source_text, "en", made.app, typed=True
        )
    except (LlmError, TimeoutError):
        made.chosen = "corrected"
        made.notes.append(POLISHED_DOWN)
        return
    made.versions["polished"] = written.text
    made.llm_model = made.llm_model or written.model


def counted(fix) -> bool:
    """Whether a written mistake may reach a rate: the floor a conversation's meet."""
    return fix.confidence >= ERROR_CONFIDENCE_FLOOR


def _interval(box: int) -> timedelta:
    days = PRACTICE_INTERVALS_DAYS[min(box, len(PRACTICE_INTERVALS_DAYS)) - 1]
    return timedelta(days=days)


def next_box(box: int, mistakes: int) -> int:
    """Up a box with no counted mistake, back to the first with any."""
    if mistakes:
        return 1
    return min(box + 1, len(PRACTICE_INTERVALS_DAYS))


def store(db: AsyncSession, user: User, made: Made) -> Capture:
    """The capture's row, and for a typed or copied check its first attempt.

    A check of English the person typed or copied is writing, so it is kept as the
    capture's first attempt and its mistakes are counted as writing. A check of English
    they said is shown and never counted: speech is measured in conversations.
    """
    row = Capture(
        user_id=user.id,
        mode=made.mode,
        via=made.via,
        source_language=made.source_language,
        source_text=made.source_text,
        duration_ms=made.duration_ms,
        app_name=made.app,
        asr_model=made.asr_model,
        llm_model=made.llm_model,
        chosen=made.chosen,
        fixes=[_fix_record(fix) for fix in made.fixes],
        dropped=made.dropped,
        timings=made.timings,
        box=0,
        **{version: text for version, text in made.versions.items()},
    )
    db.add(row)
    if made.mode == "check" and made.via != "voice":
        mistakes = sum(1 for fix in made.fixes if counted(fix))
        row.box = next_box(0, mistakes)
        row.due_at = _now() + _interval(row.box)
        row.attempts.append(
            CaptureAttempt(
                text=made.source_text,
                word_count=len(languages.words_of(made.source_text)),
                compared_with="corrected",
                forms=made.forms,
                box=row.box,
                detail=made.check_detail,
                rejects=made.rejects or None,
                errors=[_written(fix) for fix in made.fixes],
            )
        )
    return row


def _fix_record(fix: checker.Fix) -> dict:
    return {
        "category": fix.category,
        "subcategory": fix.subcategory,
        "span_start": fix.span_start,
        "span_end": fix.span_end,
        "original": fix.original,
        "correction": fix.correction,
        "explanation": fix.explanation,
        "detector": fix.detector,
        "confidence": fix.confidence,
    }


def _written(fix: checker.Fix) -> WrittenError:
    return WrittenError(**_fix_record(fix))


# ── Behind the reply ────────────────────────────────────────────────────────

# The jobs this process is running, by capture, and the versions they are writing. Held
# so a task cannot be collected mid-await, and so a click on a version can wait for the
# one already being written rather than ask the model twice.
_jobs: dict[int, asyncio.Task] = {}
_writing: dict[tuple[int, str], asyncio.Task] = {}


class Writer:
    """What writes behind the reply, and on demand. The seam the tests replace, as
    `Analyser` is: both paths use its session factory and its provider."""

    def __init__(
        self, session_factory: async_sessionmaker, provider: LlmProvider
    ) -> None:
        self._session_factory = session_factory
        self._provider = provider

    def launch(self, capture_id: int) -> None:
        task = asyncio.create_task(
            write_rest(capture_id, self._session_factory, self._provider)
        )
        _jobs[capture_id] = task

        def forget(done: asyncio.Task) -> None:
            if _jobs.get(capture_id) is done:
                del _jobs[capture_id]

        task.add_done_callback(forget)

    async def version(
        self, db: AsyncSession, capture: Capture, version: str
    ) -> Capture:
        return await write_version(
            db, capture, version, self._session_factory, self._provider
        )


def get_writer() -> Writer:
    """FastAPI dependency. Bound to the application's own session factory."""
    from database import async_session

    return Writer(async_session, get_provider())


def _owed(capture: Capture) -> list[str]:
    """The versions a capture is still owed, in the order they are written."""
    offered = OFFERED[capture.mode]
    return [
        version
        for version in offered
        if version in WRITTEN_ON_DEMAND and getattr(capture, version) is None
    ]


async def _write_version(
    capture_id: int,
    version: str,
    snapshot: dict,
    session_factory: async_sessionmaker,
    provider: LlmProvider,
) -> str | None:
    """One version written and stored, or None when the model did not answer."""
    try:
        written = await english.write(
            provider,
            version,
            snapshot["source_text"],
            snapshot["source_language"] if version != "polished" else "en",
            snapshot["app"],
            typed=snapshot["via"] != "voice",
        )
    except (LlmError, TimeoutError) as exc:
        log.info("capture %s: %s not written: %s", capture_id, version, exc)
        return None
    async with session_factory() as db:
        row = await db.get(Capture, capture_id)
        if row is None:
            return None
        if getattr(row, version) is None:
            setattr(row, version, written.text)
            dropped = dict(row.dropped or {})
            dropped[version] = keep.missing(
                row.source_text, written.text, snapshot["names"]
            )
            row.dropped = dropped
            row.llm_model = row.llm_model or written.model
            await db.commit()
        return getattr(row, version)


def _start_version(
    capture_id: int,
    version: str,
    snapshot: dict,
    session_factory: async_sessionmaker,
    provider: LlmProvider,
) -> asyncio.Task:
    key = (capture_id, version)
    running = _writing.get(key)
    if running is not None and not running.done():
        return running
    task = asyncio.create_task(
        _write_version(capture_id, version, snapshot, session_factory, provider)
    )
    _writing[key] = task

    def forget(done: asyncio.Task) -> None:
        if _writing.get(key) is done:
            del _writing[key]

    task.add_done_callback(forget)
    return task


async def _snapshot(db: AsyncSession, capture: Capture) -> dict:
    return {
        "source_text": capture.source_text,
        "source_language": capture.source_language,
        "app": capture.app_name,
        "via": capture.via,
        "names": await known_names(db, capture.user_id),
    }


async def write_rest(
    capture_id: int, session_factory: async_sessionmaker, provider: LlmProvider
) -> None:
    """The versions the capture is owed, then its phrases. Never raises: what the model
    does not write now is written when the person asks for it."""
    try:
        async with session_factory() as db:
            capture = await db.get(Capture, capture_id)
            if capture is None:
                return
            owed = _owed(capture)
            snapshot = await _snapshot(db, capture)
            mode = capture.mode
        for version in owed:
            await _start_version(
                capture_id, version, snapshot, session_factory, provider
            )
        if mode == "translate":
            await _write_phrases(capture_id, session_factory, provider)
    except (
        Exception
    ):  # noqa: BLE001 — nobody awaits this; a failure is logged, not lost
        log.exception("writing the rest of capture %s failed", capture_id)


async def _write_phrases(
    capture_id: int, session_factory: async_sessionmaker, provider: LlmProvider
) -> None:
    async with session_factory() as db:
        capture = await db.get(Capture, capture_id)
        if capture is None:
            return
        english_text = getattr(capture, capture.chosen) or ""
        source = capture.source_text
        has = await db.scalar(
            select(func.count(CapturePhrase.id)).where(
                CapturePhrase.capture_id == capture_id
            )
        )
    if has or not english_text or capture.chosen == "rough":
        return
    pairs = await english.phrases(provider, source, english_text)
    if not pairs:
        return
    async with session_factory() as db:
        if await db.get(Capture, capture_id) is None:
            return
        db.add_all(
            CapturePhrase(capture_id=capture_id, source=said, english=meant)
            for said, meant in pairs
        )
        await db.commit()


async def write_version(
    db: AsyncSession,
    capture: Capture,
    version: str,
    session_factory: async_sessionmaker,
    provider: LlmProvider,
) -> Capture:
    """A version now: the stored one, the one being written, or one written for this."""
    if version not in OFFERED[capture.mode] or version not in WRITTEN_ON_DEMAND:
        if getattr(capture, version, None) is None:
            raise NotOffered(version)
        return capture
    if getattr(capture, version) is not None:
        return capture
    snapshot = await _snapshot(db, capture)
    await db.commit()
    task = _start_version(capture.id, version, snapshot, session_factory, provider)
    try:
        written = await asyncio.wait_for(
            asyncio.shield(task), timeout=SAY_VERSION_WAIT_S
        )
    except TimeoutError:
        written = None
    if written is None:
        raise ModelDown(
            f"{version.capitalize()} needs the language model, which is not answering."
        )
    await db.refresh(capture)
    return capture


# ── Reading them back ───────────────────────────────────────────────────────


def state_of(capture: Capture, now: datetime | None = None) -> str:
    """Never written yourself, due again, or practised and not due yet."""
    if capture.box == 0:
        return "to_practise"
    if capture.due_at is not None and capture.due_at <= (now or _now()):
        return "due"
    return "practised"


def _fix_out(record: dict, counts: bool) -> CaptureFix:
    return CaptureFix(
        category=record["category"],
        label=readable(record["category"]),
        subcategory=record.get("subcategory"),
        span_start=record.get("span_start"),
        span_end=record.get("span_end"),
        original=record["original"],
        correction=record["correction"],
        explanation=record.get("explanation"),
        detector=record["detector"],
        counted=counts and record["confidence"] >= ERROR_CONFIDENCE_FLOOR,
    )


def _versions(row) -> dict[str, str | None]:
    return {
        version: getattr(row, version)
        for version in (*OFFERED[row.mode], "rough")
        if version != "rough" or getattr(row, "rough", None)
    }


def _kept(text: str, names: list[str]) -> list[str]:
    """What a version of `text` must keep, in one list, without repeats."""
    items = keep.kept_items(text, names)
    found = [*items["names"], *items["numbers"], *items["links"], *items["emails"]]
    found += items["handles"]
    return list(dict.fromkeys(found))


def made_out(made: Made) -> CaptureOut:
    """The answer for a capture that was not saved: nothing about it was kept, so nothing
    in it is counted."""
    return CaptureOut(
        id=None,
        saved=False,
        created_at=_now(),
        mode=made.mode,
        via=made.via,
        source_language=made.source_language,
        source_text=made.source_text,
        duration_ms=made.duration_ms,
        app=made.app,
        chosen=made.chosen,
        text=made.versions[made.chosen],
        versions={v: made.versions.get(v) for v in OFFERED[made.mode]}
        | ({"rough": made.versions["rough"]} if "rough" in made.versions else {}),
        dropped=made.dropped,
        kept=made.kept,
        fixes=[_fix_out(_fix_record(fix), False) for fix in made.fixes],
        changes=_changes(
            made.mode,
            made.source_text,
            {v: made.versions.get(v) for v in OFFERED[made.mode]},
        ),
        notes=made.notes,
        language=made.language,
        asr_model=made.asr_model,
        llm_model=made.llm_model,
        timings=made.timings,
    )


async def _elsewhere(
    db: AsyncSession, capture: Capture, phrases: list
) -> dict[str, int]:
    """For each phrase's English, how many of the account's other captures use it."""
    if not phrases:
        return {}
    rows = (
        await db.execute(
            select(
                Capture.direct,
                Capture.organized,
                Capture.corrected,
                Capture.polished,
                Capture.rough,
            ).where(Capture.user_id == capture.user_id, Capture.id != capture.id)
        )
    ).all()
    texts = [" ".join(part.casefold() for part in row if part) for row in rows]
    counts = {}
    for phrase in phrases:
        pattern = re.compile(
            r"(?<!\w)"
            + r"\s+".join(map(re.escape, phrase.english.casefold().split()))
            + r"(?!\w)"
        )
        counts[phrase.english] = sum(1 for text in texts if pattern.search(text))
    return counts


def word_changes(said: str, version: str) -> list[WordChange]:
    """`version` beside what was said, word by word: aligned as the recogniser's word error
    rate aligns, on the words without case or punctuation, and shown as each was written.

    Where a change sits beside a word added or dropped, either pairing costs the same, and
    the one that pairs the likelier words is kept: *tomorow* with *tomorrow*, not with the
    *morning* added after it."""
    yours, theirs = said.split(), version.split()
    steps = align(
        [" ".join(normalise(word)) for word in yours],
        [" ".join(normalise(word)) for word in theirs],
    )
    pairs = [
        [
            yours[step.ref] if step.ref is not None else None,
            theirs[step.hyp] if step.hyp is not None else None,
        ]
        for step in steps
    ]
    for i in range(len(pairs) - 1):
        a, b = pairs[i], pairs[i + 1]
        if None not in a and b[0] is None:  # a change, then a word added
            if _alike(a[0], b[1]) > _alike(a[0], a[1]):
                pairs[i], pairs[i + 1] = [None, a[1]], [a[0], b[1]]
        elif a[0] is None and None not in b:  # a word added, then a change
            if _alike(b[0], a[1]) > _alike(b[0], b[1]):
                pairs[i], pairs[i + 1] = [b[0], a[1]], [None, b[1]]
        elif None not in a and b[1] is None:  # a change, then a word dropped
            if _alike(b[0], a[1]) > _alike(a[0], a[1]):
                pairs[i], pairs[i + 1] = [a[0], None], [b[0], a[1]]
        elif a[1] is None and None not in b:  # a word dropped, then a change
            if _alike(a[0], b[1]) > _alike(b[0], b[1]):
                pairs[i], pairs[i + 1] = [a[0], b[1]], [b[0], None]
    return [WordChange(said=s, version=v) for s, v in pairs]


def _alike(one: str, other: str) -> float:
    return SequenceMatcher(
        None, " ".join(normalise(one)), " ".join(normalise(other))
    ).ratio()


def _changes(
    mode: str, said: str, versions: dict[str, str | None]
) -> dict[str, list[WordChange]]:
    if mode != "check":
        return {}
    return {name: word_changes(said, text) for name, text in versions.items() if text}


async def capture_out(
    db: AsyncSession,
    capture: Capture,
    notes: list[str] | None = None,
    language: LanguageChoice | None = None,
) -> CaptureOut:
    """One stored capture, with its phrases counted and its attempts summarised. The
    notes and the language decision are the panel's, from the request that made it."""
    attempts = list(
        (
            await db.scalars(
                select(CaptureAttempt)
                .where(CaptureAttempt.capture_id == capture.id)
                .order_by(CaptureAttempt.created_at)
            )
        ).all()
    )
    mistakes = {}
    if attempts:
        mistakes = dict(
            (
                await db.execute(
                    select(WrittenError.attempt_id, func.count(WrittenError.id))
                    .where(
                        WrittenError.attempt_id.in_([a.id for a in attempts]),
                        WrittenError.confidence >= ERROR_CONFIDENCE_FLOOR,
                    )
                    .group_by(WrittenError.attempt_id)
                )
            ).all()
        )
    phrases = list(
        (
            await db.scalars(
                select(CapturePhrase)
                .where(CapturePhrase.capture_id == capture.id)
                .order_by(CapturePhrase.id)
            )
        ).all()
    )
    elsewhere = await _elsewhere(db, capture, phrases)
    names = await known_names(db, capture.user_id)
    typed_check = capture.mode == "check" and capture.via != "voice"
    return CaptureOut(
        id=capture.id,
        created_at=capture.created_at,
        mode=capture.mode,
        via=capture.via,
        source_language=capture.source_language,
        source_text=capture.source_text,
        duration_ms=capture.duration_ms,
        app=capture.app_name,
        chosen=capture.chosen,
        text=getattr(capture, capture.chosen) or "",
        versions=_versions(capture),
        # Checked again with every name the account has used since, so it agrees with
        # `kept`; the row keeps what the panel named when the capture was made.
        dropped={
            version: keep.missing(capture.source_text, text, names)
            for version, text in _versions(capture).items()
            if text
        },
        kept=_kept(capture.source_text, names),
        fixes=[_fix_out(record, typed_check) for record in capture.fixes or []],
        changes=_changes(capture.mode, capture.source_text, _versions(capture)),
        phrases=[
            Phrase(
                source=p.source,
                english=p.english,
                elsewhere=elsewhere.get(p.english, 0),
            )
            for p in phrases
        ],
        notes=notes or [],
        language=language,
        state=state_of(capture),
        practised=len(attempts),
        box=capture.box,
        due_at=capture.due_at,
        attempts=[
            AttemptSummary(
                id=a.id,
                created_at=a.created_at,
                word_count=a.word_count,
                counted=int(mistakes.get(a.id, 0)),
                box=a.box,
            )
            for a in attempts
        ],
        asr_model=capture.asr_model,
        llm_model=capture.llm_model,
        timings=capture.timings or {},
    )


async def owned(db: AsyncSession, user: User, capture_id: int) -> Capture:
    capture = await db.scalar(
        select(Capture).where(Capture.id == capture_id, Capture.user_id == user.id)
    )
    if capture is None:
        raise NotFound(capture_id)
    return capture


def _filtered(
    query,
    user: User,
    state: str | None,
    app: str | None,
    q: str | None,
    mode: str | None = None,
):
    now = _now()
    query = query.where(Capture.user_id == user.id)
    if mode:
        query = query.where(Capture.mode == mode)
    if state == "to_practise":
        query = query.where(Capture.box == 0)
    elif state == "due":
        query = query.where(Capture.box > 0, Capture.due_at <= now)
    elif state == "practised":
        query = query.where(Capture.box > 0, Capture.due_at > now)
    if app:
        query = query.where(Capture.app_name == app)
    if q:
        like = (
            "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        )
        query = query.where(
            or_(
                *(
                    column.ilike(like, escape="\\")
                    for column in (
                        Capture.source_text,
                        Capture.direct,
                        Capture.organized,
                        Capture.corrected,
                        Capture.polished,
                    )
                )
            )
        )
    return query


async def listing(
    db: AsyncSession,
    user: User,
    state: str | None,
    app: str | None,
    q: str | None,
    limit: int,
    offset: int,
    mode: str | None = None,
) -> CaptureList:
    """The account's captures, newest first, by page, with the Notebook's counts."""
    rows = list(
        (
            await db.scalars(
                _filtered(select(Capture), user, state, app, q, mode)
                .order_by(Capture.created_at.desc(), Capture.id.desc())
                .limit(limit)
                .offset(offset)
            )
        ).all()
    )
    matching = await db.scalar(
        _filtered(select(func.count(Capture.id)), user, state, app, q, mode)
    )
    practised = {}
    if rows:
        practised = dict(
            (
                await db.execute(
                    select(CaptureAttempt.capture_id, func.count(CaptureAttempt.id))
                    .where(CaptureAttempt.capture_id.in_([r.id for r in rows]))
                    .group_by(CaptureAttempt.capture_id)
                )
            ).all()
        )
    apps = list(
        (
            await db.scalars(
                select(Capture.app_name)
                .where(Capture.user_id == user.id, Capture.app_name.is_not(None))
                .group_by(Capture.app_name)
                .order_by(func.count(Capture.id).desc(), Capture.app_name)
            )
        ).all()
    )
    return CaptureList(
        items=[
            CaptureSummary(
                id=row.id,
                created_at=row.created_at,
                mode=row.mode,
                via=row.via,
                app=row.app_name,
                source_text=row.source_text,
                chosen=row.chosen,
                text=getattr(row, row.chosen) or "",
                state=state_of(row),
                practised=int(practised.get(row.id, 0)),
                box=row.box,
                due_at=row.due_at,
                fixes=len(row.fixes or []),
            )
            for row in rows
        ],
        matching=int(matching or 0),
        limit=limit,
        offset=offset,
        counts=await counts(db, user.id),
        apps=apps,
    )


async def counts(db: AsyncSession, user_id: int) -> NotebookCounts:
    """The Notebook's figures: this week's captures and attempts, and what is due."""
    now = _now()
    week = now - timedelta(days=7)
    total = await db.scalar(
        select(func.count(Capture.id)).where(Capture.user_id == user_id)
    )
    this_week = await db.scalar(
        select(func.count(Capture.id)).where(
            Capture.user_id == user_id, Capture.created_at >= week
        )
    )
    attempts = (
        select(CaptureAttempt.id)
        .join(Capture, Capture.id == CaptureAttempt.capture_id)
        .where(Capture.user_id == user_id, CaptureAttempt.created_at >= week)
    )
    practised = await db.scalar(select(func.count()).select_from(attempts.subquery()))
    with_mistakes = await db.scalar(
        select(func.count(func.distinct(WrittenError.attempt_id))).where(
            WrittenError.attempt_id.in_(attempts),
            WrittenError.confidence >= ERROR_CONFIDENCE_FLOOR,
        )
    )
    due = await db.scalar(
        select(func.count(Capture.id)).where(
            Capture.user_id == user_id, Capture.box > 0, Capture.due_at <= now
        )
    )
    to_practise = await db.scalar(
        select(func.count(Capture.id)).where(
            Capture.user_id == user_id, Capture.box == 0
        )
    )
    return NotebookCounts(
        total=int(total or 0),
        this_week=int(this_week or 0),
        practised_this_week=int(practised or 0),
        clean_this_week=int((practised or 0) - (with_mistakes or 0)),
        due=int(due or 0),
        to_practise=int(to_practise or 0),
    )


async def delete_one(db: AsyncSession, capture: Capture) -> None:
    await db.delete(capture)


async def delete_all(db: AsyncSession, user: User) -> int:
    """Every capture of the account; their attempts, mistakes and phrases go with them."""
    result = await db.execute(delete(Capture).where(Capture.user_id == user.id))
    return result.rowcount or 0


# ── Writing it yourself ─────────────────────────────────────────────────────


def _closer(capture: Capture, text: str) -> tuple[str | None, str | None]:
    """The version the attempt is nearest, by words changed, the one copied on a tie."""
    candidates = [
        version
        for version in (capture.chosen, *OFFERED[capture.mode], "rough")
        if getattr(capture, version, None)
    ]
    written = normalise(text)
    best, distance = None, None
    for version in dict.fromkeys(candidates):
        reference = normalise(getattr(capture, version))
        steps = align(reference, written)
        changed = sum(
            1
            for step in steps
            if step.ref is None
            or step.hyp is None
            or reference[step.ref] != written[step.hyp]
        )
        if distance is None or changed < distance:
            best, distance = version, changed
    return best, getattr(capture, best) if best else None


async def attempt(
    db: AsyncSession, user: User, capture: Capture, text: str, provider: LlmProvider
) -> AttemptOut:
    """One attempt at the English, checked like a conversation's, and the box moved."""
    text = text.strip()
    if not re.search(r"\w", text):
        raise NothingGiven("Nothing was written.")
    names = await known_names(db, user.id)
    capture_id = capture.id
    await db.commit()

    checked = await checker.check(provider, text, names)
    mistakes = sum(1 for fix in checked.fixes if counted(fix))
    words = len(languages.words_of(text))

    capture = await owned(db, user, capture_id)
    box_before = capture.box
    capture.box = next_box(capture.box, mistakes)
    capture.due_at = _now() + _interval(capture.box)
    compared_with, compared_text = _closer(capture, text)
    row = CaptureAttempt(
        capture_id=capture.id,
        text=text,
        word_count=words,
        compared_with=compared_with,
        forms=checked.forms,
        box=capture.box,
        detail=checked.detail,
        rejects=checked.rejects or None,
        errors=[_written(fix) for fix in checked.fixes],
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    steps = align(normalise(compared_text or ""), normalise(text))
    reference, written = normalise(compared_text or ""), normalise(text)
    return AttemptOut(
        id=row.id,
        capture_id=capture.id,
        created_at=row.created_at,
        text=text,
        word_count=words,
        errors=[_fix_out(_fix_record(fix), True) for fix in checked.fixes],
        counted=mistakes,
        per_100_words=round(mistakes * 100 / words, 1) if words else None,
        forms=checked.forms,
        compared_with=compared_with,
        compared_text=compared_text,
        words=[
            WrittenWord(
                expected=reference[step.ref] if step.ref is not None else None,
                written=written[step.hyp] if step.hyp is not None else None,
            )
            for step in steps
        ],
        box_before=box_before,
        box=capture.box,
        due_at=capture.due_at,
        detail=checked.detail,
    )


# ── Saying it yourself ──────────────────────────────────────────────────────


def said(capture: Capture, heard_text: str) -> SaidOut:
    """What the recogniser heard, against the English the person used. Nothing stored."""
    version = capture.chosen
    if not getattr(capture, version):
        version = next(v for v, text in _versions(capture).items() if text)
    expected = getattr(capture, version)
    reference, hypothesis = normalise(expected), normalise(heard_text)
    steps = align(reference, hypothesis)
    matched = sum(
        1
        for step in steps
        if step.ref is not None
        and step.hyp is not None
        and reference[step.ref] == hypothesis[step.hyp]
    )
    missed = sum(1 for step in steps if step.hyp is None)
    added = sum(1 for step in steps if step.ref is None)
    return SaidOut(
        heard=heard_text,
        compared_with=version,
        expected=expected,
        words=[
            DrillWord(
                expected=reference[step.ref] if step.ref is not None else None,
                heard=hypothesis[step.hyp] if step.hyp is not None else None,
            )
            for step in steps
        ],
        expected_words=len(reference),
        matched=matched,
        substituted=len(reference) - matched - missed,
        missed=missed,
        added=added,
        caveat=SAID_CAVEAT,
    )
