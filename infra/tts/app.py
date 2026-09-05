"""SpeakLab TTS — text in, the persona's voice out.

A session's opening turn and every persona reply are delivered *as speech*, not as text
the browser reads aloud with whatever voice the operating system happens to have. It holds one voice, loaded once, and it is reachable
only from inside the compose network — the same rule as `asr`, and the reason there is
no authentication here.

**Two endpoints for one job, and the second one is the whole latency story.**

`POST /synthesize` returns the finished WAV. It is what the turn writer stores on the
`audio_assets` row, and on a full-length reply it takes about a second — against a 400 ms
budget. That is a miss, and it is not fixable by tuning, because the cost is proportional
to the audio produced.

`POST /synthesize/stream` returns one PCM chunk **per sentence**, as Piper produces
them, each tagged with how long the caller had been waiting when it arrived. The first
chunk lands in about 90 ms regardless of how long the reply is, because a first sentence
is a first sentence. Streaming the LLM reply into TTS sentence by sentence is what makes
the budget reachable at all, and both shapes ship together because a service that only
offers the shape which cannot meet its own budget is a service somebody has to reopen.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import os
import time
import wave
from collections.abc import Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime
from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

log = logging.getLogger("speaklab.tts")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# ── Settings ────────────────────────────────────────────────────────────────

VOICE_NAME = os.environ.get("PIPER_VOICE", "en_US-lessac-medium")

# Two directories, resolved in this order, and the order is the design:
#
#   1. VOICE_DIR       the shared model_cache volume. Empty for the default voice and
#                      populated the first time somebody asks for a different one.
#   2. BUILTIN_DIR     baked into the image at build time. 63 MB, which is why this is
#                      the one model in the system that ships inside its image.
#
# A voice in neither is downloaded into (1) during the background load, so it survives
# an image rebuild and is not re-fetched by every developer.
VOICE_DIR = Path(os.environ.get("PIPER_VOICE_DIR", "/models/piper"))
BUILTIN_DIR = Path(os.environ.get("PIPER_BUILTIN_VOICE_DIR", "/opt/piper-voices"))

# 8, not onnxruntime's own default, and this is the single largest lever in the file.
# Measured on the target machine: the default takes 831 ms on an 80-token reply where 8
# threads takes 368 ms — 2.3x, and the difference between missing the 400 ms budget and
# meeting it. The curve is a U: 1 thread is 1248 ms, 16 is 925 ms. More is not better,
# which is exactly why leaving it to a library default was the wrong call.
#
# `min(8, cpu_count)` rather than a flat 8, because 8 is a measurement from a 16-core
# machine and not a property of the model. 0 restores onnxruntime's own choice.
_configured_threads = int(os.environ.get("PIPER_NUM_THREADS", "8"))
NUM_THREADS = (
    min(_configured_threads, os.cpu_count() or _configured_threads)
    if _configured_threads > 0
    else 0
)

# Phoneme length scale: below 1 is faster speech, above 1 is slower. 1.0 is the voice's
# own trained rate. It is configurable because a slower interlocutor is a real
# pedagogical setting for a beginner band, not because anyone should tune it by feel.
LENGTH_SCALE = float(os.environ.get("PIPER_LENGTH_SCALE", "1.0"))

# A bound on damage, not a product limit. A persona reply is capped at 400 output tokens
# by the API (LLM_MAX_OUTPUT_TOKENS), which is a few hundred words; 5000 characters is
# comfortably above anything this service should ever be asked for and well below the
# point where one request could occupy the process for minutes.
MAX_CHARS = int(os.environ.get("TTS_MAX_CHARS", "5000"))

# Piper emits 16-bit mono PCM at the voice's own rate (22050 Hz for the medium voices).
SAMPLE_WIDTH = 2
CHANNELS = 1

# Synthesis is CPU-bound and onnxruntime is already using every thread it was given.
# Two concurrent syntheses do not finish sooner; they finish together, later. Serialised
# for the same reason as the recogniser.
_inference_slot = asyncio.Semaphore(int(os.environ.get("TTS_MAX_CONCURRENCY", "1")))


# ── Loading ─────────────────────────────────────────────────────────────────
#
# In a background thread, with /health answering throughout. For the default voice this
# is a second; for a voice that has to be downloaded it is a minute, and a health
# endpoint that does not answer until then is indistinguishable from a crash.


class _VoiceState:
    def __init__(self) -> None:
        self.voice: Any | None = None
        self.sample_rate: int | None = None
        self.source: str | None = None
        self.error: str | None = None
        self.load_seconds: float | None = None


state = _VoiceState()


def _resolve_voice_files(name: str) -> tuple[Path, str]:
    """Where this voice's .onnx lives, and how it got there.

    Downloads into the shared volume as a last resort. `.onnx.json` is required beside
    it — a model without its config has no phoneme id map, and failing here with a clear
    message beats failing inside onnxruntime with an index error.
    """
    for directory, source in ((VOICE_DIR, "cache"), (BUILTIN_DIR, "image")):
        model = directory / f"{name}.onnx"
        if model.is_file() and model.with_suffix(".onnx.json").is_file():
            return model, source

    from piper.download_voices import download_voice

    log.info(
        "voice %s is in neither %s nor %s; downloading", name, VOICE_DIR, BUILTIN_DIR
    )
    VOICE_DIR.mkdir(parents=True, exist_ok=True)
    download_voice(name, VOICE_DIR)
    return VOICE_DIR / f"{name}.onnx", "download"


def _load_voice() -> None:
    started = time.perf_counter()
    log.info(
        "loading voice %s (threads=%s)",
        VOICE_NAME,
        NUM_THREADS or "onnxruntime default",
    )
    try:
        from piper import PiperVoice
        from piper.config import PiperConfig

        model_path, source = _resolve_voice_files(VOICE_NAME)

        # The session is constructed here rather than by PiperVoice.load, which takes no
        # SessionOptions. That is the only reason: NUM_THREADS is not reachable through
        # the convenience loader, and it is worth 2.3x.
        options = onnxruntime.SessionOptions()
        if NUM_THREADS > 0:
            options.intra_op_num_threads = NUM_THREADS
            options.inter_op_num_threads = 1
        session = onnxruntime.InferenceSession(
            str(model_path),
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )
        with open(model_path.with_suffix(".onnx.json"), encoding="utf-8") as handle:
            config = PiperConfig.from_dict(json.load(handle))

        voice = PiperVoice(session=session, config=config)
    except Exception as exc:  # noqa: BLE001 - reported, not raised into a dead thread
        state.error = f"{type(exc).__name__}: {exc}"
        log.error("voice load failed: %s", state.error)
        return

    state.sample_rate = config.sample_rate
    state.source = source
    state.load_seconds = round(time.perf_counter() - started, 2)
    state.voice = voice
    log.info(
        "loaded %s from %s in %.2fs at %d Hz",
        VOICE_NAME,
        source,
        state.load_seconds,
        config.sample_rate,
    )


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Held in a local so the task is not garbage-collected mid-load.
    loader = asyncio.create_task(asyncio.to_thread(_load_voice))
    yield
    loader.cancel()


app = FastAPI(
    title="SpeakLab TTS",
    description="Piper on onnxruntime. Whole-reply WAV, or one chunk per sentence.",
    version="1.0.0",
    lifespan=lifespan,
)


# ── Synthesis ───────────────────────────────────────────────────────────────


class SynthesiseRequest(BaseModel):
    text: str = Field(min_length=1)

    # Optional, and checked rather than honoured. This process holds exactly one voice:
    # loading an arbitrary one per request would mean an unbounded number of resident
    # ONNX sessions and, for a voice not yet cached, a 60 MB download inside a 400 ms
    # budget. Naming a voice this service is not running is a 400, not a silent
    # substitution — a reply that comes back in the wrong voice is worse than an error.
    voice: str | None = None

    # Per-request override of PIPER_LENGTH_SCALE, so a beginner band can be given
    # slower speech without restarting the container.
    length_scale: float | None = Field(default=None, gt=0.1, le=3.0)


def _chunks(text: str, length_scale: float) -> Iterator[tuple[int, np.ndarray]]:
    """One int16 array per sentence, in order. Blocking; called in a worker thread."""
    from piper.config import SynthesisConfig

    voice = state.voice
    assert voice is not None  # guarded by the caller

    config = SynthesisConfig(length_scale=length_scale)
    for index, chunk in enumerate(voice.synthesize(text, syn_config=config)):
        yield index, chunk.audio_int16_array


def _wav_bytes(pcm: np.ndarray, sample_rate: int) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(CHANNELS)
        handle.setsampwidth(SAMPLE_WIDTH)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm.tobytes())
    return buffer.getvalue()


def _guard(request: SynthesiseRequest) -> None:
    """Every reason to refuse, in the order that keeps the cheapest check first."""
    if len(request.text) > MAX_CHARS:
        raise HTTPException(
            status_code=413,
            detail=f"text is {len(request.text)} characters; the limit is {MAX_CHARS}",
        )
    if not request.text.strip():
        raise HTTPException(status_code=422, detail="text is only whitespace")
    if request.voice is not None and request.voice != VOICE_NAME:
        # 400, and it names what is loaded. "unknown voice" without the alternative
        # sends somebody to the catalogue rather than to their own configuration.
        raise HTTPException(
            status_code=400,
            detail=f"this service is running {VOICE_NAME!r}, not {request.voice!r}",
        )
    if state.error is not None:
        raise HTTPException(status_code=503, detail=f"voice unavailable: {state.error}")
    if state.voice is None:
        raise HTTPException(
            status_code=503, detail=f"{VOICE_NAME} is still loading; retry shortly"
        )


# ── Endpoints ───────────────────────────────────────────────────────────────


@app.get("/health")
async def health(response: Response) -> dict[str, Any]:
    """Alive, and honest about whether it can speak yet.

    200 with `voice_loaded: false` while loading; 503 only when a load has *failed*,
    which is permanent for this process. Identical semantics to the asr service, so the
    API's /health probe can treat the two the same way.
    """
    if state.error is not None:
        response.status_code = 503
    return {
        "status": "error" if state.error else "ok",
        "voice": VOICE_NAME,
        "voice_loaded": state.voice is not None,
        "voice_source": state.source,
        "sample_rate": state.sample_rate,
        "load_seconds": state.load_seconds,
        "num_threads": NUM_THREADS or "onnxruntime default",
        "length_scale": LENGTH_SCALE,
        "error": state.error,
    }


@app.get("/voices")
async def voices() -> dict[str, Any]:
    """What this process is running, and what is on disk beside it.

    Deliberately does not fetch Piper's catalogue: /voices is a question about this
    container, and an endpoint that reaches the network to answer it would fail on the
    offline machine this whole system is built to run on.
    """
    available = sorted(
        {
            path.name.removesuffix(".onnx")
            for directory in (VOICE_DIR, BUILTIN_DIR)
            if directory.is_dir()
            for path in directory.glob("*.onnx")
            if path.with_suffix(".onnx.json").is_file()
        }
    )
    return {
        "loaded": VOICE_NAME if state.voice is not None else None,
        "available": available,
    }


@app.post("/synthesize")
async def synthesize(request: SynthesiseRequest) -> Response:
    """The whole reply as one WAV.

    Metadata travels in headers because the body is binary. The API records
    `duration_ms` and `sample_rate` on the `audio_assets` row, and — exactly as with the
    recogniser — the service that produced the audio is the authority on both, rather
    than the API re-deriving them from a header it would have to parse.
    """
    _guard(request)
    started = time.perf_counter()
    scale = request.length_scale if request.length_scale is not None else LENGTH_SCALE

    def run() -> tuple[np.ndarray, int]:
        parts = [pcm for _, pcm in _chunks(request.text, scale)]
        if not parts:
            return np.zeros(0, dtype=np.int16), 0
        return np.concatenate(parts), len(parts)

    async with _inference_slot:
        pcm, sentences = await asyncio.to_thread(run)

    if pcm.size == 0:
        # Text that phonemises to nothing — punctuation, an emoji, a stray bullet.
        # 422, because it is a fact about the request, and silently returning a WAV of
        # zero frames would give the browser something to play that is not speech.
        raise HTTPException(status_code=422, detail="text produced no speech")

    sample_rate = state.sample_rate or 0
    audio = _wav_bytes(pcm, sample_rate)
    return Response(
        content=audio,
        media_type="audio/wav",
        headers={
            "X-Voice": VOICE_NAME,
            "X-Sample-Rate": str(sample_rate),
            "X-Duration-Ms": str(round(len(pcm) / sample_rate * 1000)),
            "X-Sentences": str(sentences),
            "X-Length-Scale": str(scale),
            "X-Latency-Ms": str(round((time.perf_counter() - started) * 1000)),
        },
    )


@app.post("/synthesize/stream")
async def synthesize_stream(request: SynthesiseRequest) -> StreamingResponse:
    """One newline-delimited JSON object per sentence, as each is produced.

    **Raw PCM, base64, not a WAV per line.** A WAV per sentence would be individually
    playable and would also be the wrong shape for both consumers: the API concatenates
    the chunks into the one asset it stores, and a browser that plays a queue of
    separate `<audio>` elements gets an audible gap at every sentence boundary — it has
    to go through the Web Audio API, which wants samples, not containers. So the format
    is declared once per line and the payload is only samples.

    `latency_ms` on each line is measured from the start of the request, not from the
    previous chunk. It is time to first audio: how long the listener waited before
    hearing anything.
    """
    _guard(request)
    started = time.perf_counter()
    scale = request.length_scale if request.length_scale is not None else LENGTH_SCALE
    sample_rate = state.sample_rate or 0

    async def lines():
        queue: asyncio.Queue[str | None] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def produce() -> None:
            try:
                for index, pcm in _chunks(request.text, scale):
                    payload = {
                        "index": index,
                        "audio_b64": base64.b64encode(pcm.tobytes()).decode("ascii"),
                        "samples": int(pcm.size),
                        "duration_ms": round(pcm.size / sample_rate * 1000),
                        "sample_rate": sample_rate,
                        "sample_width": SAMPLE_WIDTH,
                        "channels": CHANNELS,
                        "latency_ms": round((time.perf_counter() - started) * 1000),
                    }
                    loop.call_soon_threadsafe(queue.put_nowait, json.dumps(payload))
            except Exception as exc:  # noqa: BLE001
                # The status line is long gone by the time synthesis fails, so the
                # failure has to travel in the body. A caller that stops at the first
                # line carrying "error" is doing the right thing; one that ignores it
                # would otherwise treat a truncated reply as a complete one.
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    json.dumps({"error": f"{type(exc).__name__}: {exc}"}),
                )
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        async with _inference_slot:
            worker = asyncio.create_task(asyncio.to_thread(produce))
            try:
                while True:
                    line = await queue.get()
                    if line is None:
                        break
                    yield line + "\n"
            finally:
                await worker

    return StreamingResponse(
        lines(),
        media_type="application/x-ndjson",
        headers={"X-Voice": VOICE_NAME, "X-Sample-Rate": str(sample_rate)},
    )
