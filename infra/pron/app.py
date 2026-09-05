"""SpeakLab pronunciation — audio plus the text it was meant to be, per-phone GOP out.

The only service whose *method* had to be proved before it was worth writing: a
forced-alignment pipeline with a wrong phone map returns confident numbers that measure
nothing, and nothing downstream can tell.

What it does, in order: decode whatever the browser recorded to 16 kHz mono, convert the
reference text to canonical ARPAbet phones with sentence context intact, map those to the
acoustic model's own eSpeak vocabulary, force-align, and report GOP per phone together
with the phone that actually won each segment.

Like `asr` and `tts` it holds no database connection, no user identity and no notion of a
session, and it is reachable only from inside the compose network. There is no auth here
and that is not an oversight.

**It is profiled — `docker compose --profile pron up -d`.** This is the only image with
torch in it, about 2 GB, and the stack has to stay usable by someone who never wants to
download that. With it down, `POST /attempts` still returns a transcript and a WER; the
phoneme scores report `unavailable` rather than failing the request.
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any

import av
import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, Response, UploadFile

import gop as gop_module
import phone_map as pm
from g2p import TextAlignmentError, words_with_phones

log = logging.getLogger("speaklab.pron")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# ── Settings ────────────────────────────────────────────────────────────────

MODEL_NAME = os.environ.get("PRON_MODEL", "facebook/wav2vec2-lv-60-espeak-cv-ft")

# 25 MB, matching asr. A read-aloud passage is under a minute of speech; this is a bound
# on damage rather than a product limit, and the API enforces its own lower one.
MAX_UPLOAD_BYTES = int(os.environ.get("PRON_MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))

# Serialised for the same reason asr is: the forward pass is CPU-bound and torch is
# already using every core. Two concurrent scorings do not finish sooner, they finish
# together and later.
_inference_slot = asyncio.Semaphore(int(os.environ.get("PRON_MAX_CONCURRENCY", "1")))

TARGET_SAMPLE_RATE = gop_module.SAMPLE_RATE

# A passage is ~79 words. This ceiling is about ten times that and exists so that a
# malformed request cannot ask for an alignment whose cost is quadratic in nothing
# useful.
MAX_TEXT_CHARS = int(os.environ.get("PRON_MAX_TEXT_CHARS", "4000"))


# ── Loading ─────────────────────────────────────────────────────────────────
#
# Weights and the CMU dictionary both load in a background thread while /health answers
# throughout. A cold start downloads 1.2 GB, and a health endpoint that does not answer
# until that finishes is indistinguishable from a crash to everything watching it.


class _State:
    def __init__(self) -> None:
        self.model: Any | None = None
        self.g2p: Any | None = None
        self.error: str | None = None
        self.load_seconds: float | None = None


state = _State()


def _verify_vocabulary(model) -> None:
    """The vendored vocabulary must still be the model's own.

    `phone_map` asserts its table against `/app/vocab.json` at import, which catches a
    bad *map*. This catches the other direction: a vendored file that has drifted from
    the weights actually loaded — a changed model id, a rebuilt image against a moved
    upstream — where every symbol still resolves and every id now means a different
    sound. It is the failure mode with no symptom, so it gets an explicit check.
    """
    declared = int(getattr(model.config, "vocab_size", 0))
    if declared and declared != len(pm.VOCAB):
        raise RuntimeError(
            f"{MODEL_NAME} has {declared} output classes but the vendored vocabulary "
            f"has {len(pm.VOCAB)} tokens. The image's vocab.json does not belong to "
            f"these weights; every phone id would be wrong. Rebuild the image."
        )


def _load() -> None:
    started = time.perf_counter()
    log.info("loading %s and the CMU dictionary", MODEL_NAME)
    try:
        from g2p_en import G2p
        from transformers import Wav2Vec2ForCTC

        model = Wav2Vec2ForCTC.from_pretrained(MODEL_NAME).eval()
        _verify_vocabulary(model)
        g2p = G2p()
        # One conversion now, so the first real request does not pay for the tagger's
        # own lazy initialisation and so a missing corpus fails here rather than there.
        g2p("the quick brown fox")
    except Exception as exc:  # noqa: BLE001 - reported, not raised into a dead thread
        state.error = f"{type(exc).__name__}: {exc}"
        log.error("load failed: %s", state.error)
        return

    state.load_seconds = round(time.perf_counter() - started, 2)
    state.model = model
    state.g2p = g2p
    log.info("loaded in %.2fs — %s", state.load_seconds, pm.summary())


@asynccontextmanager
async def lifespan(_: FastAPI):
    loader = asyncio.create_task(asyncio.to_thread(_load))
    yield
    loader.cancel()


app = FastAPI(
    title="SpeakLab pronunciation",
    description="Forced alignment and per-phoneme Goodness of Pronunciation.",
    version="1.0.0",
    lifespan=lifespan,
)


# ── Decoding ────────────────────────────────────────────────────────────────


class MediaError(Exception):
    """The bytes are not audio this service can decode. A 422, never a 500."""


def decode(data: bytes) -> tuple[np.ndarray, dict[str, Any]]:
    """Whatever arrived → 16 kHz mono float32, plus what it was before.

    The same decode as `infra/asr/app.py`, and deliberately a copy rather than a shared
    module: these are separate images with separate dependency sets, and the alternative
    to forty duplicated lines is a shared build context that couples a 2 GB image's cache
    to a 200 MB one's.
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
            # The resampler buffers; without the flush the tail of every recording is
            # silently missing.
            for resampled in resampler.resample(None):
                chunks.append(resampled.to_ndarray().reshape(-1))
        except Exception as exc:  # noqa: BLE001
            raise MediaError(f"cannot decode audio: {type(exc).__name__}") from exc

    pcm = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.int16)
    source["duration_ms"] = round(len(pcm) / TARGET_SAMPLE_RATE * 1000)
    # 32768 rather than 32767: it is the magnitude of the most negative int16 and the
    # only divisor that cannot clip.
    return pcm.astype(np.float32) / 32768.0, source


# ── Endpoints ───────────────────────────────────────────────────────────────


@app.get("/health")
async def health(response: Response) -> dict[str, Any]:
    """Alive, and honest about whether it can score anything yet.

    200 with `model_loaded: false` while 1.2 GB comes down — a cold start must not read
    as a crash. 503 only when the load has *failed*, which is permanent: this process
    will never return a score, and the API's /health should report it as `error` (up and
    unwell) rather than `unreachable` (absent).
    """
    if state.error is not None:
        response.status_code = 503
    return {
        "status": "error" if state.error else "ok",
        "model": MODEL_NAME,
        "model_loaded": state.model is not None,
        "load_seconds": state.load_seconds,
        "vocabulary_tokens": len(pm.VOCAB),
        "arpabet_phones": len(pm.ARPABET_TO_IPA),
        "error": state.error,
    }


@app.post("/score")
async def score(
    file: UploadFile = File(...), text: str = Form(...)
) -> dict[str, Any]:
    """One reading of one passage → GOP for every canonical phone in it."""
    data = await file.read()

    if not data:
        raise HTTPException(status_code=422, detail="empty upload")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"upload is {len(data)} bytes; the limit is {MAX_UPLOAD_BYTES}",
        )
    if not text.strip():
        raise HTTPException(status_code=422, detail="no reference text")
    if len(text) > MAX_TEXT_CHARS:
        raise HTTPException(
            status_code=413,
            detail=f"reference text is {len(text)} characters; the limit is {MAX_TEXT_CHARS}",
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
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if source["duration_ms"] == 0:
        raise HTTPException(status_code=422, detail="decoded to zero samples")

    # G2P before the semaphore: it is milliseconds and it is the failure most likely to
    # be the caller's fault, so it should not queue behind somebody else's forward pass.
    try:
        words = await asyncio.to_thread(words_with_phones, text, state.g2p)
    except TextAlignmentError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except pm.PhoneMapError as exc:
        # Not the caller's fault and not a bad recording: the text contains a phone this
        # service cannot map. A 500, because it is a defect in this image.
        log.error("phone map gap on %r: %s", text[:60], exc)
        raise HTTPException(status_code=500, detail=f"phone map gap: {exc}") from exc

    async with _inference_slot:
        try:
            rows = await asyncio.to_thread(
                gop_module.score, state.model, audio, words
            )
        except gop_module.AlignmentError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {
        "phones": rows,
        "summary": gop_module.summarise(rows),
        "words": len(words),
        "source": source,
        "model": MODEL_NAME,
        "latency_ms": round((time.perf_counter() - started) * 1000),
    }
