"""Storing a recording, and finding it again safely.

Two properties this module exists to hold:

**Content-addressed, so a retry is not a second recording.** The filename is the sha256
of the bytes, and `audio_assets` has a unique constraint on `(user_id, sha256)`. A
browser that retries an upload after a timeout, or a user who double-taps send, gets the
same row back rather than a duplicate attempt in their history. The uniqueness is scoped
to the user on purpose: two people reading the same passage are two attempts even in the
unlikely event the files are byte-identical.

**No path from a request ever reaches the filesystem.** The stored name is a hex digest
this module computed — 64 characters from a 16-symbol alphabet, so there is no `..`, no
separator and no absolute path that could be smuggled through it. `resolve_path` then
checks containment anyway, because a guarantee that depends on every future caller
remembering it is not a guarantee.

There is no ffmpeg here, and no media library at all. The API cannot open an audio file
and does not try to: `format`, `sample_rate` and `duration_ms` are reported by the asr
service, which decoded the bytes, and stored as measured rather than as declared by
whatever sent them.
"""

import hashlib
from pathlib import Path

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select

from config import AUDIO_ROOT, MAX_UPLOAD_BYTES
from db_models import Attempt, AudioAsset, Turn, User
from models.audio import SourceMedia, Transcription
from services.asr_client import transcribe


class AudioPathError(Exception):
    """A stored path does not resolve inside AUDIO_ROOT. Never expected; never ignored."""


class AudioTooLarge(Exception):
    """The upload is over MAX_UPLOAD_BYTES. Refused before anything expensive happens."""

    def __init__(self, size: int) -> None:
        super().__init__(f"upload is {size} bytes; the limit is {MAX_UPLOAD_BYTES}")
        self.size = size


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def storage_path(user_id: int, digest: str) -> Path:
    """Where the bytes for one digest belong.

    No extension. The container format lives in the `format` column, where it is a
    fact the decoder reported; a filename extension would be a second copy of it that
    nothing validates and that the media type could be read from by mistake.

    Partitioned by user because that is the unit of deletion: FR-26 lets somebody turn
    audio retention off, and "delete this person's recordings" should be a directory
    rather than a query joined against a filesystem walk.
    """
    return Path(AUDIO_ROOT) / str(user_id) / digest


def resolve_path(asset: AudioAsset) -> Path:
    """The absolute path of a stored asset, proven to be inside AUDIO_ROOT.

    The check is `Path.resolve()` on both sides and then `is_relative_to`, which follows
    symlinks — the case a string prefix comparison misses, and the one that turns
    "recordings are on their own volume" into "recordings are wherever a link points".
    """
    root = Path(AUDIO_ROOT).resolve()
    path = Path(asset.path).resolve()
    if not path.is_relative_to(root):
        raise AudioPathError(f"asset {asset.id} resolves outside {root}")
    return path


async def store_recording(
    db: AsyncSession,
    user: User,
    data: bytes,
    source: SourceMedia,
    device_hint: str | None = None,
) -> tuple[AudioAsset, bool]:
    """Persist one recording. Returns the row and whether it was newly created.

    The write is attempted and the collision is caught, rather than a SELECT followed by
    an INSERT. Between those two statements another request can insert the same digest —
    the double-tap this function exists to handle is precisely the case where two
    identical uploads are in flight at once — and the unique index is the only thing that
    can actually decide it. The pre-check would just move the error somewhere less
    convenient.

    **The INSERT goes inside a SAVEPOINT**, and that is the part worth reading twice. A
    plain `session.rollback()` in the collision path would undo the *whole* transaction,
    not the failed row — and from m6 this function is called inside a larger unit of work
    that also inserts a turn. A duplicate recording would then silently discard the turn
    that carried it, which is a data-loss bug that only appears on a retry. `begin_nested`
    rolls back to the savepoint, so the caller's work survives and so do the caller's
    loaded objects: a full rollback also expires every instance in the identity map, and
    the next attribute access on one of them raises `MissingGreenlet` somewhere entirely
    unrelated.

    The file is written before the row, so a crash between them leaves an orphaned blob
    rather than a row pointing at nothing. An orphan wastes space; a dangling row is an
    endpoint that 500s on read.
    """
    digest = sha256_of(data)
    path = storage_path(user.id, digest)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        # Written to a neighbouring name and moved into place, so a reader can never
        # observe a half-written file. os.replace is atomic within a filesystem.
        temporary = path.with_name(f".{digest}.partial")
        temporary.write_bytes(data)
        temporary.replace(path)

    try:
        async with db.begin_nested():
            asset = AudioAsset(
                user_id=user.id,
                path=str(path),
                duration_ms=source.duration_ms,
                sample_rate=source.sample_rate,
                format=source.format,
                sha256=digest,
                device_hint=device_hint,
            )
            db.add(asset)
            await db.flush()
    except IntegrityError:
        existing = await db.scalar(
            select(AudioAsset).where(
                AudioAsset.user_id == user.id, AudioAsset.sha256 == digest
            )
        )
        if existing is None:
            # The unique constraint fired but the row is not there: something other
            # than the (user_id, sha256) index rejected this. Re-raising is right —
            # swallowing it would return None from a function that promises a row.
            raise
        return existing, False

    return asset, True


async def ingest_recording(
    db: AsyncSession,
    user: User,
    data: bytes,
    filename: str = "recording",
    content_type: str | None = None,
    device_hint: str | None = None,
) -> tuple[AudioAsset, bool, Transcription]:
    """The audio pipeline, end to end: bytes in, stored asset and transcript out.

    Transcription happens *before* the row is written, because the row cannot be written
    without it — `duration_ms`, `sample_rate` and `format` are all NOT NULL and all of
    them are things only a decoder knows. That ordering also means a recording the
    service cannot decode never becomes a row: the caller gets `AsrRejected` and the
    table gets nothing.

    m6 (`POST /sessions/{id}/turns`) and m8 (`POST /attempts`) are the two callers. They
    are the reason this is a function in `services/` rather than the body of an endpoint:
    both need exactly this, one of them inside a larger transaction with an LLM call in
    it, and neither should be re-deriving the order these two steps go in.

    Not done here, deliberately: caching a transcript against the digest. At m4 there is
    nowhere to put one — `turns.transcript` is the column for it and a turn needs a
    session, which is m6. So a re-uploaded identical recording is transcribed again and
    deduplicates only its bytes. m6 is where that short-circuit belongs, and adding a
    table for it now would be building m6's storage a milestone early.
    """
    if len(data) > MAX_UPLOAD_BYTES:
        # Checked here rather than only at the asr service, and before the model call
        # rather than after it. The service has a ceiling of its own, but by the time a
        # 40 MB upload has crossed the compose network it has already been paid for; and
        # the limit that belongs to the product — how long a turn may be — belongs to
        # the service that knows what a turn is.
        raise AudioTooLarge(len(data))

    transcription = await transcribe(data, filename=filename, content_type=content_type)
    asset, created = await store_recording(
        db, user, data, transcription.source, device_hint=device_hint
    )
    return asset, created, transcription


async def delete_unreferenced_assets(
    db: AsyncSession, asset_ids: set[int]
) -> list[Path]:
    """Delete any of `asset_ids` that nothing points at any more. Returns the files to remove.

    Called when a session is deleted. Without it, `DELETE /sessions/{id}` would remove
    the conversation and leave every recording it contained sitting on the volume and in
    the table — still fetchable by anyone who had noted the asset id, and still counted
    against the disk. "Delete" that leaves the audio behind is the kind of promise this
    project should not make.

    **Unreferenced is checked, not assumed.** An asset is content-addressed and unique
    per `(user_id, sha256)`, so one row can legitimately be pointed at by more than one
    turn, and from m8 by an attempt as well. Deleting on the strength of "this session
    referenced it" would eventually take a recording out from under a read-aloud attempt
    that was still using it. The two `NOT EXISTS` checks below are what make this safe to
    call before those other referrers exist, rather than a bug scheduled for m8.

    Files are **not** removed here. The rows are deleted, the caller commits, and only
    then does it unlink — the mirror of `store_recording`, which writes the file before
    the row. A crash in that gap leaves an orphaned blob, which wastes space; the other
    order leaves a row pointing at a file that is gone, which is an endpoint that 404s on
    a recording the user was told they still had.
    """
    if not asset_ids:
        return []

    still_used_by_turn = (
        select(Turn.id).where(Turn.audio_asset_id == AudioAsset.id).exists()
    )
    still_used_by_attempt = (
        select(Attempt.id).where(Attempt.audio_asset_id == AudioAsset.id).exists()
    )

    orphans = list(
        (
            await db.scalars(
                select(AudioAsset).where(
                    AudioAsset.id.in_(asset_ids),
                    ~still_used_by_turn,
                    ~still_used_by_attempt,
                )
            )
        ).all()
    )

    paths = []
    for asset in orphans:
        try:
            paths.append(resolve_path(asset))
        except AudioPathError:
            # The row points outside the audio volume, so this process did not write it
            # and will not unlink it. The row still goes: it is unreferenced either way,
            # and refusing to delete it would keep a dangling reference to a file this
            # code is not allowed to touch.
            pass
        await db.delete(asset)

    return paths
