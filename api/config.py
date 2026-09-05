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

import json
import os

# ── Application ─────────────────────────────────────────────────────────────

# Moves with `docs/changelog.md`, and the two must be bumped in the same commit. They
# drifted once already — the changelog said 0.2.0 while /health said 0.1.0 —
# which is the small version of the rule this project runs on: a number is reported by
# the thing it describes, never written down beside it.
VERSION = "0.10.0"

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

# Alembic runs migrations synchronously and psycopg2 cannot parse the `+asyncpg`
# dialect suffix. Derived rather than configured separately so the two URLs cannot
# drift apart and point at different databases.
SYNC_DATABASE_URL = DATABASE_URL.replace("+asyncpg", "")

# ── Model services ──────────────────────────────────────────────────────────
#
# Three URLs, no client objects. The API holds no weights; it holds addresses.

ASR_URL = os.environ.get("ASR_URL", "http://asr:8101")
TTS_URL = os.environ.get("TTS_URL", "http://tts:8102")
PRON_URL = os.environ.get("PRON_URL", "http://pron:8103")

MODEL_SERVICES = {"asr": ASR_URL, "tts": TTS_URL, "pron": PRON_URL}

# Ceiling for the /health probe of the three services above. They are probed
# concurrently, so this bounds all three, not each. Short on purpose: /health is what
# the container healthcheck curls, and a liveness probe that can hang is worse than no
# probe at all.
HEALTH_PROBE_TIMEOUT_S = float(os.environ.get("HEALTH_PROBE_TIMEOUT_S", "1.5"))

# ── Generation ──────────────────────────────────────────────────────────────

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
# which means torch, and torch is what this image exists without.
#
# 4.0 is not folklore here — it was measured. `tests/test_conversation_live.py` compares
# this estimate against Ollama's own `prompt_eval_count` on real assembled prompts and
# prints the error. The estimate only ever decides
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
# is small, the persona would vanish from exactly the long conversations it is for,
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

# Stream the reply out of the LLM and hand each finished sentence to the voice while the
# next one is still being written. On by default because it is the only reason the 3 s
# turn budget is reachable at all, which was measured rather than assumed.
#
# It exists as a switch rather than as the only code path so that the two can be
# measured against each other on demand (`make turn-latency`) rather than compared
# against a number somebody wrote down once.
LLM_STREAM_TO_TTS = os.environ.get("LLM_STREAM_TO_TTS", "1") != "0"

# ── Sessions ────────────────────────────────────────────────────────────────

# `GET /sessions` is paginated where `GET /scenarios` is not, and the difference is that
# this list grows. The ceiling is a ceiling on the *server*, not a suggestion to the
# client: `?limit=100000` is answered with 100, not with a query that reads a year.
SESSION_PAGE_SIZE = int(os.environ.get("SESSION_PAGE_SIZE", "20"))
SESSION_PAGE_MAX = int(os.environ.get("SESSION_PAGE_MAX", "100"))

# ── Speech synthesis ────────────────────────────────────────────────────────

# Shorter than ASR_TIMEOUT_S by an order of magnitude, and the asymmetry is the point.
# A cold recogniser is downloading 746 MB and the first transcription after a restart
# legitimately waits for it. The tts container's default voice is baked into its image,
# so it loads in under a second and there is no cold-start case to be generous about —
# a synthesis that has not returned in 30 s is a stuck process, not a slow one.
TTS_TIMEOUT_S = float(os.environ.get("TTS_TIMEOUT_S", "30"))

# The voice this system speaks with. Read here as well as by the service because the
# conversation loop records it on the turn: a reply synthesised by lessac and one synthesised by some
# later voice are different audio for the same text, and "we changed the voice in
# March" should not be something only the container's environment remembers.
PIPER_VOICE = os.environ.get("PIPER_VOICE", "en_US-lessac-medium")

# ── Pronunciation ───────────────────────────────────────────────────────────

# Generous, like ASR_TIMEOUT_S and for the same reason: a cold pron container is
# downloading 1.2 GB of wav2vec2 weights, and the first alignment after a restart waits
# for that. The *work* is not slow — 819 ms on 3.4 s of audio against a 10 000 ms
# budget, and the cost of this service is memory and image size, not latency —
# so a call that has not returned in two minutes is a stuck process, not a busy one.
PRON_TIMEOUT_S = float(os.environ.get("PRON_TIMEOUT_S", "120"))

# The GOP below which a phone is worth showing the learner, per ARPAbet symbol.
#
# **Empty by default, and that is the honest state.** The *method* is settled — set each
# threshold as a percentile of the correct-speech GOP distribution, so it carries a
# stated false-positive rate — and so is the fact that it must be per phone: consonant
# mismatches dropped ~9.0 nats where vowels dropped ~4.2, and a single global cut-off
# would either miss every vowel or drown in false positives. What is not settled is the
# numbers, because the only measurement so far had one speaker, 35 phones and 10 probes.
#
# So this map is empty until it is calibrated, and `GET /attempts/{id}` reports each
# reading's own 5th percentile rather than pretending a line exists. The −3.119 measured
# during the feasibility work is one native speaker's number and is deliberately NOT the
# default here: a threshold that looks calibrated and is not would silently decide which
# sounds a learner is told to work on.
#
# Format: PRON_GOP_THRESHOLDS='{"TH": -3.2, "IH": -1.8}'
PRON_GOP_THRESHOLDS: dict[str, float] = json.loads(
    os.environ.get("PRON_GOP_THRESHOLDS", "{}")
)

# ── Auth ────────────────────────────────────────────────────────────────────

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

# Seven days. There is no refresh token and no server-side revocation list, so
# this is the whole story: it is how long a stolen cookie stays useful, and how long
# after logout a token copied out beforehand would still verify. Shortening it without
# a refresh endpoint means signing people out mid-practice, which is the trade being
# made here in favour of the longer window.
ACCESS_TOKEN_TTL_HOURS = int(os.environ.get("ACCESS_TOKEN_TTL_HOURS", "168"))

# The token travels in an httpOnly cookie, so the frontend never reads it.
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

# ── Audio and ASR ───────────────────────────────────────────────────────────

# Where recordings live. A named Docker volume mounted here, never a bind mount and
# never a path inside the repository: a recording that can appear in `git status` is a
# recording that can end up in the history. Every path the API serves is
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

# The confidence gate, applied per word. Below this probability a word is still stored,
# still replied to and still shown, and is marked so that an error overlapping it does
# not reach an accuracy trend: a mishearing scored as a grammar error is a correction the
# speaker cannot act on, and a trend line that moves for a reason that is not them.
#
# **Per word, not per turn, and that was settled by real speech.** A stored turn scored
# 0.899 overall while containing "department" where the speaker said "the apartment";
# that word's own probability was 0.41 and 28 of its 30 neighbours were above 0.69. The
# turn score is the mean of the per-word scores, so a locally wrong word is averaged away
# and no turn-level threshold can reach it.
#
# **0.60 is a placeholder, not a finding.** Across the whole stored corpus it marks 10.3 %
# of words (28 of 272), and most of those are transcribed correctly — it is a wide net,
# not a precise instrument. Calibrating it needs learner speech with a reference
# transcript, which this project does not yet have.
ASR_CONFIDENCE_FLOOR = float(os.environ.get("ASR_CONFIDENCE_FLOOR", "0.60"))


# ── Analysis (grammar, errors, fluency) ─────────────────────────────────────

# The parser behind deterministic grammar usage. The small English pipeline: ~12 MB of
# model, no torch, and the only component this system asks for is the dependency parse
# and morphology. A larger pipeline would buy accuracy on entities and coreference, which
# nothing here reads.
SPACY_MODEL = os.environ.get("SPACY_MODEL", "en_core_web_sm")

# What counts as a pause. Gaps below this are treated as continuous speech, because word
# boundaries out of the recogniser are accurate to a few tens of milliseconds and summing
# every small gap would measure its timestamp granularity rather than the speaker.
#
# 250 ms is the conventional boundary in the fluency literature and is used unchanged
# here. It is one number feeding three metrics — articulation rate, pause ratio and mean
# length of run — so they cannot disagree about what a pause is.
FLUENCY_PAUSE_MS = int(os.environ.get("FLUENCY_PAUSE_MS", "250"))

# The reply budget for one turn's error labelling. Larger than the conversational cap
# because the answer is JSON carrying a quote and a correction per error, and a truncated
# JSON object is a whole turn's analysis lost rather than a sentence cut short.
ANALYSIS_MAX_TOKENS = int(os.environ.get("ANALYSIS_MAX_TOKENS", "800"))

# Zero, and it is not a tuning preference. Labelling is a measurement: the same utterance
# must produce the same errors on a re-run, or re-running a backfill would rewrite a
# learner's history. A conversation keeps the provider's own default, where variety is
# the point.
ANALYSIS_TEMPERATURE = float(os.environ.get("ANALYSIS_TEMPERATURE", "0"))

# The longest quote that can be an error. A model asked to point at a mistake will quote
# the whole sentence given the chance, and a whole-sentence quote is three problems at
# once: an underline nobody can read, a span that collides with every other error in the
# turn, and — covering more words — one far likelier to touch a word the recogniser was
# unsure of and be kept out of the trend it belonged in. Longer proposals are refused and
# counted, so the cost of the rule is visible rather than assumed.
ERROR_MAX_SPAN_WORDS = int(os.environ.get("ERROR_MAX_SPAN_WORDS", "12"))

# Below this self-reported confidence an error is stored and shown but kept out of
# accuracy trends. It is the model's own number and it is not calibrated — a 4B model
# asked how sure it is answers 0.9 most of the time — so this floor is deliberately low.
# Its job is to catch the proposals the model itself hedged on, not to rank the rest.
ERROR_CONFIDENCE_FLOOR = float(os.environ.get("ERROR_CONFIDENCE_FLOOR", "0.50"))

# How many turns one backfill pass claims at a time. Small because each turn is a model
# call of a second or more, and a crash halfway through a large batch should cost one
# batch of work, not all of it.
ANALYSIS_BATCH_SIZE = int(os.environ.get("ANALYSIS_BATCH_SIZE", "20"))

# How long ending a session will wait for the analysis of its own turns before writing
# the report without them. Analysis runs behind each turn, so by the time somebody stops
# talking the only outstanding turn is usually the last one — a second or two.
#
# The budget exists for the case where it is not: a session recorded while the labelling
# model was down has every turn outstanding, and an unbounded wait would turn "end the
# session" into a request that hangs for minutes. A report written short says how many
# turns it is missing, and ending the session again picks up where it left off.
ANALYSIS_SESSION_BUDGET_S = float(os.environ.get("ANALYSIS_SESSION_BUDGET_S", "60"))


# ── Progress (rollups, trends, recommendations) ─────────────────────────────

# How far back the progress page looks. Thirty days is what "am I getting better"
# usually means to somebody practising a few times a week — long enough to hold several
# sessions, short enough that a month of neglect is visible as a gap rather than
# averaged into the line.
PROGRESS_TREND_DAYS = int(os.environ.get("PROGRESS_TREND_DAYS", "30"))

# Words a speaker has to produce in one period before that period gets a point on a
# fluency or accuracy chart. Both are rates per unit of speech, and a rate over eleven
# words is arithmetic rather than measurement: one filler in a short answer is 9 per 100
# words, which would draw a spike the speaker cannot see in themselves and cannot act on.
PROGRESS_MIN_WORDS = int(os.environ.get("PROGRESS_MIN_WORDS", "50"))

# Scored readings before any per-phone trend is shown at all. Pronunciation scores move
# with the microphone, the room and the distance from it, so the first few readings
# describe the setup as much as the speaker.
PROGRESS_MIN_ATTEMPTS = int(os.environ.get("PROGRESS_MIN_ATTEMPTS", "5"))

# And instances of one phone within a period before that phone gets a point. A passage
# engineered around one sound yields it thirty times; a phone that turned up twice is a
# sample of two, whatever the surrounding reading was worth.
PROGRESS_MIN_PHONE_SAMPLES = int(os.environ.get("PROGRESS_MIN_PHONE_SAMPLES", "5"))

# Points on a series before a *direction* is claimed. The points themselves are drawn as
# soon as they exist — hiding a measurement is its own dishonesty — but "improving" over
# two of them is a line through noise, and it is the sentence a learner would act on.
PROGRESS_MIN_POINTS = int(os.environ.get("PROGRESS_MIN_POINTS", "3"))

# How far back the pronunciation baseline reaches. Every phone score is expressed as a
# distance from this speaker's own recent history rather than as a raw value, because a
# raw value compares them against a microphone. Ninety days is long enough to survive a
# fortnight away and short enough that a year-old recording does not anchor today's.
PROGRESS_BASELINE_DAYS = int(os.environ.get("PROGRESS_BASELINE_DAYS", "90"))

# How many things to suggest practising next. Three: a list long enough to offer a
# choice and short enough that every entry has a measured reason worth reading.
RECOMMEND_LIMIT = int(os.environ.get("RECOMMEND_LIMIT", "3"))
