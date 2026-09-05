"""Wire shapes for audio and transcription.

`Word` is the load-bearing type in this file, and it is deliberately the same four
fields as `turns.words` stores and the same four the asr service emits. Three copies of
one shape is two chances to drift, so this module is the one the other two are checked
against: `services/asr_client.py` parses the service's response into these models, and
the turn writer stores them straight into the JSONB column. A field renamed here fails
validation immediately rather than producing a fluency metric of zero six months later.
"""

from datetime import datetime

from pydantic import BaseModel, Field

from models.common import ORMModel


class Word(BaseModel):
    """One recognised word, with the timing and confidence every metric derives from.

    `w` rather than `word` because this array is stored per turn and read whole: a
    150-word turn carries the key 150 times, and the short name is the difference
    between a JSONB column of readable size and one that is mostly field names.
    """

    w: str
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)

    # A log-probability, so it is <= 0 and more negative means less sure. Stored rather
    # than a 0-1 probability because the confidence gate thresholds in log space, where
    # the difference between 0.9 and 0.99 is the same size as the difference between
    # 0.09 and 0.9.
    logprob: float = Field(le=0)


class SourceMedia(BaseModel):
    """What the decoder found in the upload, before it normalised anything.

    Reported by the service that did the decoding rather than guessed at by the API,
    which holds no media library at all. These three fields are what the
    `audio_assets` row records, so the row describes what a decoder actually saw.
    """

    # ffmpeg's demuxer name, verbatim: `wav`, `flac`, `matroska,webm`. The comma form is
    # not a bug — it is one demuxer that handles several containers, and collapsing it
    # to a prettier single word here would be this layer inventing a fact.
    format: str
    codec: str
    sample_rate: int = Field(gt=0)
    channels: int = Field(gt=0)

    # Computed from the decoded sample count, not read from the container header. A
    # truncated upload declares the duration the recorder intended.
    duration_ms: int = Field(ge=0)


class DecoderSettings(BaseModel):
    """What the recogniser was configured to do.

    Echoed on every transcript for the same reason `turns.asr_model` exists at the row
    level: a WER measured today and a WER measured after somebody set
    `WHISPER_BEAM_SIZE=1` are not comparable, and "we changed a decoder setting in
    March" is otherwise indistinguishable from the user getting worse.
    """

    beam_size: int
    vad_filter: bool
    compute_type: str


class Transcription(BaseModel):
    """One transcript, as the asr service returns it."""

    text: str
    words: list[Word]

    # Mean per-word probability, 0-1. A single aggregate on purpose: a stricter gate —
    # the worst word in the turn — is derivable from `words` without re-running the
    # model, so publishing two would be publishing one of them twice.
    confidence: float = Field(ge=0, le=1)

    # How many word timings the service had to correct to satisfy its own contract
    # (0 <= start <= end <= duration). Non-zero is not an error; it is a fact about the
    # model worth watching, like the out-of-taxonomy counter on error labelling.
    timestamp_fixups: int = Field(ge=0)

    language: str
    model: str
    decoder: DecoderSettings
    source: SourceMedia
    latency_ms: int = Field(ge=0)


class AudioAssetOut(ORMModel):
    """A stored recording, as the owner sees it.

    No `path`. It is a location on a volume the browser cannot reach and has no reason
    to know, and exposing it would invite a client to construct one.
    """

    id: int
    duration_ms: int
    sample_rate: int
    format: str
    sha256: str
    device_hint: str | None
    created_at: datetime
