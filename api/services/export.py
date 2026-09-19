"""Assemble one account's history for `GET /progress/export`.

One query per table, each filtered to the caller, grouped here. Walking the ORM
relationships instead would issue a query per session and another per turn, and a history
of a few hundred turns would be a few hundred round trips for one download.
"""

from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import VERSION
from db_models import (
    Answer,
    AnswerPrompt,
    Attempt,
    AudioAsset,
    FluencyMetrics,
    GrammarUsage,
    LanguageError,
    Passage,
    PhonemeScore,
    PracticeSession,
    Presentation,
    PresentationSection,
    ProgressSnapshot,
    Rehearsal,
    RehearsalPhone,
    Scenario,
    Turn,
    User,
)
from models.export import (
    ExportAccount,
    ExportAnswer,
    ExportCorrection,
    ExportFluency,
    ExportPhone,
    ExportPresentation,
    ExportReading,
    ExportRecording,
    ExportRehearsal,
    ExportSection,
    ExportSession,
    ExportSnapshot,
    ExportTurn,
    HistoryExport,
)


async def build(db: AsyncSession, user: User) -> HistoryExport:
    session_ids = select(PracticeSession.id).where(PracticeSession.user_id == user.id)
    turn_ids = select(Turn.id).where(Turn.session_id.in_(session_ids))
    attempt_ids = select(Attempt.id).where(Attempt.session_id.in_(session_ids))

    recordings = await db.scalars(
        select(AudioAsset).where(AudioAsset.user_id == user.id).order_by(AudioAsset.id)
    )

    fluency = {
        row.turn_id: ExportFluency.model_validate(row)
        for row in await db.scalars(
            select(FluencyMetrics).where(FluencyMetrics.turn_id.in_(turn_ids))
        )
    }
    forms: dict[int, dict[str, int]] = defaultdict(dict)
    for row in await db.scalars(
        select(GrammarUsage)
        .where(GrammarUsage.turn_id.in_(turn_ids))
        .order_by(GrammarUsage.id)
    ):
        forms[row.turn_id][row.feature] = row.count
    corrections: dict[int, list[ExportCorrection]] = defaultdict(list)
    for row in await db.scalars(
        select(LanguageError)
        .where(LanguageError.turn_id.in_(turn_ids))
        .order_by(LanguageError.id)
    ):
        corrections[row.turn_id].append(ExportCorrection.model_validate(row))

    turns: dict[int, list[ExportTurn]] = defaultdict(list)
    for row in await db.scalars(
        select(Turn)
        .where(Turn.session_id.in_(session_ids))
        .order_by(Turn.session_id, Turn.idx)
    ):
        turn = ExportTurn.model_validate(row)
        if row.audio_asset_id is not None:
            turn.audio_url = f"/audio/{row.audio_asset_id}"
        turn.fluency = fluency.get(row.id)
        turn.forms = forms.get(row.id, {})
        turn.corrections = corrections.get(row.id, [])
        turns[row.session_id].append(turn)

    # Built field by field rather than validated from the row: `PracticeSession.turns` is
    # a relationship, and reading it here would lazy-load outside the async session.
    sessions = [
        ExportSession(
            id=row.id,
            scenario_slug=slug,
            mode=row.mode,
            status=row.status,
            started_at=row.started_at,
            ended_at=row.ended_at,
            report=row.report,
            turns=turns.get(row.id, []),
        )
        for row, slug in await db.execute(
            select(PracticeSession, Scenario.slug)
            .outerjoin(Scenario, PracticeSession.scenario_id == Scenario.id)
            .where(PracticeSession.user_id == user.id)
            .order_by(PracticeSession.started_at, PracticeSession.id)
        )
    ]

    phones: dict[int, list[ExportPhone]] = defaultdict(list)
    for row in await db.scalars(
        select(PhonemeScore)
        .where(PhonemeScore.attempt_id.in_(attempt_ids))
        .order_by(
            PhonemeScore.attempt_id, PhonemeScore.word_idx, PhonemeScore.phone_idx
        )
    ):
        phones[row.attempt_id].append(ExportPhone.model_validate(row))

    readings = []
    for row, slug in await db.execute(
        select(Attempt, Passage.slug)
        .join(Passage, Attempt.passage_id == Passage.id)
        .where(Attempt.session_id.in_(session_ids))
        .order_by(Attempt.created_at, Attempt.id)
    ):
        reading = ExportReading.model_validate(row)
        reading.passage_slug = slug
        reading.audio_url = f"/audio/{row.audio_asset_id}"
        reading.phones = phones.get(row.id, [])
        readings.append(reading)

    answers = []
    for row, slug in await db.execute(
        select(Answer, AnswerPrompt.slug)
        .join(AnswerPrompt, Answer.prompt_id == AnswerPrompt.id)
        .where(Answer.user_id == user.id)
        .order_by(Answer.created_at, Answer.id)
    ):
        answer = ExportAnswer.model_validate(row)
        answer.prompt_slug = slug
        answers.append(answer)

    section_rows = (
        await db.scalars(
            select(PresentationSection)
            .join(
                Presentation,
                Presentation.id == PresentationSection.presentation_id,
            )
            .where(Presentation.user_id == user.id)
            .order_by(PresentationSection.presentation_id, PresentationSection.idx)
        )
    ).all()
    sections: dict[int, list[ExportSection]] = defaultdict(list)
    # Which script and which position each take belongs to, so a take can name both
    # without a reader having to join the two lists by hand.
    where_a_take_belongs: dict[int, tuple[int, int]] = {}
    for row in section_rows:
        sections[row.presentation_id].append(ExportSection.model_validate(row))
        where_a_take_belongs[row.id] = (row.presentation_id, row.idx)

    # Built field by field rather than from the row, because both of these models carry
    # a list whose name is also a relationship on the row — and validating from attributes
    # would reach for it, which is a lazy load inside an async session and an error rather
    # than a query.
    presentations = [
        ExportPresentation(
            id=row.id,
            title=row.title,
            script=row.script,
            word_count=row.word_count,
            audience_brief=row.audience_brief,
            created_at=row.created_at,
            updated_at=row.updated_at,
            sections=sections.get(row.id, []),
        )
        for row in await db.scalars(
            select(Presentation)
            .where(Presentation.user_id == user.id)
            .order_by(Presentation.created_at, Presentation.id)
        )
    ]

    take_phones: dict[int, list[ExportPhone]] = defaultdict(list)
    for row in await db.scalars(
        select(RehearsalPhone)
        .join(Rehearsal, Rehearsal.id == RehearsalPhone.rehearsal_id)
        .where(Rehearsal.user_id == user.id)
        .order_by(
            RehearsalPhone.rehearsal_id,
            RehearsalPhone.word_idx,
            RehearsalPhone.phone_idx,
        )
    ):
        take_phones[row.rehearsal_id].append(ExportPhone.model_validate(row))

    rehearsals = []
    for row in await db.scalars(
        select(Rehearsal)
        .where(Rehearsal.user_id == user.id)
        .order_by(Rehearsal.created_at, Rehearsal.id)
    ):
        presentation_id, section_idx = where_a_take_belongs.get(
            row.section_id, (None, None)
        )
        rehearsals.append(
            ExportRehearsal(
                id=row.id,
                presentation_id=presentation_id,
                section_idx=section_idx,
                audio_url=(
                    f"/audio/{row.audio_asset_id}"
                    if row.audio_asset_id is not None
                    else None
                ),
                transcript=row.transcript,
                words=row.words,
                duration_ms=row.duration_ms,
                asr_confidence=row.asr_confidence,
                asr_model=row.asr_model,
                wer=row.wer,
                alignment=row.alignment,
                delivery=row.delivery,
                pron_status=row.pron_status,
                pron_detail=row.pron_detail,
                pron_summary=row.pron_summary,
                phones=take_phones.get(row.id, []),
                scored_at=row.scored_at,
                created_at=row.created_at,
            )
        )

    snapshots = await db.scalars(
        select(ProgressSnapshot)
        .where(ProgressSnapshot.user_id == user.id)
        .order_by(ProgressSnapshot.period, ProgressSnapshot.period_start)
    )

    return HistoryExport(
        exported_at=datetime.now(timezone.utc),
        version=VERSION,
        account=ExportAccount.model_validate(user),
        recordings=[ExportRecording.of(row) for row in recordings],
        sessions=sessions,
        readings=readings,
        answers=answers,
        presentations=presentations,
        rehearsals=rehearsals,
        snapshots=[ExportSnapshot.model_validate(row) for row in snapshots],
    )
