"""SpeakLab API — the only orchestrator in the system.

Everything that is not a model runs here: audio normalisation, the deterministic
fluency and grammar metrics, the conversation loop, the progress rollups. The models
run in `asr`, `tts` and `pron`, and this image contains none of their weights and no
torch (invariant I5). That separation is what lets this container start in a couple of
seconds and stay at 422 MB — measured with `docker images`, and worth re-measuring
rather than quoting the next time it is claimed.

Routers are registered explicitly, one line each, as their milestones land. There is no
auto-discovery: a router that fails to import should break startup loudly rather than
disappear from the OpenAPI schema with nothing in the logs.
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import CORS_ORIGINS, JWT_SECRET_IS_DEV, VERSION
from routers.auth import router as auth_router
from routers.health import router as health_router
from routers.passages import router as passages_router
from routers.scenarios import router as scenarios_router

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

# Routers arriving with their milestones:
#   m6  sessions, turns
#   m8  attempts, audio
#   m10 progress

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
