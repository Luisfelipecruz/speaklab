"""Rehearsing a script end to end: saving one, taking it, and what a take says.

The through-line: **a take is useful with nothing but a recogniser.** The pronunciation
service is profiled and off by default, and a section can contain a word no converter can
turn into phones; in both cases the take still has the script compared word by word, the
timings counted, and a sentence saying why there are no sounds. A take that 500s or comes
back empty in either case would make the feature look broken to everyone who had not read
the Makefile.

The other half: nothing here is a mark, and nothing here reaches the progress snapshots.
A script somebody wrote and rehearsed forty times is practice, and the trends are built
from conversation and from passages every speaker reads.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from db_models import AudioAsset, Presentation, Rehearsal, RehearsalPhone
from config import REHEARSAL_SOUNDS_SHOWN
from models.common import ARPABET_PHONES
from models.presentation import SectionOut, TakeSummary
from services import rehearsals
from services.pron_client import PronUnavailable
from services.wer import wer
from tests.conftest import register_account, silent_wav

OPENING = (
    "Good morning. I am glad you came. Today I want to talk about what we shipped."
)
NUMBERS = "First the numbers. We grew last year. The team is smaller than it was."
SCRIPT = f"{OPENING}\n\n{NUMBERS}"


async def save(client: AsyncClient, script: str = SCRIPT, **fields) -> dict:
    response = await client.post(
        "/presentations", json={"title": "A talk", "script": script, **fields}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def record(
    client: AsyncClient, presentation_id: int, idx: int = 0, ms: int = 3400
) -> AsyncClient.post:
    return await client.post(
        f"/presentations/{presentation_id}/sections/{idx}/takes",
        files={"file": ("take.wav", silent_wav(ms), "audio/wav")},
    )


async def take_ok(client: AsyncClient, presentation_id: int, idx: int = 0) -> dict:
    response = await record(client, presentation_id, idx)
    assert response.status_code == 201, response.text
    return response.json()


def _assets_of(account: dict):
    """Recordings belonging to this account. Counted per user: the suite shares a database."""
    return (
        select(func.count())
        .select_from(AudioAsset)
        .where(AudioAsset.user_id == account["id"])
    )


def _files_under(root) -> list:
    """Stored recordings have no extension — the container format is a column."""
    return [path for path in root.rglob("*") if path.is_file()]


# ── Saving a script ─────────────────────────────────────────────────────────


async def test_a_pasted_script_is_split_where_the_writer_split_it(
    client, account, phonemizer
):
    saved = await save(client)

    assert [section["idx"] for section in saved["sections"]] == [0, 1]
    assert saved["sections"][0]["body"] == OPENING
    assert saved["word_count"] == len(SCRIPT.split())
    assert sum(s["word_count"] for s in saved["sections"]) == saved["word_count"]


async def test_the_words_that_cannot_be_scored_are_named_under_their_own_section(
    client, account, phonemizer
):
    """Named at the moment the script is saved, before anybody has recorded anything.

    The person who can fix it is the one who wrote it, and the fix — spelling a figure
    the way it is said — is one they make in the script rather than in a recording.
    """
    phonemizer.names = ["2026"]
    saved = await save(
        client, script=f"{OPENING}\n\nWe shipped it in 2026. It works well now."
    )

    assert saved["sections"][0]["scorable"] is True
    assert saved["sections"][0]["unscorable_words"] == []
    assert saved["sections"][1]["scorable"] is False
    assert saved["sections"][1]["unscorable_words"] == ["2026"]


async def test_a_script_longer_than_a_script_may_be_says_how_long_it_is(
    client, account, phonemizer
):
    response = await client.post(
        "/presentations",
        json={"title": "Too much", "script": " ".join(["word"] * 3001)},
    )

    assert response.status_code == 422
    assert "3001" in response.json()["detail"]


async def test_sections_that_do_not_add_up_to_the_script_are_refused(
    client, account, phonemizer
):
    """A boundary moved is fine; a word changed is a script that says something else.

    Every count afterwards is against the section text. Sections that quietly disagreed
    with the stored script would compare a take with words the talk does not contain.
    """
    response = await client.post(
        "/presentations",
        json={
            "title": "Edited",
            "script": SCRIPT,
            "sections": [OPENING, NUMBERS.replace("smaller", "larger")],
        },
    )

    assert response.status_code == 422
    assert "do not add up" in response.json()["detail"]


async def test_the_writers_own_boundaries_are_kept(client, account, phonemizer):
    saved = await save(
        client,
        sections=[
            "Good morning. I am glad you came.",
            f"Today I want to talk about what we shipped. {NUMBERS}",
        ],
    )

    assert [s["word_count"] for s in saved["sections"]] == [7, 23]


async def test_a_preview_says_the_check_did_not_happen_when_the_scorer_is_down(
    client, account, phonemizer
):
    """Not running is not the same as fine, and the page must be able to say which.

    A section marked unscorable because nobody answered would never be scored again; one
    marked scorable silently would fail at every take with no reason a reader can act on.
    """
    phonemizer.error = PronUnavailable("nobody answered")

    response = await client.post(
        "/presentations/preview", json={"title": "A talk", "script": SCRIPT}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["pron"] == "unavailable"
    assert body["unscorable"] == [[], []]
    assert body["word_counts"] == [len(OPENING.split()), len(NUMBERS.split())]


async def test_a_script_saved_while_the_scorer_is_down_is_saved_scorable(
    client, account, phonemizer
):
    phonemizer.error = PronUnavailable("nobody answered")

    saved = await save(client)

    assert all(section["scorable"] for section in saved["sections"])
    assert all(section["unscorable_words"] == [] for section in saved["sections"])


# ── One take ────────────────────────────────────────────────────────────────


async def test_a_take_is_compared_with_the_section_word_by_word(
    client, account, audio_root, reader, aligner, rehearsal_scorer, phonemizer
):
    """The rate is the same arithmetic a reading is scored with, over the section text."""
    saved = await save(client)
    heard = "Good morning I am glad you came today I want to talk about what we shipped"
    reader.append(heard)

    take = await take_ok(client, saved["id"])

    assert take["wer"] == pytest.approx(wer(OPENING, heard).rate)
    assert take["fidelity"]["reference_words"] == len(OPENING.split())
    assert take["transcript"] == heard
    assert take["delivery"]["words"] == len(heard.split())


async def test_the_alignment_marks_what_was_missed_and_what_was_said_instead(
    client, account, audio_root, reader, aligner, rehearsal_scorer, phonemizer
):
    saved = await save(client)
    # "glad" said as "sad", and "came" not said at all.
    reader.append(
        "Good morning I am sad you today I want to talk about what we shipped"
    )

    take = await take_ok(client, saved["id"])

    kinds = {
        word["expected"]: word["kind"]
        for word in take["fidelity"]["words"]
        if word["expected"]
    }
    assert kinds["glad"] == "substitution"
    assert kinds["came"] == "deletion"
    assert take["fidelity"]["substitutions"] == 1
    assert take["fidelity"]["deletions"] == 1


async def test_a_take_says_pending_until_its_sounds_have_been_scored(
    client, account, audio_root, reader, aligner, rehearsal_scorer, phonemizer
):
    saved = await save(client)

    take = await take_ok(client, saved["id"])

    assert take["pronunciation"] == "pending"
    assert take["phonemes"] == []
    assert take["summary"] is None


async def test_the_job_stores_a_phone_per_row_and_the_take_reads_them_back(
    client, account, audio_root, reader, aligner, rehearsal_scorer, phonemizer
):
    saved = await save(client)
    take = await take_ok(client, saved["id"])

    await rehearsal_scorer.drain()

    detail = (await client.get(f"/presentations/takes/{take['id']}")).json()
    assert detail["pronunciation"] == "ok"
    assert [p["canonical_phone"] for p in detail["phonemes"]] == ["DH", "TH"]
    assert detail["summary"]["phones"] == 2
    assert detail["median_gop"] is not None


async def test_the_scorer_is_given_the_section_text_and_the_recording(
    client, account, audio_root, reader, aligner, rehearsal_scorer, phonemizer
):
    """Scoring the wrong words against this recording would produce plausible nonsense."""
    saved = await save(client)
    await take_ok(client, saved["id"], idx=1)

    assert rehearsal_scorer.launched[0][2] == NUMBERS
    assert rehearsal_scorer.launched[0][1].startswith(b"RIFF")

    await rehearsal_scorer.drain()
    assert aligner.texts == [NUMBERS]


async def test_a_scorer_that_is_not_running_leaves_the_take_counted(
    client, account, audio_root, reader, aligner, rehearsal_scorer, phonemizer
):
    """The default state of a fresh clone. The take keeps everything but its sounds."""
    saved = await save(client)
    take = await take_ok(client, saved["id"])
    aligner.error = PronUnavailable("profile never started")

    await rehearsal_scorer.drain()

    detail = (await client.get(f"/presentations/takes/{take['id']}")).json()
    assert detail["pronunciation"] == "unavailable"
    assert "not running" in detail["pronunciation_detail"]
    assert detail["fidelity"]["reference_words"] > 0
    assert detail["delivery"]["words"] > 0


async def test_a_section_with_an_unscorable_word_is_never_sent_to_the_scorer(
    client, account, audio_root, reader, aligner, rehearsal_scorer, phonemizer
):
    """Asking would earn a refusal the take cannot act on, so the reason is on the row.

    The words are named in it, with what to do about them: the writer respells the
    figure, and the section becomes scorable for every take after that.
    """
    phonemizer.names = ["2026"]
    saved = await save(
        client, script=f"{OPENING}\n\nWe shipped it in 2026. It works well now."
    )

    take = await take_ok(client, saved["id"], idx=1)

    assert take["pronunciation"] == "unscorable"
    assert "2026" in take["pronunciation_detail"]
    assert rehearsal_scorer.launched == []
    assert take["fidelity"]["reference_words"] > 0


# ── The recording, and whether it is kept ───────────────────────────────────


async def test_a_take_on_an_account_that_keeps_audio_can_be_played_back(
    client,
    account,
    audio_root,
    reader,
    aligner,
    rehearsal_scorer,
    phonemizer,
    db_session,
):
    saved = await save(client)

    take = await take_ok(client, saved["id"])

    assert take["audio_url"].startswith("/audio/")
    assert await db_session.scalar(_assets_of(account)) == 1
    assert (await client.get(take["audio_url"])).status_code == 200


async def test_a_take_on_an_account_that_keeps_none_is_scored_and_not_stored(
    client,
    account,
    audio_root,
    reader,
    aligner,
    rehearsal_scorer,
    phonemizer,
    db_session,
):
    """The whole cost of retention being off is the replay.

    Read-aloud refuses without retention because a reading can be scored again later and
    that needs the waveform. A take is scored once, from the bytes in the request, so
    refusing it would take the feature away for no gain.
    """
    await client.patch("/auth/me", json={"retain_audio": False})
    saved = await save(client)

    take = await take_ok(client, saved["id"])
    await rehearsal_scorer.drain()

    assert take["audio_url"] is None
    assert await db_session.scalar(_assets_of(account)) == 0
    assert not _files_under(audio_root)

    detail = (await client.get(f"/presentations/takes/{take['id']}")).json()
    assert detail["pronunciation"] == "ok"
    assert detail["phonemes"]


# ── What is refused ─────────────────────────────────────────────────────────


async def test_a_recording_with_nothing_in_it_is_refused_rather_than_compared(
    client, account, audio_root, reader, aligner, rehearsal_scorer, phonemizer
):
    saved = await save(client)
    reader.append("")

    response = await record(client, saved["id"])

    assert response.status_code == 422
    assert "Nothing was heard" in response.json()["detail"]


async def test_a_recording_over_the_limit_is_refused_before_it_is_heard(
    client, account, audio_root, reader, rehearsal_scorer, phonemizer, monkeypatch
):
    from routers import presentations as presentations_router

    saved = await save(client)
    monkeypatch.setattr(presentations_router, "MAX_UPLOAD_BYTES", 5)
    reader.append("never heard")

    response = await record(client, saved["id"])

    assert response.status_code == 413
    assert reader == ["never heard"]


async def test_a_section_that_is_not_there_is_a_404(client, account, phonemizer):
    saved = await save(client)

    response = await record(client, saved["id"], idx=9)

    assert response.status_code == 404


# ── The target time ─────────────────────────────────────────────────────────


async def test_a_target_is_set_and_a_later_take_is_over_or_under_it(
    client, account, audio_root, reader, aligner, rehearsal_scorer, phonemizer
):
    saved = await save(client)
    section_id = saved["sections"][0]["id"]

    patched = await client.patch(
        f"/presentations/{saved['id']}/sections/0", json={"target_seconds": 60}
    )
    assert patched.status_code == 200
    assert patched.json()["target_seconds"] == 60
    assert patched.json()["id"] == section_id

    reader.append("Good morning")  # two words, so the stub's audio is short
    take = await take_ok(client, saved["id"])

    assert take["target_seconds"] == 60
    assert take["pace"] == "under"


async def test_a_take_with_no_target_is_not_judged_against_one(
    client, account, audio_root, reader, aligner, rehearsal_scorer, phonemizer
):
    saved = await save(client)

    take = await take_ok(client, saved["id"])

    assert take["target_seconds"] is None
    assert take["pace"] is None


@pytest.mark.parametrize("seconds", [0, 601])
async def test_a_target_outside_the_range_a_section_can_have_is_refused(
    client, account, phonemizer, seconds
):
    saved = await save(client)

    response = await client.patch(
        f"/presentations/{saved['id']}/sections/0", json={"target_seconds": seconds}
    )

    assert response.status_code == 422


# ── The page, and the list ──────────────────────────────────────────────────


async def test_the_page_carries_each_sections_latest_take_and_its_count(
    client, account, audio_root, reader, aligner, rehearsal_scorer, phonemizer
):
    saved = await save(client)
    await take_ok(client, saved["id"])
    await take_ok(client, saved["id"])

    page = (await client.get(f"/presentations/{saved['id']}")).json()

    first, second = page["presentation"]["sections"]
    assert first["takes"] == 2
    assert first["latest"]["id"] > 0
    assert second["takes"] == 0
    assert second["latest"] is None


async def test_the_page_names_the_section_to_say_again_and_what_it_counted(
    client, account, audio_root, reader, aligner, rehearsal_scorer, phonemizer
):
    saved = await save(client)
    reader.append("Good morning I am glad")  # most of the section not said

    await take_ok(client, saved["id"])
    page = (await client.get(f"/presentations/{saved['id']}")).json()

    fidelity = next(item for item in page["next_up"] if item["kind"] == "fidelity")
    assert fidelity["reason"].endswith(
        f"of {len(OPENING.split())} words missed or changed in the last take"
    )
    assert fidelity["section_id"] == saved["sections"][0]["id"]


async def test_a_script_with_no_takes_has_nothing_to_say_next(
    client, account, phonemizer
):
    saved = await save(client)

    page = (await client.get(f"/presentations/{saved['id']}")).json()

    assert page["next_up"] == []


async def test_the_list_carries_the_counts_and_the_most_recent_first(
    client, account, audio_root, reader, aligner, rehearsal_scorer, phonemizer
):
    first = await save(client)
    await save(client, script="Another talk entirely. It is short.")
    await take_ok(client, first["id"])

    listing = (await client.get("/presentations")).json()

    assert listing["total"] == 2
    assert listing["items"][0]["id"] == first["id"]
    assert listing["items"][0]["takes"] == 1
    assert listing["items"][0]["sections"] == 2
    assert listing["items"][1]["takes"] == 0


async def test_the_takes_of_a_section_come_back_newest_first(
    client, account, audio_root, reader, aligner, rehearsal_scorer, phonemizer
):
    saved = await save(client)
    older = await take_ok(client, saved["id"])
    newer = await take_ok(client, saved["id"])

    listed = (await client.get(f"/presentations/{saved['id']}/sections/0/takes")).json()

    assert [take["id"] for take in listed["items"]] == [newer["id"], older["id"]]


# ── Somebody else's script ──────────────────────────────────────────────────


async def test_another_accounts_script_is_a_404_on_every_operation(
    client, account, other_client, audio_root, reader, phonemizer
):
    """404 rather than 403: whether a script exists is not theirs to learn either."""
    saved = await save(client)
    await register_account(other_client)

    assert (await other_client.get(f"/presentations/{saved['id']}")).status_code == 404
    assert (
        await other_client.patch(
            f"/presentations/{saved['id']}/sections/0", json={"target_seconds": 30}
        )
    ).status_code == 404
    assert (
        await other_client.delete(f"/presentations/{saved['id']}")
    ).status_code == 404
    assert (await record(other_client, saved["id"])).status_code == 404


async def test_another_accounts_take_is_a_404(
    client,
    account,
    other_client,
    audio_root,
    reader,
    aligner,
    rehearsal_scorer,
    phonemizer,
):
    saved = await save(client)
    take = await take_ok(client, saved["id"])
    await register_account(other_client)

    response = await other_client.get(f"/presentations/takes/{take['id']}")

    assert response.status_code == 404


# ── Deleting one ────────────────────────────────────────────────────────────


async def test_deleting_a_script_takes_its_takes_its_phones_and_its_audio(
    client,
    account,
    audio_root,
    reader,
    aligner,
    rehearsal_scorer,
    phonemizer,
    db_session,
):
    """Delete that leaves the recordings behind is a promise this project does not make."""
    saved = await save(client)
    take = await take_ok(client, saved["id"])
    await rehearsal_scorer.drain()

    files = _files_under(audio_root)
    assert files

    response = await client.delete(f"/presentations/{saved['id']}")

    assert response.status_code == 204
    assert (await client.get(f"/presentations/{saved['id']}")).status_code == 404
    assert await db_session.get(Presentation, saved["id"]) is None
    assert await db_session.get(Rehearsal, take["id"]) is None
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(RehearsalPhone)
            .where(RehearsalPhone.rehearsal_id == take["id"])
        )
        == 0
    )
    assert await db_session.scalar(_assets_of(account)) == 0
    assert not [path for path in files if path.exists()]


# ── What to rehearse next, on its own ───────────────────────────────────────


def section(idx: int, **fields) -> SectionOut:
    latest = fields.pop("latest", None)
    return SectionOut(
        id=idx + 1,
        idx=idx,
        body="body",
        word_count=fields.pop("word_count", 80),
        target_seconds=fields.pop("target_seconds", None),
        takes=1 if latest else 0,
        latest=latest,
        **fields,
    )


def latest_take(section_id: int, **fields) -> TakeSummary:
    return TakeSummary(
        id=section_id * 10,
        section_id=section_id,
        created_at="2026-01-01T00:00:00Z",
        wer=fields.pop("wer", 0.0),
        pron_status="scored",
        **fields,
    )


def test_nothing_is_named_when_nothing_has_been_measured():
    assert rehearsals.next_up([section(0)], [], {}) == []


def test_a_take_that_said_the_section_is_not_worth_naming():
    """Under one word in ten missed is inside what a recogniser gets wrong by itself."""
    sections = [section(0, latest=latest_take(1, wer=0.05, missed=4))]

    assert rehearsals.next_up(sections, [], {}) == []


def test_the_section_furthest_from_its_script_is_named_with_its_count():
    sections = [
        section(0, latest=latest_take(1, wer=0.12, missed=9)),
        section(1, latest=latest_take(2, wer=0.40, missed=32)),
    ]

    items = rehearsals.next_up(sections, [], {})

    assert items[0].kind == "fidelity"
    assert items[0].title == "Section 2"
    assert items[0].reason == "32 of 80 words missed or changed in the last take"
    assert items[0].section_id == 2


def test_the_sound_named_is_the_lowest_one_measured_often_enough():
    """Two takes and five instances, the same floor the progress page uses.

    A phone scored once in one take is a reading of one word on one day, and naming it
    would send somebody to practise a sound on the strength of a single segment.
    """
    means = [("TH", -8.2, 12, 3), ("S", -0.4, 40, 4), ("ZH", -9.9, 2, 1)]

    items = rehearsals.next_up([section(0)], means, {})

    assert [item.kind for item in items] == ["sound"]
    # Named in words rather than in code: /TH/ is what the model thinks in and is not
    # something the person who recorded the take can act on.
    assert items[0].title == 'the "th" in "think"'
    assert items[0].reason == "12 instances across 3 takes, mean score -8.2"


def test_a_section_over_its_target_is_named_with_both_times():
    sections = [
        section(
            0,
            target_seconds=60,
            latest=latest_take(1, wer=0.0, duration_ms=95_000),
        )
    ]

    items = rehearsals.next_up(sections, [], {})

    assert [item.kind for item in items] == ["pace"]
    assert items[0].reason == "1:35 against a target of 1:00"


def test_a_section_a_little_over_its_target_is_not_named():
    """Reading the same words twice varies by more than a second."""
    sections = [
        section(
            0,
            target_seconds=60,
            latest=latest_take(1, wer=0.0, duration_ms=64_000),
        )
    ]

    assert rehearsals.next_up(sections, [], {}) == []


def test_the_filler_named_is_the_commonest_one_said_often_enough():
    items = rehearsals.next_up([section(0)], [], {"um": (7, 3), "like": (2, 1)})

    assert [item.kind for item in items] == ["filler"]
    assert items[0].reason == "'um' 7 times in 3 takes"


def test_two_fillers_in_one_take_are_not_worth_naming():
    assert rehearsals.next_up([section(0)], [], {"um": (2, 1)}) == []


def test_each_kind_is_named_once_and_in_one_order():
    sections = [
        section(
            0,
            target_seconds=60,
            latest=latest_take(1, wer=0.30, missed=24, duration_ms=95_000),
        ),
        section(1, latest=latest_take(2, wer=0.20, missed=16, duration_ms=10_000)),
    ]

    items = rehearsals.next_up(
        sections,
        [("TH", -8.2, 12, 3)],
        {"um": (7, 3)},
    )

    assert [item.kind for item in items] == ["fidelity", "sound", "pace", "filler"]


# ── The alignment, on its own ───────────────────────────────────────────────


def heard(text: str, logprobs: list[float] | None = None):
    """A transcription of `text`, with a confidence per word."""
    from models.audio import DecoderSettings, SourceMedia, Transcription, Word

    tokens = text.split()
    scores = logprobs or [-0.2] * len(tokens)
    return Transcription(
        text=text,
        words=[
            Word(w=token, start_ms=i * 400, end_ms=i * 400 + 350, logprob=scores[i])
            for i, token in enumerate(tokens)
        ],
        confidence=0.95,
        timestamp_fixups=0,
        language="en",
        model="stub-whisper",
        decoder=DecoderSettings(beam_size=5, vad_filter=True, compute_type="int8"),
        source=SourceMedia(
            format="wav",
            codec="pcm_s16le",
            sample_rate=16000,
            channels=1,
            duration_ms=max(400, len(tokens) * 400),
        ),
        latency_ms=12,
    )


def test_a_word_the_recogniser_doubted_is_marked_rather_than_blamed():
    """The likeliest place for a difference that is the microphone's, not the speaker's.

    Marked and counted, never dropped: a word removed from the comparison because the
    recogniser was unsure of it would quietly improve the rate on the noisiest takes.
    """
    alignment = rehearsals.alignment_of(
        "the cat sat", heard("the cat sat", [-0.2, -3.0, -0.2])
    )

    assert [word["unsure"] for word in alignment["words"]] == [False, True, False]
    assert alignment["unsure_words"] == 1


def test_confidence_that_cannot_be_attached_is_said_rather_than_reported_as_none():
    """A word the recogniser wrote with punctuation in it makes the two lists disagree.

    Reporting zero uncertain words there would be a confident claim about something that
    was not checked, so the count says the check could not be made instead.
    """
    alignment = rehearsals.alignment_of("twenty five cats", heard("twenty-five cats"))

    assert alignment["unsure_words"] == rehearsals.UNSURE_UNKNOWN
    assert all(word["unsure"] is False for word in alignment["words"])


def test_a_word_said_that_is_not_in_the_script_is_an_insertion():
    alignment = rehearsals.alignment_of("the cat sat", heard("the big cat sat"))

    kinds = [(word["kind"], word["heard"]) for word in alignment["words"]]
    assert ("insertion", "big") in kinds
    assert alignment["insertions"] == 1
    assert alignment["reference_words"] == 3


# ── The sounds a script names ───────────────────────────────────────────────


def test_the_sounds_are_named_weakest_first_with_the_speakers_own_words():
    """What the script page offers to work on, in the order it offers it.

    The five the owner's four takes actually produced, with their measured means, so the
    ordering is tested against a real profile rather than an invented one.
    """
    means = [
        ("IY", -3.79, 15, 4),
        ("DH", -3.43, 16, 4),
        ("NG", -3.29, 6, 3),
        ("Z", -2.72, 14, 4),
        ("ER", -2.67, 19, 4),
    ]
    words = {"IY": ["peels", "these", "we"], "DH": ["the", "this"]}

    found = rehearsals.sounds_of(means, words)

    assert [sound.phone for sound in found] == ["IY", "DH", "NG", "Z", "ER"]
    assert found[0].name == 'the vowel in "see"'
    assert found[0].words == ["peels", "these", "we"]
    assert found[0].instances == 15
    assert found[0].takes == 4
    assert found[0].mean_gop == -3.79
    assert found[2].words == []


def test_a_sound_heard_once_or_in_one_take_is_not_offered():
    means = [("ZH", -9.9, 2, 1), ("TH", -8.2, 12, 1), ("S", -0.4, 40, 4)]

    found = rehearsals.sounds_of(means, {})

    assert [sound.phone for sound in found] == ["S"]


def test_only_a_handful_of_sounds_are_offered_at_once():
    means = [
        (phone, -float(index), 10, 3) for index, phone in enumerate(ARPABET_PHONES)
    ]

    found = rehearsals.sounds_of(means, {})

    assert len(found) == REHEARSAL_SOUNDS_SHOWN
    assert [sound.phone for sound in found] == list(ARPABET_PHONES[-1:-6:-1])
