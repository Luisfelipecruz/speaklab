"""Say it again: one of your own sentences with its correction in it, heard and compared.

**The sentence is the one you said, corrected.** It is cut around the correction the way
the grammar page cuts it, and every correction stored inside it is applied — the one being
practised and any others — because saying it with only one fixed would be practising the
rest. Corrections that overlap are not both applied: the one being practised wins, then
the first by position.

**The comparison is deterministic and asks no model.** The recording is transcribed, the
transcript is aligned word by word against the sentence with the word error rate code the
recogniser is measured with, and each correction gets what was heard where its words
belong: the corrected words, the words as first said, something else, or nothing. The
sentence as a whole gets its counts — words heard as written, heard as something else, not
heard, and heard that are not in it.

**It cannot tell a learner's correct form from the recogniser's.** A recogniser trained on
fluent English hears what fluent English would say, and it can hear a correct form where a
wrong one was spoken. So a correction heard as corrected is what the recogniser heard, and
nothing on the page calls it a pass.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import ASR_CONFIDENCE_FLOOR
from db_models import LanguageError, PracticeSession, Scenario, Turn, User
from models.audio import Transcription
from models.drill import (
    DrillCorrection,
    DrillOut,
    DrillPiece,
    DrillResult,
    DrillVerdict,
    DrillWord,
)
from services.analysis import is_counted
from services.corrections import placed, sentence_bounds
from services.recommend import readable
from services.wer import align, normalise

DRILL_CAVEAT = (
    "The recogniser was trained on fluent English, and it can hear correct English where "
    "you said a mistake. Tested with a clear synthetic voice, it heard 2 or 3 of 89 "
    "mistakes as their correction, and no correct sentence as the mistake; a learner's "
    "voice gives it less to go on. So “heard the way you first said it” is strong "
    "evidence, and “heard as corrected” is what it heard rather than proof you said it. "
    "The correction itself was proposed by rules or a language model and checked by "
    "nobody: if you think it is wrong, skip it — saying it again would practise the "
    "mistake."
)


class Correction(Protocol):
    id: int
    span_start: int | None
    span_end: int | None
    original: str
    correction: str


class NotFound(Exception):
    """No such correction, or not this user's."""


def audible(correction: Correction) -> bool:
    """Whether saying the correction differs from saying what it replaced.

    Compared as the recogniser's words are compared, so a change of capitals or punctuation
    — which a transcript cannot show was spoken — is not something to practise aloud.
    """
    return normalise(correction.original) != normalise(correction.correction)


def applied(
    transcript: str,
    drilled: Correction,
    found: Sequence[Correction],
    opens: int,
    stops: int,
) -> list[Correction]:
    """The corrections to apply inside `[opens, stops)`, in text order.

    The one practised first, then every other placed inside the stretch that overlaps none
    already chosen, by position. One that changes nothing a recording carries is left as
    it was said.
    """
    chosen = [drilled]
    for row in sorted(found, key=lambda r: (r.span_start or 0, r.id)):
        if (
            row.id == drilled.id
            or not audible(row)
            or not placed(transcript, row.span_start, row.span_end, row.original)
        ):
            continue
        if not (opens <= row.span_start and row.span_end <= stops):
            continue
        if any(
            row.span_start < other.span_end and other.span_start < row.span_end
            for other in chosen
        ):
            continue
        chosen.append(row)
    return sorted(chosen, key=lambda r: r.span_start)


def pieces(
    transcript: str, corrections: Sequence[Correction], opens: int, stops: int
) -> list[DrillPiece]:
    """The stretch `[opens, stops)` as it was said and as it is to be said.

    `corrections` are placed, in text order, and do not overlap.
    """
    result: list[DrillPiece] = []
    cursor = opens
    for row in corrections:
        if row.span_start > cursor:
            text = transcript[cursor : row.span_start]
            result.append(DrillPiece(said=text, say=text))
        result.append(
            DrillPiece(
                said=transcript[row.span_start : row.span_end],
                say=row.correction,
                correction_id=row.id,
            )
        )
        cursor = row.span_end
    if stops > cursor:
        text = transcript[cursor:stops]
        result.append(DrillPiece(said=text, say=text))
    return result


# ── The comparison ──────────────────────────────────────────────────────────


def _expected(
    sentence: Sequence[DrillPiece],
) -> tuple[list[str], list[tuple[int, int, int, list[str]]]]:
    """The sentence's words, and where each correction's words sit among them.

    Each correction is `(id, first word, one past the last, the words as first said)`.
    A correction that removes words sits between two words and covers none.
    """
    words: list[str] = []
    regions = []
    for piece in sentence:
        tokens = normalise(piece.say)
        if piece.correction_id is not None:
            regions.append(
                (
                    piece.correction_id,
                    len(words),
                    len(words) + len(tokens),
                    normalise(piece.said),
                )
            )
        words += tokens
    return words, regions


def _heard(transcription: Transcription) -> tuple[list[str], list[float | None]]:
    """The words heard, each with the recogniser's log-probability where it can be matched.

    The recogniser's own word list carries the probabilities, and normalised one word at a
    time it gives the same words as the transcript normalised whole. When it does not, the
    words are the transcript's and none carries a probability — a probability on the wrong
    word would mark a correct one as doubtful.
    """
    words = normalise(transcription.text)
    paired = [
        (token, word.logprob)
        for word in transcription.words
        for token in normalise(word.w)
    ]
    if [token for token, _ in paired] == words:
        return words, [logprob for _, logprob in paired]
    return words, [None] * len(words)


def score(sentence: Sequence[DrillPiece], transcription: Transcription) -> DrillResult:
    """What was heard, against the sentence and each correction in it."""
    ref, regions = _expected(sentence)
    hyp, logprobs = _heard(transcription)
    steps = align(ref, hyp)
    at = {
        step.ref: position
        for position, step in enumerate(steps)
        if step.ref is not None
    }
    cutoff = math.log(ASR_CONFIDENCE_FLOOR)

    def words_in(span) -> list[str]:
        return [hyp[step.hyp] for step in span if step.hyp is not None]

    verdicts = []
    for correction_id, first, last, original in regions:
        expected = ref[first:last]
        # Two readings of "in its place". Tight: from the correction's first word to its
        # last. Wide: everything between the words either side, which is where a word the
        # correction removes is heard when it is said anyway — `I am agree` for `I agree`.
        tight = words_in(steps[at[first] : at[last - 1] + 1]) if last > first else []
        low = at[first - 1] + 1 if first > 0 else 0
        high = at[last] if last < len(ref) else len(steps)
        wide_span = steps[low:high]
        wide = words_in(wide_span)

        if original and original in (tight, wide):
            verdict, shown = "original", original
        elif tight == expected and (expected or not wide):
            verdict, shown = "corrected", tight
        elif not wide:
            verdict, shown = "unheard", []
        else:
            verdict, shown = "other", wide
        verdicts.append(
            DrillVerdict(
                id=correction_id,
                verdict=verdict,
                expected=" ".join(expected),
                heard=" ".join(shown),
                unsure=any(
                    logprobs[step.hyp] is not None and logprobs[step.hyp] < cutoff
                    for step in wide_span
                    if step.hyp is not None
                ),
            )
        )

    matched = sum(
        1
        for step in steps
        if step.ref is not None
        and step.hyp is not None
        and ref[step.ref] == hyp[step.hyp]
    )
    missed = sum(1 for step in steps if step.hyp is None)
    added = sum(1 for step in steps if step.ref is None)
    return DrillResult(
        heard=transcription.text,
        words=[
            DrillWord(
                expected=ref[step.ref] if step.ref is not None else None,
                heard=hyp[step.hyp] if step.hyp is not None else None,
            )
            for step in steps
        ],
        verdicts=verdicts,
        expected_words=len(ref),
        matched=matched,
        substituted=len(ref) - matched - missed,
        missed=missed,
        added=added,
    )


# ── Reading one from the database ───────────────────────────────────────────


async def build(db: AsyncSession, user: User, error_id: int) -> DrillOut:
    """The drill for one of this user's corrections. Raises `NotFound` otherwise."""
    found = (
        await db.execute(
            select(LanguageError, Turn, Scenario.title)
            .join(Turn, Turn.id == LanguageError.turn_id)
            .join(PracticeSession, PracticeSession.id == Turn.session_id)
            .outerjoin(Scenario, Scenario.id == PracticeSession.scenario_id)
            .where(
                LanguageError.id == error_id,
                PracticeSession.user_id == user.id,
                Turn.role == "user",
            )
        )
    ).one_or_none()
    if found is None:
        raise NotFound(error_id)
    drilled, turn, scenario_title = found
    transcript = turn.transcript or ""

    drill = DrillOut(
        id=drilled.id,
        session_id=turn.session_id,
        turn_id=turn.id,
        said_at=turn.created_at,
        scenario_title=scenario_title,
        corrections=[_correction(drilled)],
        caveat=DRILL_CAVEAT,
    )
    if not placed(transcript, drilled.span_start, drilled.span_end, drilled.original):
        drill.unavailable = (
            "The words this correction quotes are not where it says they are in what you "
            "said, so there is no sentence to say again."
        )
    elif not audible(drilled):
        drill.unavailable = (
            "This correction changes only capitals or punctuation, which a recording of "
            "you speaking cannot show."
        )
    else:
        opens, stops, drill.cut_before, drill.cut_after = sentence_bounds(
            transcript, drilled.span_start, drilled.span_end
        )
        neighbours = list(
            (
                await db.scalars(
                    select(LanguageError).where(LanguageError.turn_id == turn.id)
                )
            ).all()
        )
        chosen = applied(transcript, drilled, neighbours, opens, stops)
        drill.corrections = [_correction(row) for row in chosen]
        drill.pieces = pieces(transcript, chosen, opens, stops)

    drill.next_id = await _next(
        db, user, drilled, {row.id for row in drill.corrections}
    )
    return drill


def _correction(row: LanguageError) -> DrillCorrection:
    return DrillCorrection(
        id=row.id,
        category=row.category,
        label=readable(row.category),
        subcategory=row.subcategory,
        original=row.original,
        correction=row.correction,
        explanation=row.explanation,
        detector=row.detector,
        counted=is_counted(row),
        asr_suspect=row.asr_suspect,
    )


async def _next(
    db: AsyncSession, user: User, drilled: LanguageError, done: set[int]
) -> int | None:
    """The next correction of the same kind after this one, newest first, that can be said.

    The grammar page's order, over every analysed turn rather than its window, skipping
    the corrections already in this sentence.
    """
    rows = (
        await db.execute(
            select(LanguageError, Turn.transcript)
            .join(Turn, Turn.id == LanguageError.turn_id)
            .join(PracticeSession, PracticeSession.id == Turn.session_id)
            .where(
                PracticeSession.user_id == user.id,
                Turn.role == "user",
                LanguageError.category == drilled.category,
            )
            .order_by(
                Turn.created_at.desc(),
                LanguageError.turn_id,
                LanguageError.span_start,
                LanguageError.id,
            )
        )
    ).all()
    ids = [row.id for row, _ in rows]
    if drilled.id not in ids:
        return None
    for row, transcript in rows[ids.index(drilled.id) + 1 :]:
        if row.id in done or not audible(row):
            continue
        if placed(transcript or "", row.span_start, row.span_end, row.original):
            return row.id
    return None
