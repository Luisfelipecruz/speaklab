# The ASR service. One model, one endpoint, no orchestration.
#
# Build context is this directory, not the repository root (docker-compose.yml), because
# nothing here needs anything from the rest of the tree. That is also what keeps the
# build cache useful: editing a router in api/ does not invalidate this image.
FROM python:3.12-slim

# curl is what the compose healthcheck runs. There is deliberately no ffmpeg package:
# PyAV carries the ffmpeg libraries itself, which saves roughly 200 MB of Debian
# multimedia dependencies and removes a subprocess from the hot path.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

# Weights live on the shared model_cache volume, not in the image. An image carrying
# 500 MB of weights would have to be rebuilt to change model size, and every developer
# would download them again on every `docker compose build`.
ENV HF_HOME=/models

EXPOSE 8101

# One worker. The model is loaded once per process and CTranslate2 already uses every
# core it is given; a second worker would double the memory and halve the threads.
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8101"]
