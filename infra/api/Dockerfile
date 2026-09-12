# The API image, in three stages. `runtime` is what the api service runs. `test` is the
# same installed dependencies with the test and lint tools added, so the suite runs
# against exactly the libraries the API runs with.
#
# Build context is the REPOSITORY ROOT, not this directory — see docker-compose.yml.
# That is what lets the image carry api/ and run without a bind mount. .dockerignore at
# the root keeps the context to a few hundred kilobytes.
FROM python:3.12.14-slim-trixie AS deps

# The security fixes Debian has published since the base image was built, and no package
# added: the health check below is a line of Python, not curl.
RUN apt-get update \
    && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Requirements before source, so editing a router does not re-run pip.
COPY infra/api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


# ── test: the suite and the linters ─────────────────────────────────────────
#
# Runs as root. `make fmt` rewrites the bind-mounted source in place and the measurement
# suites write into .eval/, and on a Linux host both belong to whoever cloned the
# repository, not to an account inside the image.
FROM deps AS test

COPY infra/api/requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements-dev.txt

COPY api/ .


# ── runtime: what the api service runs ──────────────────────────────────────
#
# Last, so a build that names no target gets this one.
FROM deps AS runtime

# An unprivileged account with a fixed id. The id is fixed because the audio volume
# outlives the image, and a rebuilt image has to own the files the last one wrote. /audio
# is created here and owned by that account, so a new named volume mounted over it starts
# out writable.
RUN groupadd --system --gid 10001 speaklab \
    && useradd --system --uid 10001 --gid speaklab --create-home speaklab \
    && mkdir /audio \
    && chown speaklab:speaklab /audio

# api/ becomes /app, so imports are `from config import ...` rather than
# `from api.config import ...`. api/tests/conftest.py puts the same directory on
# sys.path when the suite runs on a host, so a test that passes there passes here.
COPY api/ .

USER speaklab

EXPOSE 8000

# /health answers 200 while every model service is unreachable and 503 only when the
# database is gone, the one condition that makes this container useless. urlopen raises
# on anything but a 2xx, and the exception is the non-zero exit.
HEALTHCHECK --interval=10s --timeout=5s --retries=3 --start-period=20s \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=4)"]

# No --reload: docker-compose.yml adds it for development, where ./api is bind-mounted
# over this copy.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
