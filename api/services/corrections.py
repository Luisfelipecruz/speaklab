"""A learner's corrections, grouped by kind and by verb form, for the grammar page.

**Read from the rows, not the snapshots.** The progress page draws trends, and trends are
read from materialised snapshots. This page lists sentences, and a snapshot holds no
sentences: it reads the stored corrections for the window and the transcripts of the few
it quotes. The counts are computed the way the snapshots compute them — the same rule for
which corrections count, and the same tally per verb form — so the two pages cannot
disagree about the same speech.

**The form to practise is named only on enough evidence.** A verb form qualifies once it
has come up often enough to be a sample and been corrected often enough that the
corrections are unlikely all to be the detector's mistakes; among those, the one right
least often is named, with its counts and a scenario written to draw it out. Below the
floor nothing is named, and the page says how far the nearest form is from it.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import (
    GRAMMAR_CONTEXT_CHARS,
    GRAMMAR_CORRECTIONS_PER_FORM,
    GRAMMAR_EXAMPLES_PER_CATEGORY,
    GRAMMAR_MIN_FORM_CORRECTIONS,
    PROGRESS_MIN_FORM_CONTEXTS,
)
from db_models import (
    FluencyMetrics,
    GrammarUsage,
    LanguageError,
    PracticeSession,
    Scenario,
    Turn,
    User,
)
from models.grammar import (
    CategoryCorrections,
    CorrectionExample,
    FormCorrection,
    FormPractice,
    GrammarOut,
    GrammarTotals,
    WeakestForm,
)
from models.progress import Gate
from services import forms
from services.analysis import is_counted
from services.recommend import readable
from services.taxonomy import CATEGORY_GLOSS

GRAMMAR_CAVEAT = (
    "Every correction here was proposed by grammar rules — agreement and missing "
    "articles — or by a language model, and none was checked by a person. On this "
    "project's hand-checked set the model pointed at a real mistake half the time (0.50 "
    "precision) and found a third of the mistakes a person marked. Read each sentence and "
    "decide for yourself: a correction you disagree with may be the one that is wrong, and "
    "a form counted as right may hold a mistake nobody flagged."
)


async def build(db: AsyncSession, user: User, days: int) -> GrammarOut:
    """The grammar page for one user, over the last `days` days."""
    until = date.today()
    since = until - timedelta(days=days)
    start = datetime.combine(since, time.min, tzinfo=timezone.utc)

    def in_window(query):
        """This user's analysed turns in the window, joined onto whatever `query` reads."""
        return query.join(PracticeSession, PracticeSession.id == Turn.session_id).where(
            PracticeSession.user_id == user.id,
            Turn.role == "user",
            Turn.analysis_status == "analyzed",
            Turn.created_at >= start,
        )

    turns, sessions = (
        await db.execute(
            in_window(
                select(
                    func.count(Turn.id), func.count(func.distinct(Turn.session_id))
                ).select_from(Turn)
            )
        )
    ).one()
    words = await db.scalar(
        in_window(
            select(func.coalesce(func.sum(FluencyMetrics.word_count), 0))
            .select_from(FluencyMetrics)
            .join(Turn, Turn.id == FluencyMetrics.turn_id)
        )
    )
    used = {
        feature: int(count)
        for feature, count in (
            await db.execute(
                in_window(
                    select(GrammarUsage.feature, func.sum(GrammarUsage.count))
                    .select_from(GrammarUsage)
                    .join(Turn, Turn.id == GrammarUsage.turn_id)
                ).group_by(GrammarUsage.feature)
            )
        ).all()
    }
    rows = list(
        (
            await db.execute(
                in_window(
                    select(
                        LanguageError.id,
                        LanguageError.turn_id,
                        LanguageError.category,
                        LanguageError.subcategory,
                        LanguageError.span_start,
                        LanguageError.span_end,
                        LanguageError.original,
                        LanguageError.correction,
                        LanguageError.explanation,
                        LanguageError.detector,
                        LanguageError.confidence,
                        LanguageError.asr_suspect,
                        LanguageError.form,
                        LanguageError.corrected_form,
                        Turn.session_id,
                        Turn.created_at,
                    )
                    .select_from(LanguageError)
                    .join(Turn, Turn.id == LanguageError.turn_id)
                ).order_by(
                    Turn.created_at.desc(),
                    LanguageError.turn_id,
                    LanguageError.span_start,
                )
            )
        ).all()
    )
    words = int(words or 0)

    counted = [row for row in rows if is_counted(row)]
    tallies = forms.tally(
        used, [forms.Link(row.form, row.corrected_form) for row in counted]
    )
    weakest, gate = await _weakest(db, user, tallies)

    return GrammarOut(
        since=since,
        until=until,
        totals=GrammarTotals(
            sessions=int(sessions),
            turns=int(turns),
            words=words,
            corrections=len(rows),
            counted=len(counted),
        ),
        categories=await _categories(db, rows, words),
        forms=_forms(tallies, counted),
        weakest=weakest,
        weakest_gate=gate,
        caveat=GRAMMAR_CAVEAT if rows else None,
    )


async def _categories(
    db: AsyncSession, rows: list, words: int
) -> list[CategoryCorrections]:
    """Each kind of correction, most counted first, with its newest few in their sentence."""
    grouped: dict[str, list] = {}
    for row in rows:
        grouped.setdefault(row.category, []).append(row)

    quoted = [
        row
        for found in grouped.values()
        for row in found[:GRAMMAR_EXAMPLES_PER_CATEGORY]
    ]
    context = {
        turn_id: (transcript or "", title)
        for turn_id, transcript, title in (
            await db.execute(
                select(Turn.id, Turn.transcript, Scenario.title)
                .join(PracticeSession, PracticeSession.id == Turn.session_id)
                .outerjoin(Scenario, Scenario.id == PracticeSession.scenario_id)
                .where(Turn.id.in_(sorted({row.turn_id for row in quoted})))
            )
        ).all()
    }

    categories = []
    for category, found in grouped.items():
        counted = [row for row in found if is_counted(row)]
        by_detector: dict[str, int] = {}
        for row in found:
            by_detector[row.detector] = by_detector.get(row.detector, 0) + 1
        categories.append(
            CategoryCorrections(
                category=category,
                label=readable(category),
                description=CATEGORY_GLOSS.get(category, ""),
                counted=len(counted),
                not_counted=len(found) - len(counted),
                per_100_words=round(len(counted) * 100 / words, 2) if words else None,
                by_detector=dict(sorted(by_detector.items())),
                examples=[
                    _example(row, *context.get(row.turn_id, ("", None)))
                    for row in found[:GRAMMAR_EXAMPLES_PER_CATEGORY]
                ],
            )
        )
    categories.sort(
        key=lambda c: (-c.counted, -(c.counted + c.not_counted), c.category)
    )
    return categories


def _example(row, transcript: str, scenario_title: str | None) -> CorrectionExample:
    before, quote, after = excerpt(
        transcript, row.span_start, row.span_end, row.original
    )
    return CorrectionExample(
        id=row.id,
        session_id=row.session_id,
        turn_id=row.turn_id,
        said_at=row.created_at,
        scenario_title=scenario_title,
        before=before,
        quote=quote,
        after=after,
        original=row.original,
        correction=row.correction,
        explanation=row.explanation,
        subcategory=row.subcategory,
        detector=row.detector,
        counted=is_counted(row),
        asr_suspect=row.asr_suspect,
        form=row.form,
        corrected_form=row.corrected_form,
    )


def _bare(text: str) -> str:
    """Letters and digits only, lowercased: what was said, without how it was written."""
    return "".join(ch for ch in text if ch.isalnum()).lower()


def placed(transcript: str, start: int | None, end: int | None, original: str) -> bool:
    """Whether the stored offsets hold the words the correction quotes.

    Compared the way the offsets were found — letters and digits only — so a difference in
    capitals or spacing still places it and a different word does not.
    """
    return (
        start is not None
        and end is not None
        and 0 <= start < end <= len(transcript)
        and _bare(transcript[start:end]) == _bare(original)
    )


def sentence_bounds(
    transcript: str, start: int, end: int
) -> tuple[int, int, bool, bool]:
    """Where the sentence around `[start, end)` begins and ends, and whether each side was cut.

    The sentence runs to the nearest `.`, `?` or `!` either side, and no further than
    `GRAMMAR_CONTEXT_CHARS` from the words — the recogniser often writes a turn as one
    sentence — cut back to a whole word where there is a space to cut at.
    """
    opens = max(transcript.rfind(mark, 0, start) for mark in ".?!") + 1
    closes = [i for mark in ".?!" if (i := transcript.find(mark, end)) != -1]
    stops = min(closes) + 1 if closes else len(transcript)
    while opens < start and transcript[opens].isspace():
        opens += 1
    while stops > end and transcript[stops - 1].isspace():
        stops -= 1

    cut_before = start - opens > GRAMMAR_CONTEXT_CHARS
    if cut_before:
        cut = start - GRAMMAR_CONTEXT_CHARS
        space = transcript.find(" ", cut, start)
        opens = space + 1 if space != -1 else cut
    cut_after = stops - end > GRAMMAR_CONTEXT_CHARS
    if cut_after:
        cut = transcript[end : end + GRAMMAR_CONTEXT_CHARS]
        stops = end + (cut.rfind(" ") if " " in cut.strip() else len(cut))
    return opens, stops, cut_before, cut_after


def excerpt(
    transcript: str, start: int | None, end: int | None, original: str
) -> tuple[str, str | None, str]:
    """The sentence a correction sits in, cut around it: before, the words, after.

    The words are the transcript's. Unplaced, all three are empty but the quote is None,
    and the correction is shown on its own.
    """
    if not placed(transcript, start, end, original):
        return "", None, ""

    opens, stops, cut_before, cut_after = sentence_bounds(transcript, start, end)
    before = ("…" if cut_before else "") + transcript[opens:start]
    after = transcript[end:stops] + ("…" if cut_after else "")
    return before, transcript[start:end], after


def _forms(tallies: dict[str, forms.FormTally], counted: list) -> list[FormPractice]:
    """Each verb form said or needed, in the vocabulary's order, with the corrections behind it."""
    behind: dict[str, list[FormCorrection]] = {}
    for row in counted:
        touched = {row.form, row.corrected_form} - {None}
        for form in touched:
            behind.setdefault(form, []).append(
                FormCorrection(
                    id=row.id,
                    session_id=row.session_id,
                    original=row.original,
                    correction=row.correction,
                    form=row.form,
                    corrected_form=row.corrected_form,
                )
            )
    return [
        FormPractice(
            form=form,
            label=readable(form),
            used=tally.used,
            right=tally.right,
            wrong=tally.wrong,
            missed=tally.missed,
            corrections=behind.get(form, [])[:GRAMMAR_CORRECTIONS_PER_FORM],
        )
        for form, tally in tallies.items()
    ]


def _floor_sentence() -> str:
    return (
        f"A form is named here once it has come up {PROGRESS_MIN_FORM_CONTEXTS} times "
        f"and been corrected {GRAMMAR_MIN_FORM_CORRECTIONS} times — said wrongly, or "
        "needed where you said something else. Many of the language model's corrections "
        "are wrong, and fewer than that could be its mistakes rather than yours."
    )


async def _weakest(
    db: AsyncSession, user: User, tallies: dict[str, forms.FormTally]
) -> tuple[WeakestForm | None, Gate]:
    """The verb form right least often, among those with enough behind them."""

    def corrected(tally: forms.FormTally) -> int:
        return tally.wrong + tally.missed

    nearest = max((corrected(tally) for tally in tallies.values()), default=0)
    qualified = [
        (form, tally)
        for form, tally in tallies.items()
        if tally.contexts >= PROGRESS_MIN_FORM_CONTEXTS
        and corrected(tally) >= GRAMMAR_MIN_FORM_CORRECTIONS
    ]
    if not qualified:
        if nearest == 0:
            said = "No correction so far has changed a verb form. "
        else:
            form, tally = max(
                tallies.items(), key=lambda item: (corrected(item[1]), item[1].contexts)
            )
            count = corrected(tally)
            said = (
                f"The form with the most corrections so far is the {readable(form)}: "
                f"{count} correction{'' if count == 1 else 's'}, from the "
                f"{tally.contexts} time{'' if tally.contexts == 1 else 's'} it was said "
                "or needed. "
            )
        return None, Gate(
            shown=False,
            reason=said + _floor_sentence(),
            have=nearest,
            need=GRAMMAR_MIN_FORM_CORRECTIONS,
        )

    form, tally = min(
        qualified,
        key=lambda item: (
            item[1].right / item[1].contexts,
            -corrected(item[1]),
            item[0],
        ),
    )
    scenario = await _scenario_for(db, form, user.cefr_self_assessed)
    parts = [
        part
        for part in (
            f"said wrongly {_times(tally.wrong)}" if tally.wrong else None,
            (
                f"needed {_times(tally.missed)} where you said something else"
                if tally.missed
                else None
            ),
        )
        if part
    ]
    reason = (
        f"Right {tally.right} of {tally.contexts} — {' and '.join(parts)}. Of the forms "
        "corrected often enough to name one, this one is right least often."
    )
    reason += (
        f" {scenario.title} is written to draw it out."
        if scenario
        else " No scenario is written to draw it out yet."
    )
    return (
        WeakestForm(
            form=form,
            label=readable(form),
            used=tally.used,
            right=tally.right,
            wrong=tally.wrong,
            missed=tally.missed,
            reason=reason,
            scenario_slug=scenario.slug if scenario else None,
            scenario_title=scenario.title if scenario else None,
        ),
        Gate(shown=True, have=corrected(tally), need=GRAMMAR_MIN_FORM_CORRECTIONS),
    )


def _times(count: int) -> str:
    return "once" if count == 1 else f"{count} times"


async def _scenario_for(
    db: AsyncSession, form: str, band: str | None
) -> Scenario | None:
    """An active scenario that declares the form, at the learner's own band where one does."""
    offering = [
        scenario
        for scenario in (
            await db.scalars(
                select(Scenario)
                .where(Scenario.is_active.is_(True))
                .order_by(Scenario.slug)
            )
        ).all()
        if form in (scenario.target_grammar or [])
    ]
    if not offering:
        return None
    return next((s for s in offering if s.cefr_band == band), offering[0])
