"""The analysis job: claiming a turn, writing three kinds of row, and never raising.

These run the real job against the test database with a stub provider, so what is under
test is the transaction shape rather than the labelling. The two properties worth having
are that running it twice does not double anything, and that a failure leaves a row a
later pass can pick up.
"""

import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from db_models import (
    FluencyMetrics,
    GrammarUsage,
    LanguageError,
    PracticeSession,
    Turn,
    User,
)
from services import analysis
from services.analysis import (
    Analyser,
    analyse_turn,
    ensure_session_analysed,
    pending_turn_ids,
    reparse_turn,
    summarise,
)
from services.security import hash_password
from tests.conftest import BrokenProvider, StubProvider, unique_email

TRANSCRIPT = "yesterday I go to the office and I speak with my manager"


def reply(*errors: dict) -> str:
    import json

    return json.dumps({"errors": list(errors)})


AN_ERROR = {
    "category": "VERB_TENSE",
    "subcategory": "missing_past_marker",
    "original": "I go to the office",
    "correction": "I went to the office",
    "explanation": "Yesterday needs the past simple.",
    "confidence": 0.9,
}


def timings(transcript: str, logprob: float = -0.05) -> list[dict]:
    """Word timings that reproduce `transcript` when joined with single spaces."""
    out, start = [], 0
    for token in transcript.split():
        out.append(
            {"w": token, "start_ms": start, "end_ms": start + 300, "logprob": logprob}
        )
        start += 400
    return out


@pytest.fixture
def factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest.fixture
async def turn(db_session, seeded):
    """One user turn on a real session, owed analysis."""
    from db_models import Scenario

    user = User(
        email=unique_email("analysis"),
        password_hash=hash_password("practice-makes-permanent"),
        native_language="es",
    )
    db_session.add(user)
    await db_session.flush()

    scenario = await db_session.scalar(
        select(Scenario).where(Scenario.slug == "daily-standup")
    )
    session = PracticeSession(
        user_id=user.id, scenario_id=scenario.id, mode="conversation"
    )
    db_session.add(session)
    await db_session.flush()

    row = Turn(
        session_id=session.id,
        idx=0,
        role="user",
        transcript=TRANSCRIPT,
        words=timings(TRANSCRIPT),
        asr_confidence=0.95,
        analysis_status="pending",
    )
    db_session.add(row)
    await db_session.commit()
    return row


async def rows_for(db, model, turn_id: int) -> list:
    column = model.turn_id
    return list((await db.scalars(select(model).where(column == turn_id))).all())


# ── The happy path ──────────────────────────────────────────────────────────


async def test_analysis_writes_fluency_grammar_and_errors(turn, factory, db_session):
    outcome = await analyse_turn(turn.id, factory, StubProvider([reply(AN_ERROR)]))

    assert outcome.status == "analyzed"
    await db_session.refresh(turn)
    assert turn.analysis_status == "analyzed"
    assert turn.analyzed_at is not None

    measures = await db_session.get(FluencyMetrics, turn.id)
    assert measures is not None
    assert measures.word_count == len(TRANSCRIPT.split())

    features = {
        row.feature: row.count
        for row in await rows_for(db_session, GrammarUsage, turn.id)
    }
    assert features.get("past_simple") or features.get("present_simple")

    found = await rows_for(db_session, LanguageError, turn.id)
    assert len(found) == 1
    assert found[0].detector == "llm"
    assert found[0].category == "VERB_TENSE"
    assert found[0].asr_suspect is False


async def test_running_it_twice_does_not_double_anything(turn, factory, db_session):
    """A live job and a backfill can reach the same turn. Replacing rather than appending
    is what keeps two readings of one turn from being interleaved under it."""
    await analyse_turn(turn.id, factory, StubProvider([reply(AN_ERROR)]))

    async with factory() as db:
        again = await db.get(Turn, turn.id)
        again.analysis_status = "pending"
        await db.commit()

    await analyse_turn(turn.id, factory, StubProvider([reply(AN_ERROR)]))

    assert len(await rows_for(db_session, LanguageError, turn.id)) == 1
    assert len(await rows_for(db_session, FluencyMetrics, turn.id)) == 1


async def test_a_turn_already_claimed_is_left_alone(turn, factory, db_session):
    """The claim is what stops two jobs writing the same rows."""
    async with factory() as db:
        claimed = await db.get(Turn, turn.id)
        claimed.analysis_status = "analyzing"
        await db.commit()

    provider = StubProvider([reply(AN_ERROR)])
    outcome = await analyse_turn(turn.id, factory, provider)

    assert outcome.status == "claimed-elsewhere"
    assert provider.calls == []


async def test_an_assistant_turn_is_not_analysed(turn, factory, db_session):
    reply_turn = Turn(
        session_id=turn.session_id,
        idx=1,
        role="assistant",
        transcript="Thanks for the update.",
    )
    db_session.add(reply_turn)
    await db_session.commit()

    outcome = await analyse_turn(reply_turn.id, factory, StubProvider([reply()]))
    assert outcome.status == "skipped"
    await db_session.refresh(reply_turn)
    assert reply_turn.analysis_status is None


# ── Failure, and what survives it ───────────────────────────────────────────


async def test_a_model_that_is_down_still_leaves_the_fluency_numbers(
    turn, factory, db_session
):
    """Fluency and the forms are arithmetic and a parse. They succeed whether or not
    Ollama is running, and a turn that keeps them is not a turn worth recomputing."""
    outcome = await analyse_turn(turn.id, factory, BrokenProvider())

    assert outcome.status == "analyzed"
    await db_session.refresh(turn)
    assert turn.analysis_status == "analyzed"
    assert "unavailable" in turn.analysis_error
    assert await db_session.get(FluencyMetrics, turn.id) is not None
    assert await rows_for(db_session, LanguageError, turn.id) == []


async def test_the_job_records_a_crash_rather_than_raising(turn, factory, monkeypatch):
    """Nobody awaits this task. An escaping exception would be logged as an unretrieved
    future and the turn would sit in `analyzing` for ever."""
    from services import analysis

    def boom(*args, **kwargs):
        raise RuntimeError("the parser exploded")

    monkeypatch.setattr(analysis.fluency, "analyse", boom)
    outcome = await analyse_turn(turn.id, factory, StubProvider([reply()]))

    assert outcome.status == "failed"
    async with factory() as db:
        failed = await db.get(Turn, turn.id)
    assert failed.analysis_status == "failed"
    assert "RuntimeError" in failed.analysis_error


async def test_a_failed_turn_is_picked_up_again(turn, factory, db_session):
    """There is no separate retry queue. A turn whose model was down is exactly the turn
    a later pass should take."""
    await analyse_turn(turn.id, factory, BrokenProvider())
    async with factory() as db:
        done = await db.get(Turn, turn.id)
        done.analysis_status = "failed"
        await db.commit()
        assert turn.id in await pending_turn_ids(db)


async def test_a_rule_row_is_stored_as_the_rules(turn, factory, db_session):
    """The one column that says which layer proposed a row."""
    async with factory() as db:
        row = await db.get(Turn, turn.id)
        row.transcript = "my sister work in a bank near the station"
        row.words = timings(row.transcript)
        await db.commit()

    await analyse_turn(turn.id, factory, BrokenProvider())

    found = await rows_for(db_session, LanguageError, turn.id)
    assert [(f.detector, f.category, f.confidence) for f in found] == [
        ("rule", "SUBJECT_VERB_AGREEMENT", 1.0)
    ]


async def test_the_summary_says_which_detector_found_what(turn, factory, db_session):
    """A layer that covers two categories finds those two more reliably than the model
    finds the rest, so the split by category is read differently once it is there — and
    the report has to say how the rows divide."""
    async with factory() as db:
        row = await db.get(Turn, turn.id)
        row.transcript = "I go to the office every day and my sister work in a bank"
        row.words = timings(row.transcript)
        await db.commit()

    duplicate = dict(
        AN_ERROR,
        category="SUBJECT_VERB_AGREEMENT",
        subcategory="third_person_s",
        original="my sister work",
        correction="my sister works",
    )
    await analyse_turn(turn.id, factory, StubProvider([reply(AN_ERROR, duplicate)]))
    summary = await summarise(db_session, turn.session_id, None)

    errors = summary["errors"]
    assert errors["by_detector"] == {"llm": 1, "rule": 1}
    assert sorted(item["detector"] for item in errors["items"]) == ["llm", "rule"]
    assert errors["superseded"] == 1
    assert errors["rejected"] == 0
    assert errors["rejection_rate"] == 0.0


async def test_a_correction_is_stored_with_the_forms_it_was_made_in(
    turn, factory, db_session
):
    """`I go` corrected to `I went`: said in the present simple, needing the past."""
    await analyse_turn(turn.id, factory, StubProvider([reply(AN_ERROR)]))

    (found,) = await rows_for(db_session, LanguageError, turn.id)
    assert (found.form, found.corrected_form) == ("present_simple", "past_simple")


async def test_the_summary_gives_accuracy_per_form(turn, factory, db_session):
    """Two present simples, one of them corrected to a past: the present simple is right
    once in two, and the past simple was needed once and never said."""
    await analyse_turn(turn.id, factory, StubProvider([reply(AN_ERROR)]))
    summary = await summarise(db_session, turn.session_id, None)

    assert summary["form_accuracy"] == {
        "present_simple": {
            "used": 2,
            "right": 1,
            "wrong": 1,
            "missed": 0,
            "accuracy": 0.5,
        },
        "past_simple": {
            "used": 0,
            "right": 0,
            "wrong": 0,
            "missed": 1,
            "accuracy": 0.0,
        },
    }
    (item,) = summary["errors"]["items"]
    assert (item["form"], item["corrected_form"]) == ("present_simple", "past_simple")


async def test_a_failed_join_still_stores_the_correction(
    turn, factory, db_session, monkeypatch
):
    """The correction is real without its forms. It is stored unlinked, and says why."""
    from services import analysis

    def boom(*args, **kwargs):
        raise RuntimeError("the join exploded")

    monkeypatch.setattr(analysis.forms, "link", boom)
    outcome = await analyse_turn(turn.id, factory, StubProvider([reply(AN_ERROR)]))

    assert outcome.status == "analyzed"
    (found,) = await rows_for(db_session, LanguageError, turn.id)
    assert (found.form, found.corrected_form) == (None, None)
    await db_session.refresh(turn)
    assert "the form join failed" in turn.analysis_error


async def test_reparse_recounts_and_relinks_without_the_model(
    turn, factory, db_session
):
    """For a change to the parser or the join: the stored transcript and correction are
    all it needs, and the correction itself is not touched."""
    await analyse_turn(turn.id, factory, StubProvider([reply(AN_ERROR)]))
    async with factory() as db:
        (row,) = await rows_for(db, LanguageError, turn.id)
        row.form = row.corrected_form = None
        usage = await db.scalar(
            select(GrammarUsage).where(
                GrammarUsage.turn_id == turn.id,
                GrammarUsage.feature == "present_simple",
            )
        )
        usage.count = 9
        analysed_at = (await db.get(Turn, turn.id)).analyzed_at
        await db.commit()

    done = await reparse_turn(turn.id, factory)

    assert done.forms_before["present_simple"] == 9
    assert done.forms_after["present_simple"] == 2
    assert (done.corrections, done.linked) == (1, 1)
    async with factory() as db:
        (row,) = await rows_for(db, LanguageError, turn.id)
        assert (row.form, row.corrected_form) == ("present_simple", "past_simple")
        assert row.correction == AN_ERROR["correction"]
        assert (await db.get(Turn, turn.id)).analyzed_at > analysed_at


async def test_reparse_leaves_a_turn_that_was_never_analysed(turn, factory):
    assert await reparse_turn(turn.id, factory) is None


async def test_rejections_are_stored_on_the_turn(turn, factory, db_session):
    """The rate is the measurement that says whether the labelling model is strong
    enough, and it is not recoverable later from the proposals that passed."""
    invented = dict(AN_ERROR, category="SPELLING")
    await analyse_turn(turn.id, factory, StubProvider([reply(invented)]))

    await db_session.refresh(turn)
    assert turn.analysis_rejects
    assert turn.analysis_rejects[0]["reason"] == "unknown_category"
    assert await rows_for(db_session, LanguageError, turn.id) == []


# ── A whole session ─────────────────────────────────────────────────────────


async def test_ensure_session_analysed_clears_what_is_outstanding(
    turn, factory, db_session
):
    analysed, outstanding = await ensure_session_analysed(
        turn.session_id, factory, StubProvider([reply(AN_ERROR)])
    )
    assert (analysed, outstanding) == (1, 0)


async def test_a_zero_budget_leaves_the_turn_for_later(turn, factory, db_session):
    """A report written short says how many turns it is missing, and ending the session
    again picks up where it left off."""
    analysed, outstanding = await ensure_session_analysed(
        turn.session_id, factory, StubProvider([reply()]), budget_s=0
    )
    assert (analysed, outstanding) == (0, 1)


class GatedProvider(StubProvider):
    """A labelling model that answers only when the test says so."""

    def __init__(self, replies) -> None:
        super().__init__(replies)
        self.asked = asyncio.Event()
        self.answer = asyncio.Event()

    async def complete(self, messages, max_tokens=None, temperature=None):
        self.asked.set()
        await self.answer.wait()
        return await super().complete(messages, max_tokens, temperature)


async def test_ending_waits_for_a_turn_already_being_analysed(
    turn, factory, db_session
):
    """The live job claims a turn the moment the reply goes back, so ending straight
    after speaking finds the last turn mid-analysis. Skipping it wrote the report
    without it."""
    live = GatedProvider([reply(AN_ERROR)])
    Analyser(factory, live).launch(turn.id)
    await asyncio.wait_for(live.asked.wait(), 30)

    ending = asyncio.create_task(
        ensure_session_analysed(
            turn.session_id, factory, StubProvider([reply()]), budget_s=30
        )
    )
    await asyncio.sleep(0.2)
    assert not ending.done()

    live.answer.set()
    assert await asyncio.wait_for(ending, 30) == (1, 0)
    summary = await summarise(db_session, turn.session_id, None)
    assert summary["complete"] is True
    assert summary["errors"]["total"] == 1


async def test_at_the_deadline_the_live_job_is_left_to_finish(
    turn, factory, db_session
):
    """It is doing the work. Cancelling it would throw away a turn nearly analysed; left
    running, it writes what an incomplete report is later finished from."""
    live = GatedProvider([reply(AN_ERROR)])
    Analyser(factory, live).launch(turn.id)
    await asyncio.wait_for(live.asked.wait(), 30)

    assert await ensure_session_analysed(
        turn.session_id, factory, StubProvider([reply()]), budget_s=0.2
    ) == (0, 1)

    job = analysis._jobs[turn.id]
    live.answer.set()
    outcome = await asyncio.wait_for(job, 30)
    assert outcome.status == "analyzed"
    assert turn.id not in analysis._jobs


async def test_a_turn_claimed_by_another_process_is_waited_for(
    turn, factory, db_session
):
    """A backfill run from the command line holds its claim in another process, where
    there is no job to await. Its turn is looked at again until it is done."""
    async with factory() as db:
        (await db.get(Turn, turn.id)).analysis_status = "analyzing"
        await db.commit()

    async def finish_elsewhere():
        await asyncio.sleep(0.3)
        async with factory() as db:
            (await db.get(Turn, turn.id)).analysis_status = "analyzed"
            await db.commit()

    elsewhere = asyncio.create_task(finish_elsewhere())
    provider = StubProvider([reply()])
    assert await ensure_session_analysed(
        turn.session_id, factory, provider, budget_s=30
    ) == (1, 0)
    await elsewhere
    assert provider.calls == []


async def test_a_cancelled_job_puts_its_turn_back_in_the_queue(
    turn, factory, db_session
):
    """A server that stops mid-analysis cancels the job. A turn left in `analyzing` has
    nothing coming to finish it and nothing that will take it again."""
    live = GatedProvider([reply(AN_ERROR)])
    job = asyncio.create_task(analyse_turn(turn.id, factory, live))
    await asyncio.wait_for(live.asked.wait(), 30)

    job.cancel()
    with pytest.raises(asyncio.CancelledError):
        await job

    async with factory() as db:
        released = await db.get(Turn, turn.id)
        assert released.analysis_status == "pending"
        assert "interrupted" in released.analysis_error
        assert turn.id in await pending_turn_ids(db)
    assert await rows_for(db_session, LanguageError, turn.id) == []


async def test_the_session_summary_reports_what_was_not_elicited(
    turn, factory, db_session
):
    """A set difference, not a judgement: the scenario names the forms it was built to
    elicit in the same vocabulary the parser counts in."""
    from db_models import Scenario

    await analyse_turn(turn.id, factory, StubProvider([reply(AN_ERROR)]))
    session = await db_session.get(PracticeSession, turn.session_id)
    scenario = await db_session.get(Scenario, session.scenario_id)

    summary = await summarise(db_session, turn.session_id, scenario)

    assert summary["complete"] is True
    assert summary["turns_analysed"] == 1
    assert summary["target_forms"]["declared"] == scenario.target_grammar
    assert set(summary["target_forms"]["elicited"]) | set(
        summary["target_forms"]["not_elicited"]
    ) == set(scenario.target_grammar)
    assert summary["fluency"]["words_spoken"] == len(TRANSCRIPT.split())
    assert summary["errors"]["counted"] == 1
    assert summary["errors"]["per_100_words"] is not None


async def test_a_suspect_error_is_shown_but_not_counted(turn, factory, db_session):
    """Shown, because a transcript with a hole in it is worse. Not counted, because a
    trend that moves for the recogniser's reasons is worse than both."""
    import math

    from db_models import Scenario

    async with factory() as db:
        row = await db.get(Turn, turn.id)
        row.words = [
            dict(word, logprob=math.log(0.2)) if word["w"] == "go" else word
            for word in timings(TRANSCRIPT)
        ]
        await db.commit()

    await analyse_turn(turn.id, factory, StubProvider([reply(AN_ERROR)]))

    session = await db_session.get(PracticeSession, turn.session_id)
    scenario = await db_session.get(Scenario, session.scenario_id)
    summary = await summarise(db_session, turn.session_id, scenario)

    assert summary["errors"]["total"] == 1
    assert summary["errors"]["counted"] == 0
    assert summary["errors"]["asr_suspect"] == 1
    assert summary["errors"]["items"][0]["counted"] is False
    assert summary["form_accuracy"]["present_simple"]["wrong"] == 0
    assert "past_simple" not in summary["form_accuracy"]


async def test_a_session_with_no_user_turns_is_complete_rather_than_empty(
    db_session, seeded
):
    """A read-aloud sitting has nothing to analyse. That is a finished state, not an
    outstanding one, and a report must not wait for it."""
    user = User(
        email=unique_email("empty"),
        password_hash=hash_password("practice-makes-permanent"),
    )
    db_session.add(user)
    await db_session.flush()
    session = PracticeSession(user_id=user.id, mode="read_aloud")
    db_session.add(session)
    await db_session.commit()

    summary = await summarise(db_session, session.id, None)
    assert summary["complete"] is True
    assert summary["fluency"] is None
