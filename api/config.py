"""Environment-derived settings.

Plain module-level constants read from `os.environ`, not a settings class. They are
read once at import and every one has a working default — a `BaseSettings` subclass
would add a dependency and a layer of indirection to `os.environ.get` with a fallback.
(An earlier version of this docstring counted them. It was wrong by the end of the next
milestone, which is a small demonstration of why a number belongs in something that
runs rather than in prose beside it.)

Every default here is the value that works on a laptop with nothing else running. A
fresh clone starts with `cp .env.example .env && make up` and no editing.
"""

import os

# ── Application ─────────────────────────────────────────────────────────────

# Moves with `docs/changelog.md`, and the two must be bumped in the same commit. They
# had already drifted by the end of m2 — the changelog said 0.2.0 while /health said
# 0.1.0 — which is a small instance of exactly what invariant I9 is about: a number
# that is written down rather than reported by the thing it describes.
VERSION = "0.6.0"

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

# How long Ollama keeps the weights resident after a call. Its own default is five
# minutes, which is short enough that a user who stops to think for six pays the model
# load again — measured at ~2.6 s on this machine, against a 3 s budget for the whole
# turn. Ten minutes covers a pause without pinning 3.3 GB of host RAM indefinitely.
#
# Host RAM, not container RAM: the PRD's 8 GB ceiling is for the Compose stack and
# explicitly excludes the host's Ollama, so this trades memory the ceiling does not
# count for latency the budget does.
OLLAMA_KEEP_ALIVE = os.environ.get("OLLAMA_KEEP_ALIVE", "10m")

# Ceilings, not targets. A prompt-assembly bug shows up here as a refused request
# rather than as a five-minute turn.
LLM_TIMEOUT_S = float(os.environ.get("LLM_TIMEOUT_S", "120"))
LLM_MAX_INPUT_TOKENS = int(os.environ.get("LLM_MAX_INPUT_TOKENS", "4000"))
LLM_MAX_OUTPUT_TOKENS = int(os.environ.get("LLM_MAX_OUTPUT_TOKENS", "400"))

# Characters per token, used to size a prompt *before* sending it. There is no Gemma
# tokenizer in this image and there is not going to be one: it would mean transformers,
# which means torch, which is exactly what invariant I5 keeps out of the API.
#
# 4.0 is not folklore here — it was measured. `tests/test_conversation_live.py` compares
# this estimate against Ollama's own `prompt_eval_count` on real assembled prompts and
# prints the error; decision 0003 records what it was. The estimate only ever decides
# *what to send*, never what is reported: `turns.prompt_tokens` stores the count Ollama
# returned, so a drifting constant shows up as a widening gap between two stored numbers
# rather than as a silently over-full context.
LLM_CHARS_PER_TOKEN = float(os.environ.get("LLM_CHARS_PER_TOKEN", "4.0"))

# How far that estimate is allowed to be wrong before the context window is at risk,
# expressed as a multiplier and **measured rather than assumed**. Characters per token is
# not a constant of the language, it is a property of the text: on 2026-08-30 the same
# estimator over-counted a long conversational history by 5.7 %, under-counted a
# persona-sized block of repeated instructions by 8.9 %, and under-counted a one-line
# greeting by 41 % — where the absolute error was seven tokens and did not matter.
#
# 1.25 covers all of that with room left, and `test_conversation_live.py` asserts that it
# still does against the live model. It is not a fudge factor: it is what turns a
# heuristic into a bound, and the bound is what LLM_NUM_CTX is sized from.
LLM_ESTIMATOR_MARGIN = float(os.environ.get("LLM_ESTIMATOR_MARGIN", "1.25"))

# The context window to ask Ollama for, and the one option here that is not a
# preference. **Ollama does not refuse a prompt that does not fit — it silently
# discards half the context and answers anyway.** Measured on 2026-08-30, gemma3:4b,
# Ollama 0.33.1:
#
#     prompt ~3935 tokens, num_ctx 4096  ->  prompt_eval_count 3935   intact
#     prompt ~4200 tokens, num_ctx 4096  ->  prompt_eval_count 2051   half of it gone
#
# There is no error, no warning and no field in the response that says it happened; the
# reply comes back 200 and reads perfectly well. The discarded half is the *front* of
# the conversation, which is where a system message lives — so on a host whose default
# is small, the persona would vanish from exactly the long conversations R7 is about,
# and the symptom would be "the AI drifts out of character after turn twelve".
#
# So the window is stated rather than inherited, and it is the whole budget **scaled by
# the measured error of the thing that enforces the budget**, plus the reply. A window of
# exactly input + output would be right only if the estimator were exact, and it is not:
# an 8.9 % under-count on a 4000-token budget is 356 tokens past the edge, and the edge
# costs half the prompt. `services/conversation.py` keeps the assembled prompt under
# LLM_MAX_INPUT_TOKENS; this margin is what makes that guarantee survive the estimator
# being wrong in the dangerous direction.
LLM_NUM_CTX = int(
    os.environ.get(
        "LLM_NUM_CTX",
        str(round(LLM_MAX_INPUT_TOKENS * LLM_ESTIMATOR_MARGIN) + LLM_MAX_OUTPUT_TOKENS),
    )
)

# The digest is prose, and prose given no ceiling grows until it is the context problem
# it was written to solve. Roughly 200 tokens of running summary.
LLM_DIGEST_MAX_TOKENS = int(os.environ.get("LLM_DIGEST_MAX_TOKENS", "200"))

# When the history has filled this fraction of its share of the budget, fold the oldest
# turns into the digest. Below 1.0 on purpose, and the gap is the design: at the mark
# every turn still fits, so the fold is preparation for the next turn rather than a
# rescue for this one — which is what lets it run *after* the reply has been sent
# instead of while somebody is waiting for it.
LLM_HISTORY_HIGH_WATER = float(os.environ.get("LLM_HISTORY_HIGH_WATER", "0.7"))

# PRD §9.1's first prescribed fallback: stream the reply out of the LLM and hand each
# finished sentence to the voice while the next one is still being written. On by
# default because it is the only reason the 3 s turn budget is reachable at all —
# measured at m6, and the whole of decision 0003 §3.
#
# It exists as a switch rather than as the only code path so that the two can be
# measured against each other on demand (`make turn-latency`) rather than compared
# against a number somebody wrote down once.
LLM_STREAM_TO_TTS = os.environ.get("LLM_STREAM_TO_TTS", "1") != "0"

# ── Sessions (m6) ───────────────────────────────────────────────────────────

# `GET /sessions` is paginated where `GET /scenarios` is not, and the difference is that
# this list grows. The ceiling is a ceiling on the *server*, not a suggestion to the
# client: `?limit=100000` is answered with 100, not with a query that reads a year.
SESSION_PAGE_SIZE = int(os.environ.get("SESSION_PAGE_SIZE", "20"))
SESSION_PAGE_MAX = int(os.environ.get("SESSION_PAGE_MAX", "100"))

# ── Speech synthesis (m5) ───────────────────────────────────────────────────

# Shorter than ASR_TIMEOUT_S by an order of magnitude, and the asymmetry is the point.
# A cold recogniser is downloading 746 MB and the first transcription after a restart
# legitimately waits for it. The tts container's default voice is baked into its image,
# so it loads in under a second and there is no cold-start case to be generous about —
# a synthesis that has not returned in 30 s is a stuck process, not a slow one.
TTS_TIMEOUT_S = float(os.environ.get("TTS_TIMEOUT_S", "30"))

# The voice this system speaks with. Read here as well as by the service because m6
# records it on the turn: a reply synthesised by lessac and one synthesised by some
# later voice are different audio for the same text, and "we changed the voice in
# March" should not be something only the container's environment remembers.
PIPER_VOICE = os.environ.get("PIPER_VOICE", "en_US-lessac-medium")

# ── Auth (m3) ───────────────────────────────────────────────────────────────

# The signing key, and the one constant here whose default is not simply "the value that
# works on a laptop" — it is also a value that must never reach a deployment. It is a
# fixed string rather than a fresh `secrets.token_hex()` per process on purpose. A random
# default looks safer and behaves worse: every restart would silently invalidate every
# cookie, and under more than one worker each worker would sign with a different key, so
# a user would be logged out on roughly (n-1)/n of their requests with nothing in the
# logs to explain it. A fixed sentinel is at least detectable, and `main.py` logs a
# warning at startup whenever it is in use.
DEV_JWT_SECRET = "dev-only-secret-change-before-this-leaves-the-laptop"

# `or`, not a `.get` default. Compose passes an unset `${JWT_SECRET:-}` through as an
# empty string, and `os.environ.get("JWT_SECRET", DEV_JWT_SECRET)` would return that
# empty string — signing every token with a zero-length key and, worse, skipping the
# startup warning below, because "" is not the sentinel. Blank means absent.
JWT_SECRET = os.environ.get("JWT_SECRET") or DEV_JWT_SECRET
JWT_SECRET_IS_DEV = JWT_SECRET == DEV_JWT_SECRET

# HS256, not RS256. One service signs and the same service verifies, so an asymmetric
# key pair would add key distribution to solve a problem this system does not have.
JWT_ALGORITHM = "HS256"

# Seven days. There is no refresh token and no server-side revocation list (D24), so
# this is the whole story: it is how long a stolen cookie stays useful, and how long
# after logout a token copied out beforehand would still verify. Shortening it without
# a refresh endpoint means signing people out mid-practice, which is the trade being
# made here in favour of the longer window.
ACCESS_TOKEN_TTL_HOURS = int(os.environ.get("ACCESS_TOKEN_TTL_HOURS", "168"))

# The token travels in an httpOnly cookie, so the frontend never reads it (D24).
SESSION_COOKIE_NAME = "speaklab_session"

# False by default because the laptop stack is http://localhost — a `Secure` cookie
# would be set by the API, dropped by the browser, and the only symptom would be a
# login that appears to succeed and a /auth/me that 401s. Set COOKIE_SECURE=1 wherever
# there is TLS.
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "0") == "1"

# `lax` works for localhost:3003 -> localhost:8002 because SameSite is computed on the
# registrable domain and ignores the port: those two origins are the same *site*. It
# also works for app.example.com -> api.example.com. It does NOT work across genuinely
# different domains, which needs `none` and therefore also `secure`.
COOKIE_SAMESITE = os.environ.get("COOKIE_SAMESITE", "lax")

# ── Audio and ASR (m4) ──────────────────────────────────────────────────────

# Where recordings live. A named Docker volume mounted here, never a bind mount and
# never a path inside the repository: a recording that can appear in `git status` is a
# recording that can end up in the history (trap 4). Every path the API serves is
# resolved and checked to be inside this directory before a byte is read.
AUDIO_ROOT = os.environ.get("AUDIO_ROOT", "/audio")

# 10 MB. A conversational turn is seconds and a read-aloud passage is under a minute;
# at 16 kHz mono this is roughly five minutes of uncompressed WAV and far more of
# anything the browser actually sends. The asr service enforces its own, higher ceiling
# — two limits because the API's is a product decision and the service's is a bound on
# damage from anything that reaches it.
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))

# Long, on purpose, and not the same number as HEALTH_PROBE_TIMEOUT_S. A cold asr
# container is downloading or loading weights, and the first transcription after a
# restart waits for that. The health probe is what must stay fast; this is the working
# call, and failing it early would turn a slow start into a lost recording.
ASR_TIMEOUT_S = float(os.environ.get("ASR_TIMEOUT_S", "120"))

# Below this mean per-word probability, a turn is still stored, still replied to, and
# still shown — and is flagged so that m9 keeps it out of accuracy trends. PRD §7.5 and
# R2: a mishearing scored as a grammar error is a correction the speaker cannot act on,
# and a trend line that moves for a reason that is not them.
#
# **0.60 is a placeholder, not a finding**, in the same sense as the five-attempt gate in
# Q5. Nothing has yet measured where learner speech actually sits on this scale — the
# golden set is clean read speech by native speakers, which is the wrong distribution to
# calibrate against. m9 has the labelled corpus that can answer it; until then this
# number's only job is to exist, be visible, and be wrong in public rather than in
# private. See handoff Q11.
ASR_CONFIDENCE_FLOOR = float(os.environ.get("ASR_CONFIDENCE_FLOOR", "0.60"))
