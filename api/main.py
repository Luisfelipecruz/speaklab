"""SpeakLab API — the only orchestrator in the system.

Everything that is not a model runs here: audio normalisation, the deterministic
fluency and grammar metrics, the conversation loop, the progress rollups. The models
run in `asr`, `tts` and `pron`, and this image contains none of their weights and no
torch. That separation is what lets this container start in a couple of seconds, and its
size is worth re-measuring rather than quoting the next time it is claimed.

Routers are registered explicitly, one line each, as their milestones land. There is no
auto-discovery: a router that fails to import should break startup loudly rather than
disappear from the OpenAPI schema with nothing in the logs.
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import CORS_ORIGINS, JWT_SECRET_IS_DEV, VERSION
from routers.answers import router as answers_router
from routers.attempts import router as attempts_router
from routers.audio import router as audio_router
from routers.auth import router as auth_router
from routers.drills import router as drills_router
from routers.grammar import router as grammar_router
from routers.health import router as health_router
from routers.passages import router as passages_router
from routers.progress import router as progress_router
from routers.scenarios import router as scenarios_router
from routers.sessions import router as sessions_router
from routers.turns import router as turns_router

app = FastAPI(
    title="SpeakLab",
    description=(
        "Practise spoken English against local models. Scenario role-play, read-aloud "
        "pronunciation scoring with per-phoneme GOP, and measurable progress over time."
    ),
    version=VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(scenarios_router)
app.include_router(passages_router)
app.include_router(audio_router)
app.include_router(sessions_router)
# After sessions, and it matters: both routers carry the /sessions prefix, and FastAPI
# matches in registration order. `POST /sessions/{id}/turns` and `POST /sessions/{id}/end`
# cannot collide — the literal segments differ — but registering the more specific router
# first would put the endpoint the product is about above the CRUD it belongs to in the
# OpenAPI schema, which is a worse table of contents than it is a routing decision.
app.include_router(turns_router)

# Read-aloud. A sibling of the conversation loop rather than a child of it: an attempt
# belongs to a session, but it is addressed by its own id because the client polls it,
# and `/sessions/{id}/attempts/{id}` would make a poll carry a session id the poller has
# no other use for.
app.include_router(attempts_router)

# Trends and recommendations. Last, because it is the only router that reads what every
# other one wrote and adds nothing of its own to the schema.
app.include_router(progress_router)

# Your corrections, grouped, and the verb form to practise. Beside progress: it reads the
# same rows the snapshots are built from, and lists the sentences a snapshot cannot hold.
app.include_router(grammar_router)

# One of those corrections, said again and compared with what the recogniser heard.
app.include_router(drills_router)

# A spoken answer to a work prompt: how it was said and how it was built, counted, with a
# language model's feedback beside the counts.
app.include_router(answers_router)

# Said once, at startup, in the logs the operator is already reading. The sentinel
# signing key is the right default for a laptop and a serious problem anywhere else,
# and the difference between those two situations is not something config.py can see —
# so it is reported rather than guessed at. `docker compose logs api` is where it lands.
if JWT_SECRET_IS_DEV:
    logging.getLogger("speaklab").warning(
        "JWT_SECRET is unset, so sessions are signed with the built-in development "
        "key. Anyone holding this repository can mint a valid session cookie. Set "
        "JWT_SECRET before this is reachable by anyone but you."
    )
