"""What a stopped API left owed, picked up when it starts: `services/catchup.py`.

The rows are made the way the product makes them, through the endpoints, and then left
where a process that stopped mid-job leaves them. The suite shares one database and the
catch-up goes over everything owed in it, whoever's; so every assertion here is about this
test's own rows, and the analysis batch is made large enough to reach them.
"""

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

import main
from db_models import (
    Attempt,
    LanguageError,
    PracticeSession,
    ProgressSnapshot,
    Rehearsal,
    Scenario,
    Turn,
)
from services import catchup
from services.analysis import analyse_turn
from services.rollup import is_stale
from tests.conftest import StubProvider, silent_wav

PASSAGE = "third-street-theatre"
SCRIPT = "Good morning. I am glad you came.\n\nFirst the numbers. We grew last year."
TRANSCRIPT = "yesterday I go to the office and I speak with my manager"
AN_ERROR = (
    '{"errors": [{"category": "VERB_TENSE", "subcategory": "missing_past_marker", '
    '"original": "I go to the office", "correction": "I went to the office", '
    '"explanation": "Yesterday needs the past simple.", "confidence": 0.9}]}'
)
EVERYTHING = 100_000


@pytest.fixture
def factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


async def serving(name: str) -> bool:
    return True


async def nothing_serving(name: str) -> bool:
    return False


async def read_aloud(client) -> dict:
    response = await client.post(
        "/attempts",
        files={"file": ("reading.wav", silent_wav(3400), "audio/wav")},
        data={"passage_slug": PASSAGE},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def take(client, presentation_id: int) -> dict:
    response = await client.post(
        f"/presentations/{presentation_id}/sections/0/takes",
        files={"file": ("take.wav", silent_wav(3400), "audio/wav")},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def script(client) -> dict:
    response = await client.post(
        "/presentations", json={"title": "A talk", "script": SCRIPT}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def user_turn(factory, user_id: int, status: str = "pending") -> int:
    """A user turn on a conversation of this account, in the state given."""
    async with factory() as db:
        scenario = await db.scalar(
            select(Scenario).where(Scenario.slug == "daily-standup")
        )
        session = PracticeSession(
            user_id=user_id, scenario_id=scenario.id, mode="conversation"
        )
        db.add(session)
        await db.flush()
        words, start = [], 0
        for token in TRANSCRIPT.split():
            words.append(
                {"w": token, "start_ms": start, "end_ms": start + 300, "logprob": -0.05}
            )
            start += 400
        row = Turn(
            session_id=session.id,
            idx=0,
            role="user",
            transcript=TRANSCRIPT,
            words=words,
            asr_confidence=0.95,
            analysis_status=status,
        )
        db.add(row)
        await db.commit()
        return row.id


async def set_state(factory, model, row_id: int, **values) -> None:
    async with factory() as db:
        row = await db.get(model, row_id)
        for name, value in values.items():
            setattr(row, name, value)
        await db.commit()


async def fetch(factory, model, row_id: int):
    async with factory() as db:
        return await db.get(model, row_id)


# ── Releasing the claims ────────────────────────────────────────────────────


async def test_the_claims_a_stopped_process_left_go_back_in_the_queue(
    client,
    account,
    seeded,
    audio_root,
    reader,
    aligner,
    scorer,
    rehearsal_scorer,
    phonemizer,
    factory,
):
    attempt = await read_aloud(client)
    talk = await script(client)
    kept = await take(client, talk["id"])
    assert (
        await client.patch("/auth/me", json={"retain_audio": False})
    ).status_code == 200
    unkept = await take(client, talk["id"])
    turn_id = await user_turn(factory, account["id"], status="analyzing")
    await set_state(factory, Attempt, attempt["id"], status="scoring")
    await set_state(factory, Rehearsal, kept["id"], pron_status="scoring")
    await set_state(factory, Rehearsal, unkept["id"], pron_status="scoring")

    released = await catchup.release_claims(factory)

    assert released.attempts >= 1 and released.takes >= 1 and released.turns >= 1
    assert (await fetch(factory, Attempt, attempt["id"])).status == "pending"
    assert (await fetch(factory, Rehearsal, kept["id"])).pron_status == "pending"
    turn = await fetch(factory, Turn, turn_id)
    assert turn.analysis_status == "pending"
    assert turn.analysis_error == catchup.INTERRUPTED
    # Its bytes lived in the task that stopped: closed, and saying so.
    closed = await fetch(factory, Rehearsal, unkept["id"])
    assert closed.audio_asset_id is None
    assert closed.pron_status == "scored"
    assert closed.pron_detail == catchup.NOT_KEPT


# ── The work ────────────────────────────────────────────────────────────────


async def test_a_reading_left_scoring_is_scored_once_the_api_is_back(
    client, account, seeded, audio_root, reader, aligner, scorer, factory
):
    attempt = await read_aloud(client)
    await set_state(factory, Attempt, attempt["id"], status="scoring")

    await catchup.release_claims(factory)
    await catchup.catch_up(
        factory, StubProvider(), serving, wait_s=0, poll_s=0, batch=0
    )

    detail = (await client.get(f"/attempts/{attempt['id']}")).json()
    assert detail["status"] == "scored"
    assert detail["pronunciation"] == "ok"
    assert detail["phoneme_count"] == 2
    assert any(text.startswith("The theatre on Third Street") for text in aligner.texts)


async def test_a_kept_take_left_scoring_is_scored_against_its_section(
    client, account, audio_root, reader, aligner, rehearsal_scorer, phonemizer, factory
):
    talk = await script(client)
    left = await take(client, talk["id"])
    await set_state(factory, Rehearsal, left["id"], pron_status="scoring")

    await catchup.release_claims(factory)
    await catchup.catch_up(
        factory, StubProvider(), serving, wait_s=0, poll_s=0, batch=0
    )

    row = await fetch(factory, Rehearsal, left["id"])
    assert row.pron_status == "scored"
    assert row.pron_detail is None
    assert aligner.texts.count(talk["sections"][0]["body"]) == 1


async def test_a_pending_turn_is_analysed(
    client, account, seeded, audio_root, aligner, factory
):
    turn_id = await user_turn(factory, account["id"])

    await catchup.catch_up(
        factory,
        StubProvider([AN_ERROR]),
        serving,
        wait_s=0,
        poll_s=0,
        batch=EVERYTHING,
    )

    assert (await fetch(factory, Turn, turn_id)).analysis_status == "analyzed"
    async with factory() as db:
        errors = await db.scalar(
            select(func.count())
            .select_from(LanguageError)
            .where(LanguageError.turn_id == turn_id)
        )
    assert errors == 1


async def test_a_stale_account_is_rolled_up(client, account, seeded, factory):
    turn_id = await user_turn(factory, account["id"])
    await analyse_turn(turn_id, factory, StubProvider([AN_ERROR]))
    async with factory() as db:
        assert await is_stale(db, account["id"])

    await catchup.catch_up(factory, StubProvider(), nothing_serving, wait_s=0, poll_s=0)

    async with factory() as db:
        assert not await is_stale(db, account["id"])
        written = await db.scalar(
            select(func.count())
            .select_from(ProgressSnapshot)
            .where(ProgressSnapshot.user_id == account["id"])
        )
    assert written > 0


# ── Waiting for the services, and the claims of the live paths ──────────────


async def test_nothing_is_scored_before_pron_has_loaded_its_model(
    client, account, seeded, audio_root, reader, aligner, scorer, factory
):
    """Scored now it would be closed as unscorable for good, with pron a second away."""
    attempt = await read_aloud(client)

    done = await catchup.catch_up(
        factory, StubProvider(), nothing_serving, wait_s=0.05, poll_s=0.01
    )

    assert done.attempts == 0
    assert aligner.calls == 0
    assert (await fetch(factory, Attempt, attempt["id"])).status == "pending"


async def test_nothing_is_analysed_while_the_labelling_model_is_down(
    client, account, seeded, factory
):
    """Analysed now, the turn would be stored without its errors, and never asked again."""
    turn_id = await user_turn(factory, account["id"])
    provider = StubProvider([AN_ERROR])

    await catchup.catch_up(
        factory, provider, nothing_serving, wait_s=0.05, poll_s=0.01, batch=EVERYTHING
    )

    assert provider.calls == []
    assert (await fetch(factory, Turn, turn_id)).analysis_status == "pending"


async def test_a_row_a_request_claimed_first_is_left_to_it(
    client, account, seeded, audio_root, reader, aligner, scorer, factory
):
    """The live path claims as the catch-up does, so whichever is first does the work."""
    attempt = await read_aloud(client)

    async def claimed_while_waiting(name: str) -> bool:
        # A rescore arrives while the catch-up waits for pron, and claims the reading.
        await set_state(factory, Attempt, attempt["id"], status="scoring")
        return True

    await catchup.catch_up(
        factory, StubProvider(), claimed_while_waiting, wait_s=0, poll_s=0, batch=0
    )

    assert (await fetch(factory, Attempt, attempt["id"])).status == "scoring"
    assert not any(
        text.startswith("The theatre on Third Street") for text in aligner.texts
    )


async def test_only_a_claim_is_released(client, account, seeded, factory):
    """A finished turn, and a failed one nothing has claimed, are left as they are."""
    analysed = await user_turn(factory, account["id"], status="analyzed")
    failed = await user_turn(factory, account["id"], status="failed")

    await catchup.release_claims(factory)

    assert (await fetch(factory, Turn, analysed)).analysis_status == "analyzed"
    assert (await fetch(factory, Turn, failed)).analysis_status == "failed"


# ── The API's start ─────────────────────────────────────────────────────────


async def test_the_api_releases_and_starts_the_work_when_it_starts(monkeypatch):
    begun = []

    async def begin(session_factory, provider):
        begun.append((session_factory, provider))
        return None

    monkeypatch.setattr(main, "STARTUP_CATCHUP", True)
    monkeypatch.setattr(main.catchup, "begin", begin)

    async with main.lifespan(main.app):
        assert len(begun) == 1


async def test_nothing_is_caught_up_with_the_flag_off(monkeypatch):
    begun = []

    async def begin(session_factory, provider):
        begun.append(provider)

    monkeypatch.setattr(main, "STARTUP_CATCHUP", False)
    monkeypatch.setattr(main.catchup, "begin", begin)

    async with main.lifespan(main.app):
        pass
    assert begun == []


async def test_a_database_that_cannot_be_read_does_not_stop_the_api():
    """On a database not yet migrated the release fails; the API starts all the same."""

    def broken_factory():
        raise RuntimeError('relation "turns" does not exist')

    assert await catchup.begin(broken_factory, StubProvider()) is None
