"""Turn wire shapes.

**`words` is not here, and that is the decision worth stating.** Every turn stores an
array of word timings — roughly 150 entries for a long turn, each with four fields — and
it is the raw material for every fluency metric. It is also read by exactly one kind of
consumer, which is server-side analysis. Serialising it into `GET /sessions/{id}` would
multiply the size of a transcript response by something like twenty, to deliver a payload
that no screen draws and that the browser would immediately discard.

If a client ever needs timings — a karaoke-style transcript highlight is the plausible
one — that is an endpoint for a single turn, not a field on every turn of every session.
"""

from datetime import datetime

from pydantic import BaseModel, Field

from config import ASR_CONFIDENCE_FLOOR
from models.common import ORMModel


class TurnOut(ORMModel):
    """One turn as the owner sees it.

    `audio_url` is built rather than stored. The client needs a path it can put in an
    `<audio src>`, and the alternative — letting the browser assemble `/audio/{id}` from
    the id — is a URL scheme duplicated in two languages that drift apart at the first
    rename.
    """

    id: int
    idx: int
    role: str
    transcript: str | None
    audio_asset_id: int | None
    audio_url: str | None = None
    asr_confidence: float | None
    asr_model: str | None
    llm_model: str | None
    tts_voice: str | None
    latency_ms: int | None
    created_at: datetime

    # Derived, not stored. The threshold is a placeholder awaiting calibration against
    # real learner speech, and the day it moves, every turn ever recorded has to move
    # with it — which a stored boolean would not. It is on the turn rather than only on
    # the response that created it because a reloaded transcript has to mark the same
    # turns as the live one did; without this the marker survived a conversation and
    # vanished on a page refresh.
    low_confidence: bool = False

    @classmethod
    def of(cls, turn) -> "TurnOut":
        out = cls.model_validate(turn)
        if turn.audio_asset_id is not None:
            out.audio_url = f"/audio/{turn.audio_asset_id}"
        out.low_confidence = (
            turn.asr_confidence is not None
            and turn.asr_confidence < ASR_CONFIDENCE_FLOOR
        )
        return out


class SpeechOut(BaseModel):
    """Whether the reply was actually spoken, and if not, why.

    A separate object rather than a nullable `audio_url`, because "the voice is down"
    and "this turn has no audio" are different facts and the UI should be able to say
    which. The client renders the difference: a missing player is a bug, a player with a
    note saying the voice is unavailable is a system being honest.
    """

    # ok | skipped | unavailable | rejected | protocol
    status: str
    detail: str | None = None
    voice: str | None = None
    duration_ms: int | None = None
    sample_rate: int | None = None
    sentences: int = Field(default=0, ge=0)


class TurnTiming(BaseModel):
    """Where a turn's wall clock went.

    Returned on every turn rather than only under a debug flag, because a latency
    regression is felt long before it is noticed, and a number that is only visible when
    somebody goes looking is a number nobody looks at. It is also what `make
    turn-latency` reads, so the measurement and the product see the same figures.

    On the overlapped path `synthesis_ms` is the tail rather than the work: most of the
    voice's effort happened inside time that was being spent generating, so
    `generation_ms + synthesis_ms` is less than the two would cost in series.
    """

    total_ms: int = Field(ge=0)
    asr_ms: int = Field(ge=0)
    generation_ms: int = Field(ge=0)

    # What the turn still had to wait for once generation finished: the last sentence
    # on the overlapped path, the whole reply's synthesis in series. Comparing this field
    # between `make turn-latency` and `make turn-latency-noflow` is how the overlap is
    # measured — there is no honest way to do it within one run.
    synthesis_ms: int = Field(ge=0)
    reply_ms: int = Field(ge=0)

    # Non-zero only on the first turn after the model was evicted from memory. Reported
    # separately because a p95 that silently contains one cold load is a p95 about
    # something other than the system's speed.
    model_load_ms: int | None = None

    # Ollama's own counts for this turn, not the estimate that sized the prompt.
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class TurnResponse(BaseModel):
    """What `POST /sessions/{id}/turns` returns: both halves of the exchange.

    Both turns, not just the reply. The client sent audio and has no transcript of its
    own — the recogniser is the only thing that knows what was said — so returning only
    the persona's answer would force an immediate second request to find out what the
    speaker was heard to have said.
    """

    session_id: int
    user_turn: TurnOut
    reply_turn: TurnOut
    speech: SpeechOut
    timing: TurnTiming

    # Below the confidence gate this turn is still stored and still replied to, but it
    # must not contribute to an accuracy trend. Surfaced here so the client can mark it
    # and the analysers do not have to re-derive the same threshold.
    #
    # The same value now appears as `user_turn.low_confidence`, and the duplication is
    # deliberate rather than left over: this field is part of the turn endpoint's
    # contract, and a client that reads only the envelope should not have to reach into
    # a nested object to find out whether the recogniser was sure. Both come from the
    # one comparison in `TurnOut.of`, so they cannot disagree.
    low_confidence: bool = False
