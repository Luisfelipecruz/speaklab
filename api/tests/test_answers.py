"""Make your point: the two operations, with the recogniser and the model replaced.

What is asserted is what the page is built on: an answer is counted, stored without its
recording, and given feedback that cannot stop it being stored; a second attempt is linked
to the first; the history judges only what has a better end; and nobody reaches another
account's answers.
"""

import json

from sqlalchemy import func, select

from db_models import Answer, AudioAsset
from services import structure
from services.llm import get_provider
from tests.conftest import BrokenProvider, register_account

PROMPT = "explain-a-failed-release"

SAID = (
    "Yesterday the release broke checkout for an hour. It failed because the new version "
    "expected a field that the old app does not send. We we rolled back after 20 minutes. "
    "For example, every payment from the app failed. In short, a missing field."
)

FEEDBACK = json.dumps(
    {
        "lead": "Say first that a missing field broke checkout.",
        "gaps": [],
        "rewrite": "The release broke checkout because the new version expected a field "
        "the old app does not send, so we rolled back.",
    }
)


def recording(name: str = "answer.webm") -> dict:
    return {"file": (name, b"not really audio", "audio/webm")}


async def say(client, prompt: str = PROMPT, **form):
    return await client.post(
        "/answers", data={"prompt": prompt, **form}, files=recording()
    )


async def test_the_page_needs_an_account(client, seeded):
    assert (await client.get("/answers")).status_code == 401


async def test_every_prompt_is_listed_and_nothing_is_answered_yet(
    client, seeded, account
):
    response = await client.get("/answers")

    assert response.status_code == 200
    body = response.json()
    assert len(body["prompts"]) == 13
    assert {prompt["answers"] for prompt in body["prompts"]} == {0}
    assert body["answered"] == 0
    assert body["answers"] == []
    assert body["history"]
    assert all(not series["gate"]["shown"] for series in body["history"])


async def test_an_answer_is_counted_stored_without_its_recording_and_explained(
    client, seeded, account, db_session, recogniser, provider
):
    recogniser.append(SAID)
    provider.replies = [FEEDBACK]
    assets_before = await db_session.scalar(select(func.count(AudioAsset.id)))

    response = await say(client)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["transcript"] == SAID
    assert body["prompt"]["slug"] == PROMPT
    built = body["structure"]
    assert built["signposts"]["reason"] == 1
    assert built["signposts"]["example"] == 1
    assert built["signposts"]["close"] == 1
    assert built["repeats"] == 1
    assert built["sentences"] == 5
    assert {item["kind"] for item in built["found"]} <= set(built["shown"])
    assert body["delivery"]["words"] == len(SAID.split())
    assert body["feedback"]["status"] == "ok"
    assert body["feedback"]["rewrite"].startswith("The release broke checkout")
    assert "did not hear you" in body["feedback"]["caveat"]

    stored = await db_session.scalar(select(Answer).where(Answer.id == body["id"]))
    assert stored.transcript == SAID
    assert stored.feedback["status"] == "ok"
    assert await db_session.scalar(select(func.count(AudioAsset.id))) == assets_before


async def test_restarts_are_counted_and_stored_but_not_sent(
    client, seeded, account, db_session, recogniser, provider
):
    recogniser.append("Their API had no, there was no documentation. So we guessed.")
    provider.replies = [FEEDBACK]

    body = (await say(client)).json()

    assert structure.RESTART not in body["structure"]["shown"]
    assert "restarts" not in body["structure"]
    assert all(item["kind"] != structure.RESTART for item in body["structure"]["found"])
    stored = await db_session.scalar(select(Answer).where(Answer.id == body["id"]))
    assert stored.structure["restarts"] == 1


async def test_saying_it_again_links_the_two_and_lists_them_newest_first(
    client, seeded, account, recogniser, provider
):
    provider.replies = [FEEDBACK]
    first = (await say(client)).json()

    second = await say(client, again_of=str(first["id"]))

    assert second.status_code == 201, second.text
    assert second.json()["again_of"] == first["id"]
    page = (await client.get("/answers", params={"prompt": PROMPT})).json()
    assert page["prompt"]["slug"] == PROMPT
    assert [answer["id"] for answer in page["answers"]] == [
        second.json()["id"],
        first["id"],
    ]
    (summary,) = [p for p in page["prompts"] if p["slug"] == PROMPT]
    assert summary["answers"] == 2
    assert page["answered"] == 2


async def test_saying_again_an_answer_to_another_prompt_is_refused(
    client, seeded, account, recogniser, provider
):
    first = (await say(client)).json()

    response = await say(client, prompt="recommend-a-tool", again_of=str(first["id"]))

    assert response.status_code == 409


async def test_another_accounts_answer_is_not_found(
    client, seeded, account, other_client, recogniser, provider
):
    await register_account(other_client)
    theirs = (await say(other_client)).json()

    response = await say(client, again_of=str(theirs["id"]))

    assert response.status_code == 404
    page = (await client.get("/answers")).json()
    assert page["answered"] == 0


async def test_an_unknown_prompt_is_a_404_both_ways(
    client, seeded, account, recogniser
):
    recogniser.append("never heard")

    assert (await say(client, prompt="no-such-prompt")).status_code == 404
    assert (await client.get("/answers", params={"prompt": "nope"})).status_code == 404
    assert recogniser == ["never heard"]


async def test_a_recording_with_no_speech_in_it_is_refused_and_not_stored(
    client, seeded, account, db_session, recogniser, provider
):
    recogniser.append("Um.")

    response = await say(client)

    assert response.status_code == 422
    assert "Nothing was heard" in response.json()["detail"]
    assert provider.calls == []


async def test_a_recording_over_the_limit_is_refused_before_it_is_heard(
    client, seeded, account, recogniser, monkeypatch
):
    from routers import answers as answers_router

    monkeypatch.setattr(answers_router, "MAX_UPLOAD_BYTES", 5)
    recogniser.append("never heard")

    response = await say(client)

    assert response.status_code == 413
    assert recogniser == ["never heard"]


async def test_a_model_that_is_down_still_leaves_the_answer_counted(
    client, seeded, account, recogniser
):
    from main import app

    app.dependency_overrides[get_provider] = lambda: BrokenProvider()
    try:
        recogniser.append(SAID)
        response = await say(client)
    finally:
        app.dependency_overrides.pop(get_provider, None)

    assert response.status_code == 201
    body = response.json()
    assert body["feedback"]["status"] == "unavailable"
    assert body["structure"]["signposts"]["reason"] == 1


async def test_the_history_judges_fillers_and_repeats_and_nothing_else(
    client, seeded, account, recogniser, provider
):
    base = "We shipped the release and it worked well for everyone on the team. " * 5
    for fillers in (3, 2, 1):
        recogniser.append("Um, " * fillers + base)
        assert (await say(client)).status_code == 201

    history = {
        series["metric"]: series
        for series in (await client.get("/answers")).json()["history"]
    }

    assert len(history["fillers_per_100_words"]["points"]) == 3
    assert history["fillers_per_100_words"]["direction"] == "improving"
    assert history["repeats_per_100_words"]["better"] == "lower"
    for metric in ("speech_rate_wpm", "words_per_sentence", "signposts"):
        assert history[metric]["direction"] is None
        assert history[metric]["better"] is None


async def test_a_short_answer_gets_no_rate_on_the_history(
    client, seeded, account, recogniser, provider
):
    recogniser.append("We rolled back. It worked.")
    await say(client)

    history = {
        series["metric"]: series
        for series in (await client.get("/answers")).json()["history"]
    }

    (point,) = history["fillers_per_100_words"]["points"]
    assert point["value"] is None
    assert "fewer than" in point["withheld"]
    assert history["speech_rate_wpm"]["points"][0]["value"] is not None
