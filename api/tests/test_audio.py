"""Storing a recording, and serving it back to exactly one person.

The endpoint is four lines long and every one of them is a check, so the tests here
outnumber the code by some margin. That is the right ratio for it: `GET /audio/41` is a
URL anybody can type, and the only thing between a stranger and somebody's voice is
`get_owned_or_404`.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db_models import AudioAsset, User
from models.audio import SourceMedia
from services.audio import AudioPathError, resolve_path, sha256_of, store_recording
from tests.conftest import register_account, unique_email

# A WAV header followed by nothing. These tests never decode it — decoding is the asr
# service's job and `test_asr_golden.py` is where real audio goes through a real model.
# What is under test here is storage, ownership and path safety, none of which look at
# the bytes.
RECORDING = b"RIFF$\x00\x00\x00WAVEfmt " + bytes(range(64))

SOURCE = SourceMedia(
    format="wav", codec="pcm_s16le", sample_rate=16000, channels=1, duration_ms=4000
)


async def a_user(db: AsyncSession, client: AsyncClient) -> User:
    """A registered account, as the ORM object the service layer takes."""
    profile = await register_account(client, email=unique_email("audio"))
    user = await db.scalar(select(User).where(User.id == profile["id"]))
    assert user is not None
    return user


# ── Storage ─────────────────────────────────────────────────────────────────


async def test_a_recording_is_stored_under_the_digest_of_its_own_bytes(
    audio_root, client, db_session
):
    user = await a_user(db_session, client)
    asset, created = await store_recording(db_session, user, RECORDING, SOURCE)
    await db_session.commit()

    assert created is True
    assert asset.sha256 == sha256_of(RECORDING)
    stored = audio_root / str(user.id) / asset.sha256
    assert stored.read_bytes() == RECORDING
    # Content-addressed means the name carries no user input at all: 64 hex characters,
    # so there is no separator, no `..` and nothing to escape.
    assert stored.name.isalnum() and len(stored.name) == 64


async def test_the_row_records_what_the_decoder_measured(
    audio_root, client, db_session
):
    """Not what the uploader claimed. The API cannot open an audio file at all."""
    user = await a_user(db_session, client)
    asset, _ = await store_recording(db_session, user, RECORDING, SOURCE)

    assert (asset.duration_ms, asset.sample_rate, asset.format) == (4000, 16000, "wav")


async def test_the_same_bytes_from_the_same_user_do_not_become_two_recordings(
    audio_root, client, db_session
):
    """The double-tap case, and the retry-after-timeout case. One row, not two."""
    user = await a_user(db_session, client)
    first, created_first = await store_recording(db_session, user, RECORDING, SOURCE)
    await db_session.commit()
    second, created_second = await store_recording(db_session, user, RECORDING, SOURCE)
    await db_session.commit()

    assert (created_first, created_second) == (True, False)
    assert first.id == second.id

    rows = await db_session.scalars(
        select(AudioAsset).where(AudioAsset.user_id == user.id)
    )
    assert len(list(rows)) == 1


async def test_the_same_bytes_from_two_users_are_two_recordings(
    audio_root, client, other_client, db_session
):
    """Uniqueness is scoped to the user, not global.

    Two people reading the same passage are two attempts. Deduplicating across accounts
    would also mean one person's row pointing at a file another person uploaded, which
    is a deletion request that cannot be honoured.
    """
    one = await a_user(db_session, client)
    two = await a_user(db_session, other_client)

    first, _ = await store_recording(db_session, one, RECORDING, SOURCE)
    await db_session.commit()
    second, created = await store_recording(db_session, two, RECORDING, SOURCE)
    await db_session.commit()

    assert created is True
    assert first.id != second.id
    assert first.sha256 == second.sha256


async def test_a_second_write_of_identical_bytes_does_not_rewrite_the_file(
    audio_root, client, db_session
):
    user = await a_user(db_session, client)
    asset, _ = await store_recording(db_session, user, RECORDING, SOURCE)
    await db_session.commit()
    stored = audio_root / str(user.id) / asset.sha256
    written_at = stored.stat().st_mtime_ns

    await store_recording(db_session, user, RECORDING, SOURCE)
    await db_session.commit()

    assert stored.stat().st_mtime_ns == written_at


async def test_no_partial_file_is_left_behind(audio_root, client, db_session):
    """The write goes to a neighbour and is moved into place.

    A reader must never observe a half-written recording, so the only thing that can
    appear at the final name is a complete file.
    """
    user = await a_user(db_session, client)
    await store_recording(db_session, user, RECORDING, SOURCE)

    assert list((audio_root / str(user.id)).glob(".*partial")) == []


# ── Path safety ─────────────────────────────────────────────────────────────


async def test_a_path_outside_the_audio_volume_is_refused(
    audio_root, client, db_session
):
    """Nothing in this codebase can write such a row. The check is for when something else does."""
    user = await a_user(db_session, client)
    asset, _ = await store_recording(db_session, user, RECORDING, SOURCE)
    asset.path = "/etc/passwd"

    with pytest.raises(AudioPathError):
        resolve_path(asset)


async def test_a_symlink_out_of_the_volume_is_refused(
    audio_root, client, db_session, tmp_path
):
    """The case a string-prefix check misses.

    `/audio/7/dead…beef` starts with `/audio` whether or not it is a link to somewhere
    else entirely, which is why containment is decided after `resolve()`.
    """
    outside = tmp_path.parent / "outside-the-volume"
    outside.write_bytes(b"not a recording")

    user = await a_user(db_session, client)
    asset, _ = await store_recording(db_session, user, RECORDING, SOURCE)
    stored = audio_root / str(user.id) / asset.sha256
    stored.unlink()
    stored.symlink_to(outside)

    with pytest.raises(AudioPathError):
        resolve_path(asset)


# ── GET /audio/{asset_id} ───────────────────────────────────────────────────


async def test_the_owner_gets_their_recording_back(audio_root, client, db_session):
    user = await a_user(db_session, client)
    asset, _ = await store_recording(db_session, user, RECORDING, SOURCE)
    await db_session.commit()

    response = await client.get(f"/audio/{asset.id}")

    assert response.status_code == 200
    assert response.content == RECORDING
    assert response.headers["content-type"].startswith("audio/wav")


async def test_another_account_gets_404_not_403(
    audio_root, client, other_client, db_session
):
    """A 403 would confirm the recording exists, which is the fact being probed for (D25)."""
    owner = await a_user(db_session, client)
    await a_user(db_session, other_client)
    asset, _ = await store_recording(db_session, owner, RECORDING, SOURCE)
    await db_session.commit()

    response = await other_client.get(f"/audio/{asset.id}")

    assert response.status_code == 404
    # And the body says nothing the guesser did not already supply.
    assert str(owner.id) not in response.text


async def test_an_id_that_was_never_issued_looks_exactly_like_one_that_belongs_to_someone_else(
    audio_root, client, other_client, db_session
):
    """The whole point of 404-not-403, stated as an equality rather than as prose."""
    owner = await a_user(db_session, client)
    await a_user(db_session, other_client)
    asset, _ = await store_recording(db_session, owner, RECORDING, SOURCE)
    await db_session.commit()

    someone_elses = await other_client.get(f"/audio/{asset.id}")
    never_issued = await other_client.get("/audio/99999999")

    assert someone_elses.status_code == never_issued.status_code == 404
    assert someone_elses.json()["detail"] == never_issued.json()["detail"].replace(
        "99999999", str(asset.id)
    )


async def test_an_anonymous_request_is_401(audio_root, client, db_session):
    user = await a_user(db_session, client)
    asset, _ = await store_recording(db_session, user, RECORDING, SOURCE)
    await db_session.commit()
    client.cookies.clear()

    response = await client.get(f"/audio/{asset.id}")

    assert response.status_code == 401


async def test_a_row_whose_file_was_deleted_is_404_and_the_row_survives(
    audio_root, client, db_session
):
    """FR-26: retention off means the waveform goes and the derived numbers stay.

    So this is a normal state, not corruption — and the row must not be deleted to
    produce it, because every metric computed from that recording still references it.
    """
    user = await a_user(db_session, client)
    asset, _ = await store_recording(db_session, user, RECORDING, SOURCE)
    await db_session.commit()
    (audio_root / str(user.id) / asset.sha256).unlink()

    response = await client.get(f"/audio/{asset.id}")

    assert response.status_code == 404
    assert await db_session.get(AudioAsset, asset.id) is not None


async def test_the_response_never_carries_the_stored_path(
    audio_root, client, db_session
):
    """A location on a volume the browser cannot reach, and has no reason to know."""
    user = await a_user(db_session, client)
    asset, _ = await store_recording(db_session, user, RECORDING, SOURCE)
    await db_session.commit()

    response = await client.get(f"/audio/{asset.id}")

    assert str(audio_root) not in response.headers.get("content-disposition", "")
    assert str(audio_root).encode() not in response.content


# ── The pipeline ────────────────────────────────────────────────────────────


async def test_an_oversized_upload_is_refused_before_the_model_is_called(
    audio_root, client, db_session, monkeypatch
):
    """The check is in `ingest_recording`, above the ASR call, so a 40 MB upload costs
    nothing but the bytes already received. A `transcribe` that raises proves the order:
    if the size check ran second, this test would fail with the wrong exception."""
    from services import audio as service
    from services.audio import AudioTooLarge, ingest_recording

    async def must_not_be_called(*args, **kwargs):
        raise AssertionError("the recogniser was called before the size was checked")

    monkeypatch.setattr(service, "MAX_UPLOAD_BYTES", 128)
    monkeypatch.setattr(service, "transcribe", must_not_be_called)
    user = await a_user(db_session, client)

    with pytest.raises(AudioTooLarge) as caught:
        await ingest_recording(db_session, user, b"x" * 129)

    assert caught.value.size == 129


async def test_the_pipeline_stores_what_the_recogniser_measured(
    audio_root, client, db_session, monkeypatch
):
    """`ingest_recording` transcribes first and stores second, and the row records the
    decoder's numbers rather than anything the caller supplied."""
    from services import audio as service
    from services.audio import ingest_recording
    from models.audio import Transcription

    transcript = Transcription(
        text="hello there",
        words=[{"w": "hello", "start_ms": 0, "end_ms": 400, "logprob": -0.01}],
        confidence=0.99,
        timestamp_fixups=0,
        language="en",
        model="small.en",
        decoder={"beam_size": 5, "vad_filter": True, "compute_type": "int8"},
        source={
            "format": "matroska,webm",
            "codec": "opus",
            "sample_rate": 48000,
            "channels": 2,
            "duration_ms": 1234,
        },
        latency_ms=90,
    )

    async def fake_transcribe(*args, **kwargs):
        return transcript

    monkeypatch.setattr(service, "transcribe", fake_transcribe)
    user = await a_user(db_session, client)

    asset, created, result = await ingest_recording(db_session, user, RECORDING)
    await db_session.commit()

    assert created is True
    assert result.text == "hello there"
    # 48 kHz stereo WebM from a browser, recorded as such — not as the 16 kHz mono the
    # model saw. The column describes the recording, not the model's view of it.
    assert (asset.sample_rate, asset.format, asset.duration_ms) == (
        48000,
        "matroska,webm",
        1234,
    )
