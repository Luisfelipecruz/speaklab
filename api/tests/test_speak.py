"""Hearing one word, and everything the route refuses to say.

Most of what is worth testing here is the refusing. A route that synthesises speech is
one closed set away from being an open text-to-speech service, and the set is the whole
design — so the case that matters most is a word that exists, is spelled correctly, and
belongs to somebody else's script.

The voice is stubbed. What it sounds like is not this file's business; that it is asked
for a *repeatable* rendering is, because a specimen that changes on every press is the
thing the pinned settings exist to prevent.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db_models import Passage
from models.speech import Speech
from services import phone_names, wer
from tests.conftest import register_account, silent_wav

pytestmark = pytest.mark.asyncio

SCRIPT = "Our warehouse throughput doubled. The freight bill did not."
OTHERS = "Peregrine falcons nest on the cathedral spire every spring."


@pytest.fixture
def voice_for_words(monkeypatch):
    """The tts call, recorded rather than made. Returns the list of calls."""
    from routers import speak as route

    calls: list[dict] = []

    async def fake_speak(text, voice=None, length_scale=None, client=None, **kwargs):
        calls.append({"text": text, **kwargs})
        return Speech(
            audio=silent_wav(400),
            voice="stub-voice",
            sample_rate=22050,
            duration_ms=400,
            sentences=1,
            length_scale=1.0,
            latency_ms=1,
        )

    monkeypatch.setattr(route, "speak", fake_speak)
    return calls


async def save_script(client: AsyncClient, script: str) -> dict:
    response = await client.post(
        "/presentations", json={"title": "A talk", "script": script}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def a_passage_word(db: AsyncSession) -> str:
    """A word that is in a shipped passage and is not already an example word.

    Chosen from the seeded rows rather than written down here, so the test keeps
    meaning what it says when the passages are edited.
    """
    bodies = (await db.execute(select(Passage.body).where(Passage.is_active))).scalars()
    examples = set(phone_names.EXAMPLE_WORDS.values())
    for body in bodies:
        for word in wer.normalise(body):
            if word not in examples and "'" not in word:
                return word
    raise AssertionError("no passage word outside the example words")


async def test_a_sound_this_system_names_is_a_sound_it_can_say(
    client: AsyncClient, account: dict, voice_for_words: list
):
    response = await client.get("/speak/is")

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "audio/wav"
    assert response.content.startswith(b"RIFF")
    assert [call["text"] for call in voice_for_words] == ["is"]


async def test_every_phone_has_a_word_that_can_be_spoken(
    client: AsyncClient, account: dict, voice_for_words: list
):
    """The naming table and the speaking route agree about all thirty-nine.

    A sound named on a screen with no word behind it would be a button that 404s, which
    is worse than no button.
    """
    for phone in phone_names.PHONE_NAMES:
        word = phone_names.example_word_of(phone)
        assert word is not None, phone
        response = await client.get(f"/speak/{word}")
        assert response.status_code == 200, f"{phone} -> {word}: {response.text}"


async def test_a_word_from_a_shipped_passage_is_spoken(
    client: AsyncClient, account: dict, seeded: AsyncSession, voice_for_words: list
):
    word = await a_passage_word(seeded)

    assert (await client.get(f"/speak/{word}")).status_code == 200


async def test_a_word_from_your_own_script_is_spoken(
    client: AsyncClient, account: dict, voice_for_words: list
):
    await save_script(client, SCRIPT)

    assert (await client.get("/speak/throughput")).status_code == 200


async def test_a_word_from_somebody_elses_script_is_not(
    client: AsyncClient,
    account: dict,
    other_client: AsyncClient,
    voice_for_words: list,
):
    """The set is per account, and this is the case that proves it is not global.

    `peregrine` is a real word, spelled correctly, and sitting in a script this system
    holds — just not in one belonging to the caller. It is a 404 and the voice is never
    asked, because the alternative is that any account can read any other account's
    vocabulary one request at a time.
    """
    await register_account(other_client)
    await save_script(other_client, OTHERS)

    response = await client.get("/speak/peregrine")

    assert response.status_code == 404
    assert voice_for_words == []

    assert (await other_client.get("/speak/peregrine")).status_code == 200


async def test_a_word_in_nothing_at_all_is_not_found(
    client: AsyncClient, account: dict, voice_for_words: list
):
    response = await client.get("/speak/perambulate")

    assert response.status_code == 404
    assert voice_for_words == []


@pytest.mark.parametrize("requested", ["see the", "...", "'"])
async def test_what_is_not_one_word_is_refused_before_the_set_is_consulted(
    client: AsyncClient, account: dict, voice_for_words: list, requested: str
):
    """Two words, and marks that normalise away to none. Both fail the same way.

    A digit is deliberately not in this list: `2026` is one word to the tokeniser, so it
    is refused or spoken by the same rule as any other — whether it appears in text this
    account already has — rather than by a separate rule about numbers.
    """
    response = await client.get(f"/speak/{requested}")

    assert response.status_code == 404
    assert voice_for_words == []


async def test_a_figure_is_governed_by_the_set_like_any_other_word(
    client: AsyncClient, account: dict, voice_for_words: list
):
    assert (await client.get("/speak/2026")).status_code == 404

    await save_script(client, "We doubled in 2026. Nobody expected that.")

    assert (await client.get("/speak/2026")).status_code == 200


async def test_the_word_reaches_the_voice_in_the_form_the_system_holds(
    client: AsyncClient, account: dict, voice_for_words: list
):
    """`Is` and `is` are one word, and the voice is asked for it once, in one spelling."""
    assert (await client.get("/speak/Is")).status_code == 200

    assert [call["text"] for call in voice_for_words] == ["is"]


async def test_the_voice_is_asked_for_a_rendering_that_does_not_change(
    client: AsyncClient, account: dict, voice_for_words: list
):
    """Both noise sources off. This is the whole reason the route exists as its own."""
    await client.get("/speak/see")

    assert voice_for_words[0]["noise_scale"] == 0.0
    assert voice_for_words[0]["noise_w_scale"] == 0.0


async def test_a_caller_who_already_has_the_word_is_answered_without_synthesising_it(
    client: AsyncClient, account: dict, voice_for_words: list
):
    """The saving is the synthesis, not the transfer.

    A deterministic rendering means the tag can be computed from the voice, the word and
    the settings — so a matching `If-None-Match` is answered before the voice is called
    at all, rather than after producing bytes that are then thrown away.
    """
    first = await client.get("/speak/think")
    tag = first.headers["etag"]
    assert len(voice_for_words) == 1

    again = await client.get("/speak/think", headers={"If-None-Match": tag})

    assert again.status_code == 304
    assert again.content == b""
    assert len(voice_for_words) == 1


async def test_the_word_says_how_long_it_may_be_kept_and_that_it_is_not_shared(
    client: AsyncClient, account: dict, voice_for_words: list
):
    response = await client.get("/speak/see")

    assert response.headers["cache-control"].startswith("private,")
    assert response.headers["etag"]


async def test_two_different_words_do_not_share_an_identity(
    client: AsyncClient, account: dict, voice_for_words: list
):
    see = (await client.get("/speak/see")).headers["etag"]
    think = (await client.get("/speak/think")).headers["etag"]

    assert see != think


async def test_a_voice_that_is_not_answering_is_not_a_missing_word(
    client: AsyncClient, account: dict, monkeypatch
):
    """503, not 404. The word exists; the thing that says it does not."""
    from routers import speak as route
    from services.tts_client import TtsUnavailable

    async def broken(*args, **kwargs):
        raise TtsUnavailable("connection refused")

    monkeypatch.setattr(route, "speak", broken)

    assert (await client.get("/speak/is")).status_code == 503


async def test_nobody_is_spoken_to_without_signing_in(client: AsyncClient):
    assert (await client.get("/speak/is")).status_code == 401
