"""Writing a generated reply down, and the one place that decides how it was generated.

Two functions, both shared by `POST /sessions` (the opening turn) and
`POST /sessions/{id}/turns` (every turn after it). They live here rather than in either
router because the opening turn and a mid-conversation turn are the same operation with
a different message list, and the moment that stops being true in the code is the moment
the persona's first line starts being stored differently from its tenth.
"""

from sqlalchemy.ext.asyncio import AsyncSession

import config
from db_models import PracticeSession, Turn, User
from models.audio import SourceMedia
from services.audio import store_recording
from services.conversation import Reply, generate_reply
from services.llm import ChatMessage, LlmProvider


async def reply_to(
    provider: LlmProvider, messages: list[ChatMessage], voice: str | None = None
) -> Reply:
    """Generate and speak one persona turn, honouring the configured overlap.

    `config.LLM_STREAM_TO_TTS` is read here, at call time, rather than imported as a
    value. That is what lets `make turn-latency` run the same endpoint twice with the
    fallback on and off and compare two measurements of the real path, instead of
    comparing the real path against a description of the other one.
    """
    return await generate_reply(
        provider,
        messages,
        voice=voice or config.PIPER_VOICE,
        stream_to_tts=config.LLM_STREAM_TO_TTS,
    )


async def persist_reply(
    db: AsyncSession,
    user: User,
    session: PracticeSession,
    reply: Reply,
    idx: int,
    latency_ms: int,
) -> Turn:
    """Store the persona's audio and its turn row. Does not commit.

    The audio goes through `store_recording` — the same content-addressed path a user's
    recording takes — and that deserves a sentence, because it looks at first like the
    wrong function for the job. It is the right one for two reasons. The row it writes is
    an `audio_assets` row either way, with the same NOT NULL columns, and `GET /audio/{id}`
    already serves it with an ownership check the reply needs just as much as the
    recording does. And its INSERT is inside a savepoint, so a digest collision cannot
    roll back the turn that is being written in the same transaction.

    `duration_ms` and `sample_rate` are the ones computed from the frames actually
    concatenated (`services/wav.py`), not the ones the tts service reported per sentence.
    Where those two could disagree, the stored number should describe the stored audio.

    **The voice is recorded, not derived.** Synthesis is non-deterministic (decision
    0002), so which voice produced this audio cannot be recovered later by re-synthesising
    the text and comparing. If it is not written down now it is not knowable at all.

    No commit, no flush of the caller's other work: the router owns the transaction, and
    a service function that commits is a service function that cannot be called twice in
    one unit of work.
    """
    asset_id = None
    if reply.audio and reply.sample_rate and reply.duration_ms:
        asset, _ = await store_recording(
            db,
            user,
            reply.audio,
            SourceMedia(
                format="wav",
                codec="pcm_s16le",
                sample_rate=reply.sample_rate,
                channels=1,
                duration_ms=reply.duration_ms,
            ),
            # No device_hint. That column answers "which microphone made this", which
            # is how a pronunciation trend gets annotated when somebody changes headsets.
            # Synthesised speech came from no microphone, and writing a sentinel there
            # would put a fake device into the one column whose whole purpose is to be
            # trustworthy about devices.
            device_hint=None,
        )
        asset_id = asset.id

    turn = Turn(
        session_id=session.id,
        idx=idx,
        role="assistant",
        transcript=reply.text,
        audio_asset_id=asset_id,
        llm_model=reply.model,
        tts_voice=reply.voice,
        prompt_tokens=reply.prompt_tokens,
        completion_tokens=reply.completion_tokens,
        latency_ms=latency_ms,
    )
    db.add(turn)
    return turn
