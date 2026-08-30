"""Wire shapes for synthesised speech.

The mirror image of `models/audio.py`. There, a recogniser told the API what it heard;
here the API asks for speech and is told what came back. Both files exist for the same
reason: the `audio_assets` row records `duration_ms`, `sample_rate` and `format`, and in
both directions the service that produced the audio is the authority on those, not the
API — which holds no media library at all (invariant I5).

The metadata arrives in response headers rather than in the body, because the body is a
WAV. Parsing headers into a typed model rather than reading `response.headers[...]` at
the call site is what makes a service that stops sending `X-Duration-Ms` a loud failure
instead of a `KeyError` in whichever milestone happens to touch it next.
"""

from pydantic import BaseModel, Field


class Speech(BaseModel):
    """One synthesised utterance, whole.

    `audio` is a complete WAV including its header, so it can be written to the audio
    volume and served by `GET /audio/{asset_id}` with no re-encoding — which is also why
    the service returns WAV rather than MP3: an encode step inside a 400 ms budget buys
    a smaller file for audio that never leaves this machine.
    """

    audio: bytes
    voice: str
    sample_rate: int = Field(gt=0)
    duration_ms: int = Field(gt=0)

    # How many sentences Piper split the text into. Worth having because it is the unit
    # the streaming endpoint emits, so a caller can tell in advance whether streaming
    # would buy anything for this particular reply — for a one-sentence reply it buys
    # nothing at all.
    sentences: int = Field(ge=1)

    # Phoneme length scale the audio was produced at: below 1 faster, above 1 slower.
    # Recorded because a reply synthesised at 0.8 and one at 1.0 are different audio for
    # the same text, and a stored asset should say which it is.
    length_scale: float = Field(gt=0)

    latency_ms: int = Field(ge=0)


class SpeechChunk(BaseModel):
    """One sentence of a streamed synthesis.

    Raw 16-bit PCM, not a WAV per chunk — the container would be wrong for both
    consumers. Concatenating the `pcm` of every chunk in `index` order and adding a
    single WAV header reproduces exactly what `POST /synthesize` would have returned.
    """

    index: int = Field(ge=0)
    pcm: bytes
    samples: int = Field(ge=0)
    duration_ms: int = Field(ge=0)
    sample_rate: int = Field(gt=0)
    sample_width: int = Field(gt=0)
    channels: int = Field(gt=0)

    # Measured from the start of the request, not from the previous chunk. On chunk 0
    # this is the number PRD §9.1's fallback exists to reduce: how long the listener
    # waited before hearing anything at all.
    latency_ms: int = Field(ge=0)
