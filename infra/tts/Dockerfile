# The TTS service. One voice, two endpoints, no orchestration.
#
# Build context is this directory, not the repository root, for the same reason as
# infra/asr: nothing here needs anything from the rest of the tree, and editing a router
# in api/ should not invalidate this image's cache.
FROM python:3.12.14-slim-trixie

# The security fixes Debian has published since the base image was built, and no package
# added: the health check is a line of Python, and there is deliberately no espeak-ng —
# piper-tts carries the phonemiser as a compiled extension and its own data directory, so
# installing the Debian one would add a second espeak whose version this file does not
# control.
RUN apt-get update \
    && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/*

# The same unprivileged account, with the same id, in every image that shares the
# model_cache volume, so a file one service downloads the others can read and replace.
# /models is created here and owned by that account, so a new volume mounted over it
# starts out writable.
RUN groupadd --system --gid 10001 speaklab \
    && useradd --system --uid 10001 --gid speaklab --create-home speaklab \
    && mkdir /models \
    && chown speaklab:speaklab /models

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# The default voice is baked into the image, and this is the one place this system does
# that rather than mounting weights from the shared volume. The reason is size: a Piper
# voice is 63 MB, where Whisper small.en is 746 MB and wav2vec2 is ~2 GB. At 63 MB the
# download belongs in a layer that is built once and cached, and the alternative — a
# first request that blocks for a download — is a cold first turn, which is the worst
# possible first impression for a conversation product.
#
# A voice OTHER than this one is still fetched at runtime into the shared model_cache
# volume and cached there across rebuilds (FR-28). app.py resolves in that order.
ARG PIPER_VOICE=en_US-lessac-medium
ENV PIPER_BUILTIN_VOICE_DIR=/opt/piper-voices
RUN python -m piper.download_voices "${PIPER_VOICE}" \
    --download-dir "${PIPER_BUILTIN_VOICE_DIR}"

COPY app.py .

USER speaklab

EXPOSE 8102

# The default voice is in the image, so the start period covers process start rather
# than a download.
HEALTHCHECK --interval=15s --timeout=5s --retries=5 --start-period=60s \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8102/health', timeout=4)"]

# One worker, for the same reason as asr: the voice is loaded once per process and
# onnxruntime is already given every thread it can use. A second worker doubles the
# resident voice and halves the threads each copy gets.
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8102"]
