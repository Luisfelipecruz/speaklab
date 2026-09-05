"""Read-aloud end to end: the endpoint, the job, and every way `pron` can decline.

The through-line of this file is one requirement, PRD R6: **an attempt with the
pronunciation service switched off is still a useful attempt.** It has a transcript, it
has a WER against the passage, and it says in words why there are no phones. That is not
graceful degradation as a nicety — `pron` is profiled and 5 GB, so "switched off" is the
*default* state of a fresh clone, and an endpoint that 500s there would make read-aloud
look broken to everybody who had not read the Makefile.

The other half is FR-16: a failure is a row state with a reason on it, and it can be run
again without asking the user to read anything twice.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from db_models import Attempt, PhonemeScore
from tests.conftest import register_account, silent_wav

PASSAGE = "third-street-theatre"


async def read_aloud(client: AsyncClient, slug: str = PASSAGE, **data) -> dict:
    """Post a reading. Returns the created attempt."""
    response = await client.post(
        "/attempts",
        files={"file": ("reading.wav", silent_wav(3400), "audio/wav")},
        data={"passage_slug": slug, **data},
    )
    assert response.status_code == 201, response.text
    return response.json()


# ── The happy path ──────────────────────────────────────────────────────────


async def test_a_reading_returns_a_transcript_before_it_is_scored(
    client, account, seeded, audio_root, reader, aligner, scorer
):
    """201 with the transcript and the WER already on it, and the phones still to come.

    This is the two-clock design in one assertion. Transcription cannot be deferred — the
    `audio_assets` row needs a decoder's account of the file — so it happens in the
    request. Alignment can be, and is. The client gets something to show immediately and
    polls for the rest (FR-15).
    """
    attempt = await read_aloud(client)

    assert attempt["status"] == "pending"
    assert attempt["transcript"]
    assert attempt["wer"] is not None
    assert attempt["passage_slug"] == PASSAGE
    assert attempt["passage_body"].startswith("The theatre on Third Street")
    assert attempt["phonemes"] == []
    assert attempt["audio_url"] == f"/audio/{attempt['id']}".replace(
        str(attempt["id"]), attempt["audio_url"].rsplit("/", 1)[1]
    )


async def test_the_job_stores_a_phone_per_row_and_marks_the_attempt_scored(
    client, account, seeded, audio_root, reader, aligner, scorer, db_session
):
    """The phones land, in order, with the substitution that makes them actionable."""
    attempt = await read_aloud(client)
    await scorer.drain()

    detail = (await client.get(f"/attempts/{attempt['id']}")).json()
    assert detail["status"] == "scored"
    assert detail["pronunciation"] == "ok"
    assert detail["phoneme_count"] == 2

    phones = detail["phonemes"]
    assert [p["canonical_phone"] for p in phones] == ["DH", "TH"]

    # The pair the whole feature exists for: not "your /θ/ is weak" but "you produced an
    # /s/ where English wants /θ/".
    assert phones[1]["recognized_phone"] == "s"
    assert phones[1]["gop"] == pytest.approx(-9.4)

    stored = (
        await db_session.scalars(
            select(PhonemeScore).where(PhonemeScore.attempt_id == attempt["id"])
        )
    ).all()
    assert len(stored) == 2


async def test_the_reference_text_sent_to_the_aligner_is_the_passage(
    client, account, seeded, audio_root, reader, aligner, scorer
):
    """The assertion that would otherwise never fail visibly.

    Aligning a recording against the wrong passage produces a complete set of plausible
    numbers about nothing at all — every phone scored, every score meaningless. Nothing
    downstream can tell. So the text that crossed the wire is checked here.
    """
    await read_aloud(client)
    await scorer.drain()

    assert len(aligner.texts) == 1
    assert aligner.texts[0].startswith("The theatre on Third Street is worth the trip.")
    assert "thistles" in aligner.texts[0], "the whole passage, not the first sentence"


async def test_the_summary_is_recomputed_from_the_stored_rows(
    client, account, seeded, audio_root, reader, aligner, scorer
):
    """Four numbers derived on read, not a column that can drift from its inputs."""
    await read_aloud(client)
    await scorer.drain()
    detail = (await client.get("/attempts")).json()["items"][0]
    full = (await client.get(f"/attempts/{detail['id']}")).json()

    assert full["summary"]["phones"] == 2
    assert full["summary"]["mean_gop"] == pytest.approx(-4.7)

    # Interpolated, not "the worst one": with two phones at 0.0 and -9.4 the 5th
    # percentile sits 5 % of the way up from the bottom, at -8.93. It is the same linear
    # interpolation `spike/analyze.py` used to set m0's threshold and the same one
    # `infra/pron/gop.py` computes, which is the point — three places, one definition of
    # what a percentile means here.
    assert full["summary"]["percentile_5"] == pytest.approx(-8.93)


# ── WER, and what it is for ─────────────────────────────────────────────────


async def test_reading_the_passage_correctly_scores_a_wer_of_zero(
    client, account, seeded, audio_root, reader, aligner, scorer, db_session
):
    from db_models import Passage

    passage = await db_session.scalar(select(Passage).where(Passage.slug == PASSAGE))
    reader.append(passage.body)

    attempt = await read_aloud(client)
    assert attempt["wer"] == pytest.approx(0.0)


async def test_reading_something_else_scores_a_wer_near_one(
    client, account, seeded, audio_root, reader, aligner, scorer
):
    """The sanity check on the alignment, not only a reading grade.

    A WER near 1.0 means the speaker read some other text, and per-phone GOP against the
    wrong words is noise with decimal places. The number is stored so that a screen — or
    m10's trend — can decline to draw conclusions from it.
    """
    reader.append("I would like to order a coffee please")
    attempt = await read_aloud(client)
    assert attempt["wer"] > 0.8


# ── PRD R6: the service is off, which is the default ────────────────────────


async def test_with_pron_down_the_reading_keeps_its_transcript_and_says_why(
    client, account, seeded, audio_root, reader, aligner, scorer
):
    """The ordinary state of a fresh clone, and it must not look like a failure.

    `scored`, not `failed`: the reading *was* processed and nothing about it was lost.
    Calling it failed would tell the user their recording is gone when it is on disk and
    one `make pron-up` away from being scored.
    """
    from services.pron_client import PronUnavailable

    aligner.error = PronUnavailable("ConnectError: [Errno 111] Connection refused")

    attempt = await read_aloud(client)
    await scorer.drain()

    detail = (await client.get(f"/attempts/{attempt['id']}")).json()
    assert detail["status"] == "scored"
    assert detail["pronunciation"] == "unavailable"
    assert "not running" in detail["pronunciation_detail"]
    assert detail["transcript"]
    assert detail["wer"] is not None
    assert detail["phonemes"] == []


@pytest.mark.parametrize(
    "error_factory, fragment",
    [
        ("rejected", "could not use this reading"),
        ("protocol", "shape this API does not understand"),
        ("misconfigured", "misconfigured"),
    ],
)
async def test_every_other_way_pron_declines_is_also_a_reason_not_a_500(
    client,
    account,
    seeded,
    audio_root,
    reader,
    aligner,
    scorer,
    error_factory,
    fragment,
):
    """Four failure modes, four log lines, one thing the screen has to say.

    The taxonomy is kept where it is actionable — `services/scoring.py` logs each under
    its own level, and a phone-map gap is an error because the image is wrong — and
    collapsed where it is not. A learner does not need to know which of four ways the
    aligner declined; they need to know there are no phones and that it was not their
    recording's fault.
    """
    from services.pron_client import (
        PronMisconfigured,
        PronProtocolError,
        PronRejected,
    )

    aligner.error = {
        "rejected": PronRejected(
            "the recording is 40 frames but the passage needs 250", 422
        ),
        "protocol": PronProtocolError("unexpected response shape"),
        "misconfigured": PronMisconfigured("phone map gap: unmapped phone 'QQ'"),
    }[error_factory]

    attempt = await read_aloud(client)
    await scorer.drain()

    detail = (await client.get(f"/attempts/{attempt['id']}")).json()
    assert detail["status"] == "scored"
    assert detail["pronunciation"] == "unavailable"
    assert fragment in detail["pronunciation_detail"]


# ── FR-16: rescore ──────────────────────────────────────────────────────────


async def test_a_reading_can_be_scored_again_without_being_read_again(
    client, account, seeded, audio_root, reader, aligner, scorer
):
    """Practise with `pron` down, start it later, rescore what you already have.

    This is what makes a 5 GB profiled service tolerable rather than a wall. The audio is
    on disk — which is exactly why `attempts.audio_asset_id` is NOT NULL — so this costs
    the model's time and asks the user for nothing.
    """
    from services.pron_client import PronUnavailable

    aligner.error = PronUnavailable("nobody home")
    attempt = await read_aloud(client)
    await scorer.drain()
    assert (await client.get(f"/attempts/{attempt['id']}")).json()[
        "pronunciation"
    ] == "unavailable"

    aligner.error = None
    response = await client.post(f"/attempts/{attempt['id']}/rescore")
    assert response.status_code == 200
    await scorer.drain()

    detail = (await client.get(f"/attempts/{attempt['id']}")).json()
    assert detail["pronunciation"] == "ok"
    assert detail["phoneme_count"] == 2
    assert detail["pronunciation_detail"] is None


async def test_rescoring_replaces_the_phones_rather_than_adding_to_them(
    client, account, seeded, audio_root, reader, aligner, scorer, db_session
):
    """Two runs, one set of rows. Otherwise a rescore doubles every aggregate."""
    attempt = await read_aloud(client)
    await scorer.drain()

    await client.post(f"/attempts/{attempt['id']}/rescore")
    await scorer.drain()

    stored = (
        await db_session.scalars(
            select(PhonemeScore).where(PhonemeScore.attempt_id == attempt["id"])
        )
    ).all()
    assert len(stored) == 2


async def test_an_attempt_already_being_scored_is_not_launched_twice(
    client, account, seeded, audio_root, reader, aligner, scorer, db_session
):
    """A double-tapped rescore must not put two jobs on one attempt.

    Both would delete-then-insert, and the second one's delete would race the first one's
    insert. 409 rather than a silent no-op, because the caller asked for something that
    is already happening and should be told so.
    """
    attempt = await read_aloud(client)
    await scorer.drain()

    row = await db_session.get(Attempt, attempt["id"])
    row.status = "scoring"
    await db_session.commit()

    response = await client.post(f"/attempts/{attempt['id']}/rescore")
    assert response.status_code == 409
    assert "being scored" in response.json()["detail"]


async def test_the_job_declines_an_attempt_that_is_not_waiting(
    client, account, seeded, audio_root, reader, aligner, scorer, db_session, db_engine
):
    """The same guard inside the job, where the race actually is.

    The endpoint's 409 is a courtesy; this is the property. `score_attempt` re-reads the
    status inside its own transaction and returns if the attempt is not `pending` or
    `failed`, so two jobs that both got past the endpoint still produce one set of rows.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from services.scoring import score_attempt

    attempt = await read_aloud(client)
    await scorer.drain()
    calls_after_first = aligner.calls

    row = await db_session.get(Attempt, attempt["id"])
    row.status = "scoring"
    await db_session.commit()

    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    await score_attempt(attempt["id"], factory)

    assert aligner.calls == calls_after_first, "the model was called for a running job"


# ── Ownership, and the two conflicting requirements ─────────────────────────


async def test_another_accounts_reading_is_a_404(
    client, other_client, account, seeded, audio_root, reader, aligner, scorer
):
    """404, never 403. A 403 confirms the row exists, which is what a prober wants.

    `attempts` has no `user_id`, so this cannot use `get_owned_or_404` — the join runs
    through `sessions`. That is exactly the shape where an ownership check gets forgotten,
    which is why it has its own test rather than relying on `test_ownership.py`.
    """
    attempt = await read_aloud(client)
    await register_account(other_client)

    assert (await other_client.get(f"/attempts/{attempt['id']}")).status_code == 404
    assert (
        await other_client.post(f"/attempts/{attempt['id']}/rescore")
    ).status_code == 404


async def test_the_list_shows_only_this_accounts_readings(
    client, other_client, account, seeded, audio_root, reader, aligner, scorer
):
    await read_aloud(client)
    await register_account(other_client)

    mine = (await client.get("/attempts")).json()
    theirs = (await other_client.get("/attempts")).json()
    assert mine["total"] == 1
    assert theirs["total"] == 0


async def test_an_account_with_retention_off_is_refused_and_told_which_setting(
    client, account, seeded, audio_root, reader, aligner, scorer
):
    """FR-26 and FR-16 genuinely conflict, and this is the resolution.

    Read-aloud needs the recording to survive the request — `audio_asset_id` is NOT NULL
    so that a reading can be scored again — and an account with retention off has asked
    for exactly the opposite. Quietly storing it anyway would break a promise the user
    made a deliberate choice about, so the endpoint refuses, says why, and names the
    setting and the mode that does work. See handoff Q14.
    """
    await client.patch("/auth/me", json={"retain_audio": False})

    response = await client.post(
        "/attempts",
        files={"file": ("reading.wav", silent_wav(3400), "audio/wav")},
        data={"passage_slug": PASSAGE},
    )
    assert response.status_code == 409
    body = response.json()["detail"]
    assert "retention" in body and "settings" in body
    assert "conversation practice" in body


# ── The passage and the session ─────────────────────────────────────────────


async def test_an_unknown_passage_is_a_404(client, account, seeded, audio_root, reader):
    response = await client.post(
        "/attempts",
        files={"file": ("reading.wav", silent_wav(1000), "audio/wav")},
        data={"passage_slug": "no-such-passage"},
    )
    assert response.status_code == 404


async def test_readings_join_a_sitting_when_one_is_named(
    client, account, seeded, audio_root, reader, aligner, scorer
):
    """Two readings, one read-aloud session. The sitting is what m10 aggregates over."""
    first = await read_aloud(client)
    second = await read_aloud(client, session_id=first["session_id"])
    assert second["session_id"] == first["session_id"]


async def test_a_reading_cannot_be_filed_under_a_conversation(
    client, account, seeded, audio_root, reader, aligner, scorer, provider, voice
):
    """A conversation session has a persona and turns; it is not a place for attempts.

    `provider` and `voice` are here because opening a conversation session generates and
    speaks an opening line — the one place in this file that needs m6's stubs at all.
    """
    created = await client.post(
        "/sessions", json={"scenario_slug": "job-interview-backend"}
    )
    assert created.status_code == 201

    response = await client.post(
        "/attempts",
        files={"file": ("reading.wav", silent_wav(1000), "audio/wav")},
        data={"passage_slug": PASSAGE, "session_id": str(created.json()["id"])},
    )
    assert response.status_code == 409
    assert "conversation" in response.json()["detail"]


async def test_the_list_can_be_filtered_to_one_sitting(
    client, account, seeded, audio_root, reader, aligner, scorer
):
    """What `/sessions/{id}` reads for a read-aloud sitting.

    Added after using the product: a read-aloud session appeared in History, opened the
    conversation screen, and offered a record button whose only possible outcome was a 409.
    The page now branches on `mode` and needs the sitting's readings, which needs this
    filter. Every unit test in this file built a conversation until m8, because until m8
    there was no other kind of session — which is exactly why nothing caught it.
    """
    first = await read_aloud(client)
    await read_aloud(client, session_id=first["session_id"])
    await read_aloud(client)  # a second sitting, which must not appear

    page = (await client.get(f"/attempts?session_id={first['session_id']}")).json()
    assert page["total"] == 2
    assert {item["session_id"] for item in page["items"]} == {first["session_id"]}


async def test_another_accounts_sitting_returns_an_empty_page_not_a_403(
    client, other_client, account, seeded, audio_root, reader, aligner, scorer
):
    """An unowned id is filtered, not refused.

    The filter is applied inside the same `owned` subquery as everything else, so a
    stranger's session id returns nothing rather than a 403 — which would confirm the
    sitting exists, the fact `dependencies.py` refuses to hand back.
    """
    mine = await read_aloud(client)
    await register_account(other_client)

    page = (await other_client.get(f"/attempts?session_id={mine['session_id']}")).json()
    assert page["total"] == 0


async def test_the_list_can_be_filtered_to_one_passage(
    client, account, seeded, audio_root, reader, aligner, scorer
):
    await read_aloud(client, PASSAGE)
    await read_aloud(client, "the-ship-and-the-sheep")

    filtered = (await client.get(f"/attempts?passage_slug={PASSAGE}")).json()
    assert filtered["total"] == 1
    assert filtered["items"][0]["passage_slug"] == PASSAGE
