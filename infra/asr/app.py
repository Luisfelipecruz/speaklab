"""SpeakLab ASR — audio in, transcript with per-word timings and logprobs out.

This service exists because of one line in PRD §7.1: every fluency metric in the
product is derived from word-level timings, and every accuracy metric is gated on
word-level confidence. Nothing else in the system can produce either. So
`word_timestamps=True` is not a feature flag here, it is the reason the service exists.

Three things it does, in order:

1. **Decodes whatever arrives.** The browser sends Opus in a WebM container on Chrome
   and AAC in MP4 on Safari; neither reaches the model. PyAV — the ffmpeg libraries,
   in-process — resamples everything to 16 kHz mono, which is the only input Whisper
   has ever seen.
2. **Transcribes it**, forcing word timestamps.
3. **Reports what it received**, because the API stores `format`, `sample_rate` and
   `duration_ms` on the `audio_assets` row and should not have to guess at any of them.
   The decoder is the authority on those, so the decoder answers.

It holds no database connection, no user identity and no notion of a session. It is
reachable only from inside the compose network (invariant: model services are never
exposed to the browser), which is why there is no auth here and why that is not an
oversight.
"""

from __future__ import annotations

import asyncio
import io
import logging
import math
import os
import time
from contextlib import asynccontextmanager
from typing import Any

import av
import numpy as np
from fastapi import FastAPI, File, HTTPException, Response, UploadFile
from faster_whisper import WhisperModel

log = logging.getLogger("speaklab.asr")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# ── Settings ────────────────────────────────────────────────────────────────

MODEL_NAME = os.environ.get("WHISPER_MODEL", "small.en")

# int8 on CPU. The quality cost against float32 is small enough to be inside the noise
# of the golden set (docs/decisions/0001 has the measurement) and the speed difference
# is not.
COMPUTE_TYPE = os.environ.get("WHISPER_COMPUTE_TYPE", "int8")
DEVICE = os.environ.get("WHISPER_DEVICE", "cpu")

# 0 lets CTranslate2 choose, which is the right default on a machine whose core count
# this file cannot know. Set it when the container is sharing a host with something
# latency-sensitive.
CPU_THREADS = int(os.environ.get("WHISPER_CPU_THREADS", "0"))

# Beam size is the latency dial. 1 is greedy decoding; 5 is the Whisper default. The
# measured trade on the golden set is in docs/decisions/0001.
BEAM_SIZE = int(os.environ.get("WHISPER_BEAM_SIZE", "5"))

# English-only, because the product is English practice. An `.en` model has no language
# detection to skip, and forcing it on a multilingual model stops a heavily accented
# turn from being transcribed as Spanish — a failure mode that looks like nonsense
# output rather than like a language guess.
LANGUAGE = os.environ.get("WHISPER_LANGUAGE", "en")

# Silero VAD, on by default. Whisper hallucinates on silence — it emits "Thank you." or
# "Bye." for an empty recording, and a learner who pressed record and hesitated would
# get a transcript of words they never said, scored as if they had. The cost is that
# very quiet speech can be trimmed; WHISPER_VAD=0 turns it off, and the effect on the
# golden set is measured in docs/decisions/0001.
VAD = os.environ.get("WHISPER_VAD", "1") == "1"

# Whisper's own decoder can loop, repeating a phrase until the segment ends, when it is
# conditioned on its previous output. Off, permanently: a repetition loop in a learner's
# transcript is not a transcription error the user can act on, it is noise in every
# metric downstream of it.
CONDITION_ON_PREVIOUS = False

TARGET_SAMPLE_RATE = 16000

# 25 MB. A conversational turn is seconds; a read-aloud passage is under a minute. This
# is a bound on damage, not a product limit — the API enforces its own, lower one.
MAX_UPLOAD_BYTES = int(os.environ.get("ASR_MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))

# Inference is CPU-bound and CTranslate2 is already using every core. Two concurrent
# transcriptions on one container do not finish sooner; they finish together, later,
# and the second caller's timeout fires. Serialised on purpose.
_inference_slot = asyncio.Semaphore(int(os.environ.get("ASR_MAX_CONCURRENCY", "1")))


# ── Model loading ───────────────────────────────────────────────────────────
#
# Loading happens in a background thread and the service answers /health throughout.
# A cold start downloads weights, which is minutes, and a health endpoint that does not
# answer until that finishes is indistinguishable from a crash to everything watching it.


class _ModelState:
    def __init__(self) -> None:
        self.model: WhisperModel | None = None
        self.error: str | None = None
        self.load_seconds: float | None = None


state = _ModelState()


def _load_model() -> None:
    started = time.perf_counter()
    log.info("loading %s (%s, %s)", MODEL_NAME, DEVICE, COMPUTE_TYPE)
    try:
        model = WhisperModel(
            MODEL_NAME,
            device=DEVICE,
            compute_type=COMPUTE_TYPE,
            cpu_threads=CPU_THREADS,
            num_workers=1,
        )
    except Exception as exc:  # noqa: BLE001 - reported, not raised into a dead thread
        state.error = f"{type(exc).__name__}: {exc}"
        log.error("model load failed: %s", state.error)
        return
    state.load_seconds = round(time.perf_counter() - started, 2)
    state.model = model
    log.info("loaded %s in %.2fs", MODEL_NAME, state.load_seconds)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Held in a local so the task is not garbage-collected mid-load, which is a real
    # asyncio footgun rather than a theoretical one.
    loader = asyncio.create_task(asyncio.to_thread(_load_model))
    yield
    loader.cancel()


app = FastAPI(
    title="SpeakLab ASR",
    description="Whisper on CTranslate2, with word-level timestamps and logprobs.",
    version="1.0.0",
    lifespan=lifespan,
)


# ── Decoding ────────────────────────────────────────────────────────────────


class MediaError(Exception):
    """The bytes are not audio this service can decode. A 422, never a 500."""


def decode(data: bytes) -> tuple[np.ndarray, dict[str, Any]]:
    """Whatever arrived -> 16 kHz mono float32, plus what it was before.

    `duration_ms` is computed from the decoded sample count rather than read from the
    container header. A header can be wrong — a truncated WebM from an interrupted
    upload declares the duration the recorder intended — and the number that matters
    downstream is the length of the audio the model actually saw.
    """
    try:
        container = av.open(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001
        raise MediaError(f"cannot open media: {type(exc).__name__}") from exc

    with container:
        streams = container.streams.audio
        if not streams:
            raise MediaError("no audio stream in this file")
        stream = streams[0]

        source = {
            "format": container.format.name,
            "codec": stream.codec_context.name,
            "sample_rate": stream.codec_context.sample_rate,
            "channels": getattr(stream.codec_context, "channels", None)
            or getattr(getattr(stream.codec_context, "layout", None), "nb_channels", 1),
        }

        resampler = av.audio.resampler.AudioResampler(
            format="s16", layout="mono", rate=TARGET_SAMPLE_RATE
        )
        chunks: list[np.ndarray] = []
        try:
            for frame in container.decode(stream):
                for resampled in resampler.resample(frame):
                    chunks.append(resampled.to_ndarray().reshape(-1))
            # Flushing matters: the resampler buffers, and without this the tail of
            # every recording is silently missing.
            for resampled in resampler.resample(None):
                chunks.append(resampled.to_ndarray().reshape(-1))
        except Exception as exc:  # noqa: BLE001
            raise MediaError(f"cannot decode audio: {type(exc).__name__}") from exc

    pcm = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.int16)
    source["duration_ms"] = round(len(pcm) / TARGET_SAMPLE_RATE * 1000)

    # CTranslate2 wants float32 in [-1, 1); 32768 rather than 32767 because that is the
    # magnitude of the most negative int16 and the only divisor that cannot clip.
    return pcm.astype(np.float32) / 32768.0, source


# ── Transcription ───────────────────────────────────────────────────────────


def _transcribe(audio: np.ndarray, duration_ms: int) -> dict[str, Any]:
    """Run the model. Blocking, and called in a worker thread.

    Returns the wire shape directly, including the `words` array in exactly the form
    `turns.words` stores: `[{w, start_ms, end_ms, logprob}]`. The database column and
    this function were written against each other; changing one without the other is
    the kind of drift that shows up as a fluency metric of zero.
    """
    model = state.model
    assert model is not None  # guarded by the caller

    segments, info = model.transcribe(
        audio,
        language=LANGUAGE,
        beam_size=BEAM_SIZE,
        word_timestamps=True,
        vad_filter=VAD,
        condition_on_previous_text=CONDITION_ON_PREVIOUS,
    )

    words: list[dict[str, Any]] = []
    texts: list[str] = []
    fixups = 0

    # `segments` is a generator; the work happens here, on iteration.
    for segment in segments:
        texts.append(segment.text)
        for word in segment.words or []:
            start_ms = round(word.start * 1000)
            end_ms = round(word.end * 1000)

            # The wire contract promises 0 <= start <= end <= duration. Whisper
            # occasionally returns a word ending after the audio does, or a zero-width
            # word. Those are repaired rather than passed on — but they are also
            # COUNTED, because a fixup rate that starts climbing is a fact about the
            # model, and silently repairing it would be the same mistake as scoring an
            # unmapped phone as correct.
            fixed = False
            if start_ms < 0:
                start_ms, fixed = 0, True
            if end_ms > duration_ms:
                end_ms, fixed = duration_ms, True
            if end_ms < start_ms:
                end_ms, fixed = start_ms, True
            fixups += fixed

            words.append(
                {
                    "w": word.word.strip(),
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    # Stored as a logprob, not a probability, because that is what the
                    # confidence gate in PRD §7.5 thresholds on and what `turns.words`
                    # declares. `max(p, 1e-9)` keeps a zero-probability word from
                    # becoming -inf and taking the JSON serialiser with it.
                    "logprob": round(math.log(max(word.probability, 1e-9)), 4),
                }
            )

    # The arithmetic mean of per-word probabilities: "how sure was the recogniser, on
    # average, about the words it emitted". A stricter gate — the worst single word —
    # is derivable from `words` without re-running anything, which is why only one
    # aggregate is published here. Empty transcript means no evidence, so 0.0 rather
    # than a division by zero or a misleading 1.0.
    confidence = (
        sum(math.exp(word["logprob"]) for word in words) / len(words) if words else 0.0
    )

    return {
        "text": "".join(texts).strip(),
        "words": words,
        "confidence": round(confidence, 4),
        "timestamp_fixups": fixups,
        "language": info.language,
        "model": MODEL_NAME,
        # What the decoder was actually configured to do, echoed so that a number
        # measured six months ago can be compared against a number measured today.
        # `turns.asr_model` exists for the same reason at the row level.
        "decoder": {
            "beam_size": BEAM_SIZE,
            "vad_filter": VAD,
            "compute_type": COMPUTE_TYPE,
        },
    }


# ── Endpoints ───────────────────────────────────────────────────────────────


@app.get("/health")
async def health(response: Response) -> dict[str, Any]:
    """Alive, and honest about whether it can actually do anything yet.

    200 with `model_loaded: false` while the weights load — a cold start downloads
    hundreds of megabytes and must not read as a crash. 503 only when the load has
    *failed*, which is permanent: this process will never serve a transcript, the
    compose healthcheck should mark it unhealthy, and the API's /health should report
    it as `error` (up and unwell) rather than `unreachable` (absent).
    """
    if state.error is not None:
        response.status_code = 503
    return {
        "status": "error" if state.error else "ok",
        "model": MODEL_NAME,
        "model_loaded": state.model is not None,
        "load_seconds": state.load_seconds,
        "device": DEVICE,
        "compute_type": COMPUTE_TYPE,
        "error": state.error,
    }


@app.post("/transcribe")
async def transcribe(file: UploadFile = File(...)) -> dict[str, Any]:
    """Audio in, transcript with per-word timings and logprobs out."""
    data = await file.read()

    if not data:
        raise HTTPException(status_code=422, detail="empty upload")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"upload is {len(data)} bytes; the limit is {MAX_UPLOAD_BYTES}",
        )
    if state.error is not None:
        raise HTTPException(status_code=503, detail=f"model unavailable: {state.error}")
    if state.model is None:
        raise HTTPException(
            status_code=503, detail=f"{MODEL_NAME} is still loading; retry shortly"
        )

    started = time.perf_counter()
    try:
        audio, source = await asyncio.to_thread(decode, data)
    except MediaError as exc:
        # 422, not 500. Unreadable audio is a fact about the request, and a service
        # that answers 500 to it invites a retry loop that can never succeed.
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if source["duration_ms"] == 0:
        raise HTTPException(status_code=422, detail="decoded to zero samples")

    async with _inference_slot:
        result = await asyncio.to_thread(_transcribe, audio, source["duration_ms"])

    result["source"] = source
    result["latency_ms"] = round((time.perf_counter() - started) * 1000)
    return result
