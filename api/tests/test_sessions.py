"""Starting, listing, reading, ending and deleting a session.

The turn endpoint has a file of its own. What is here is everything around it, and the
theme is that a session is the first thing in this system that is both **private** and
**reachable by a guessable integer**: `GET /sessions/41` is a URL anybody can type, and
behind it is a transcript and audio of somebody's voice. So a good half of this file is
the same question asked five ways — does the second account get a 404.
"""

import pytest

from db_models import PracticeSession, Turn
from services.llm import get_provider
from tests.conftest import BrokenProvider, register_account, unique_email

SLUG = "job-interview-backend"


@pytest.fixture
def broken_provider():
    """The model layer, down."""
    from main import app

    stub = BrokenProvider()
    app.dependency_overrides[get_provider] = lambda: stub
    yield stub
    app.dependency_overrides.pop(get_provider, None)


async def start(client, slug: str = SLUG):
    return await client.post("/sessions", json={"scenario_slug": slug})


# ── Starting ────────────────────────────────────────────────────────────────


async def test_starting_a_session_returns_the_personas_opening_turn(
    seeded, client, account, provider, voice, audio_root
):
    """The opening line is generated rather than seeded: a scenario that always opens
    with the same sentence is a scenario you have already heard."""
    response = await start(client)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["scenario_slug"] == SLUG
    assert body["status"] == "active"
    assert body["turn_count"] == 1

    opening = body["turns"][0]
    assert opening["role"] == "assistant"
    assert opening["idx"] == 0
    assert opening["transcript"]
    assert opening["audio_url"] == f"/audio/{opening['audio_asset_id']}"
    assert opening["llm_model"] == "stub-model"


async def test_the_opening_turn_is_playable_through_the_audio_endpoint(
    seeded, client, account, provider, voice, audio_root
):
    """The reply audio goes through the same ownership-checked route a recording does.
    A separate path for synthesised speech would be a second place to get that wrong."""
    body = (await start(client)).json()

    response = await client.get(body["turns"][0]["audio_url"])

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.content.startswith(b"RIFF")


async def test_the_persona_prompt_never_reaches_the_client(
    seeded, client, account, provider, voice, audio_root
):
    """The same property `test_scenarios.py` asserts of the catalogue, asserted again
    where a session could plausibly leak it. It is the exercise: a user who reads
    "push back twice on a vague answer" is no longer practising the thing."""
    body = (await start(client)).json()

    assert "hiring manager" not in str(body).lower()
    assert "persona_prompt" not in str(body)


async def test_a_scenario_that_does_not_exist_is_a_404(
    seeded, client, account, provider
):
    response = await start(client, "no-such-scenario")

    assert response.status_code == 404
    assert "no-such-scenario" in response.json()["detail"]


async def test_starting_a_session_needs_a_session(seeded, client, provider):
    """No cookie, no conversation. The route table test asserts this over every
    endpoint; this one shows the status code."""
    response = await start(client)

    assert response.status_code == 401


async def test_the_model_being_down_is_a_503_and_writes_nothing(
    seeded, client, account, broken_provider, voice, audio_root, db_session
):
    """Generation degrades explicitly, never a fabricated reply.

    And nothing is written. The session row is created in the same transaction as its
    first turn precisely so that a machine with no Ollama does not accumulate empty
    sessions as the most common row in the table.
    """
    response = await start(client)

    assert response.status_code == 503
    assert "not responding" in response.json()["detail"]

    # Scoped to this account: the test database is created once per run and never
    # truncated between tests, so a global count would be counting other tests.
    from sqlalchemy import func, select

    mine = await db_session.scalar(
        select(func.count(PracticeSession.id)).where(
            PracticeSession.user_id == account["id"]
        )
    )
    assert mine == 0


# ── Listing and reading ─────────────────────────────────────────────────────


async def test_history_is_newest_first_and_paginated(
    seeded, client, account, provider, voice, audio_root
):
    for _ in range(3):
        assert (await start(client)).status_code == 201

    page = (await client.get("/sessions", params={"limit": 2})).json()

    assert page["total"] == 3
    assert len(page["items"]) == 2
    assert page["items"][0]["id"] > page["items"][1]["id"]
    assert page["items"][0]["turn_count"] == 1
    assert page["items"][0]["scenario_title"]


async def test_the_second_page_is_the_rest(
    seeded, client, account, provider, voice, audio_root
):
    for _ in range(3):
        await start(client)

    first = (await client.get("/sessions", params={"limit": 2, "offset": 0})).json()
    second = (await client.get("/sessions", params={"limit": 2, "offset": 2})).json()

    ids = [item["id"] for item in first["items"] + second["items"]]
    assert len(set(ids)) == 3


async def test_an_absurd_page_size_is_refused_rather_than_served(
    seeded, client, account
):
    """A server-side ceiling, not advice. `?limit=100000` must not become a query that
    reads a year of history because a client asked without thinking."""
    response = await client.get("/sessions", params={"limit": 100000})

    assert response.status_code == 422


async def test_a_session_reads_back_with_its_whole_transcript(
    seeded, client, account, provider, voice, audio_root
):
    """This is the request a page reload makes."""
    created = (await start(client)).json()

    body = (await client.get(f"/sessions/{created['id']}")).json()

    assert body["id"] == created["id"]
    assert [turn["idx"] for turn in body["turns"]] == [0]
    assert body["turns"][0]["transcript"] == created["turns"][0]["transcript"]


async def test_another_accounts_session_is_a_404_and_never_a_403(
    seeded, client, other_client, account, provider, voice, audio_root
):
    """403 confirms the session exists and belongs to somebody else, which is the fact
    the guess was probing for. 404 is indistinguishable from an id never issued."""
    mine = (await start(client)).json()
    await register_account(other_client, email=unique_email("intruder"))

    for method, path in (
        ("get", f"/sessions/{mine['id']}"),
        ("post", f"/sessions/{mine['id']}/end"),
        ("delete", f"/sessions/{mine['id']}"),
    ):
        response = await getattr(other_client, method)(path)
        assert response.status_code == 404, (method, path, response.status_code)


async def test_a_session_that_never_existed_gets_the_same_404(seeded, client, account):
    """Same status and same shape as somebody else's session. If they differed, the
    difference would be the leak."""
    response = await client.get("/sessions/987654321")

    assert response.status_code == 404


async def test_another_accounts_sessions_are_absent_from_the_list(
    seeded, client, other_client, account, provider, voice, audio_root
):
    await start(client)
    await register_account(other_client, email=unique_email("stranger"))

    assert (await other_client.get("/sessions")).json()["total"] == 0


# ── Ending ──────────────────────────────────────────────────────────────────


async def test_ending_a_session_produces_a_report_and_closes_it(
    seeded, client, account, provider, voice, audio_root
):
    provider.replies = [
        "Tell me about your experience.",
        '{"summary": "A short interview.", "goal_met": false, "note": "Clear answers."}',
    ]
    created = (await start(client)).json()

    body = (await client.post(f"/sessions/{created['id']}/end")).json()

    assert body["status"] == "completed"
    assert body["ended_at"] is not None
    assert body["report"]["measured"]["turns"]["total"] == 1
    assert body["report"]["narrative"]["goal_met"] is False
    assert "taxonomy" in body["report"]["pending"]["errors"]


async def test_ending_a_session_twice_returns_the_same_report(
    seeded, client, account, provider, voice, audio_root
):
    """Idempotent on purpose. Regenerating would spend a model call to produce a
    *different* narrative for a conversation that has not changed, and a report that
    reads differently every time you open it is not a record of anything."""
    created = (await start(client)).json()

    first = (await client.post(f"/sessions/{created['id']}/end")).json()
    calls_after_first = len(provider.calls)
    second = (await client.post(f"/sessions/{created['id']}/end")).json()

    assert first["report"] == second["report"]
    assert len(provider.calls) == calls_after_first, "the model was asked a second time"


async def test_a_session_still_ends_when_the_model_is_down(
    seeded, client, account, provider, voice, audio_root
):
    """A session stuck in `active` because a container was restarting would be a worse
    failure than a report with a missing paragraph. The counts come from rows; only the
    prose needs Ollama."""
    from main import app

    created = (await start(client)).json()
    app.dependency_overrides[get_provider] = lambda: BrokenProvider()

    body = (await client.post(f"/sessions/{created['id']}/end")).json()

    assert body["status"] == "completed"
    assert body["report"]["measured"]["turns"]["total"] == 1
    assert body["report"]["narrative"]["status"] == "unavailable"


# ── Deleting ────────────────────────────────────────────────────────────────


async def test_deleting_a_session_removes_its_turns_and_its_audio(
    seeded, client, account, provider, voice, audio_root, db_session
):
    """Delete has to mean delete. A session removed from the history while its audio
    stays on the volume — still fetchable by anyone holding the asset id — is not a
    promise this project should make."""
    from sqlalchemy import func, select

    from db_models import AudioAsset

    created = (await start(client)).json()
    asset_id = created["turns"][0]["audio_asset_id"]
    stored = [path for path in audio_root.rglob("*") if path.is_file()]
    assert stored, "the opening turn wrote no audio, so this test proves nothing"

    response = await client.delete(f"/sessions/{created['id']}")
    assert response.status_code == 204

    assert await db_session.get(PracticeSession, created["id"]) is None
    remaining = await db_session.scalar(
        select(func.count(Turn.id)).where(Turn.session_id == created["id"])
    )
    assert remaining == 0
    assert await db_session.get(AudioAsset, asset_id) is None
    assert [path for path in audio_root.rglob("*") if path.is_file()] == []

    assert (await client.get(f"/audio/{asset_id}")).status_code == 404


async def test_an_asset_another_row_still_needs_survives_the_delete(
    seeded, client, account, provider, voice, audio_root, db_session
):
    """Assets are content-addressed, so one row can be referenced more than once —
    by a read-aloud attempt as well as a turn. Deleting on the strength of "this session
    referenced it" would eventually take a recording out from under something still
    using it."""
    from sqlalchemy import select

    from db_models import AudioAsset, User

    created = (await start(client)).json()
    asset_id = created["turns"][0]["audio_asset_id"]

    # A second session, and a turn in it pointing at the same asset.
    other = (await start(client)).json()
    user = await db_session.scalar(select(User).where(User.email == account["email"]))
    db_session.add(
        Turn(session_id=other["id"], idx=99, role="assistant", audio_asset_id=asset_id)
    )
    await db_session.commit()

    assert (await client.delete(f"/sessions/{created['id']}")).status_code == 204

    assert await db_session.get(AudioAsset, asset_id) is not None
    assert user is not None
