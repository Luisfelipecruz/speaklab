# The ASR service. One model, one endpoint, no orchestration.
#
# Build context is this directory, not the repository root (docker-compose.yml), because
# nothing here needs anything from the rest of the tree. That is also what keeps the
# build cache useful: editing a router in api/ does not invalidate this image.
FROM python:3.12.14-slim-trixie

# The security fixes Debian has published since the base image was built, and no package
# added: the health check is a line of Python, and there is deliberately no ffmpeg —
# PyAV carries the ffmpeg libraries itself, which saves roughly 200 MB of Debian
# multimedia dependencies and removes a subprocess from the hot path.
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

COPY app.py .

# Weights live on the shared model_cache volume, not in the image. An image carrying
# 500 MB of weights would have to be rebuilt to change model size, and every developer
# would download them again on every `docker compose build`.
ENV HF_HOME=/models

USER speaklab

EXPOSE 8101

# /health answers 200 with `model_loaded: false` while the weights download, so a cold
# start is healthy; the long start period covers the download on a first run.
HEALTHCHECK --interval=15s --timeout=5s --retries=5 --start-period=180s \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8101/health', timeout=4)"]

# One worker. The model is loaded once per process and CTranslate2 already uses every
# core it is given; a second worker would double the memory and halve the threads.
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8101"]
