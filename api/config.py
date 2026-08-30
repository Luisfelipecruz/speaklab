"""Environment-derived settings.

Plain module-level constants read from `os.environ`, not a settings class. There are
fourteen of them, they are read once at import, and every one has a working default —
a `BaseSettings` subclass would add a dependency and a layer of indirection to
`os.environ.get` with a fallback.

Every default here is the value that works on a laptop with nothing else running. A
fresh clone starts with `cp .env.example .env && make up` and no editing.
"""

import os

# ── Application ─────────────────────────────────────────────────────────────

VERSION = "0.1.0"

# Which origins may call the API from a browser. The frontend is on 3003 (not 3000 —
# the ports are offset so this stack runs alongside the others on this machine).
CORS_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("CORS_ORIGINS", "http://localhost:3003").split(",")
    if origin.strip()
]

# ── Database ────────────────────────────────────────────────────────────────

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://speaklab:speaklab_dev@localhost:5433/speaklab",
)

# Alembic (m2) runs migrations synchronously and psycopg2 cannot parse the `+asyncpg`
# dialect suffix. Derived rather than configured separately so the two URLs cannot
# drift apart and point at different databases.
SYNC_DATABASE_URL = DATABASE_URL.replace("+asyncpg", "")

# ── Model services ──────────────────────────────────────────────────────────
#
# Three URLs, no client objects. The API holds no weights (I5); it holds addresses.

ASR_URL = os.environ.get("ASR_URL", "http://asr:8101")
TTS_URL = os.environ.get("TTS_URL", "http://tts:8102")
PRON_URL = os.environ.get("PRON_URL", "http://pron:8103")

MODEL_SERVICES = {"asr": ASR_URL, "tts": TTS_URL, "pron": PRON_URL}

# Ceiling for the /health probe of the three services above. They are probed
# concurrently, so this bounds all three, not each. Short on purpose: /health is what
# the container healthcheck curls, and a liveness probe that can hang is worse than no
# probe at all.
HEALTH_PROBE_TIMEOUT_S = float(os.environ.get("HEALTH_PROBE_TIMEOUT_S", "1.5"))

# ── Generation (m6) ─────────────────────────────────────────────────────────

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gemma3:4b")

# Ceilings, not targets. A prompt-assembly bug shows up here as a refused request
# rather than as a five-minute turn.
LLM_TIMEOUT_S = float(os.environ.get("LLM_TIMEOUT_S", "120"))
LLM_MAX_INPUT_TOKENS = int(os.environ.get("LLM_MAX_INPUT_TOKENS", "4000"))
LLM_MAX_OUTPUT_TOKENS = int(os.environ.get("LLM_MAX_OUTPUT_TOKENS", "400"))
