"""Liveness, and an honest account of what is degraded.

The distinction this module exists to make: **the database is a dependency, the model
layer is not.** Without Postgres this container cannot answer anything and should say so
with a 503. Without `asr`, `tts`, `pron` and the LLM it can still serve scenarios,
sessions, auth and progress, and it starts and answers while those services are still
loading their weights. A stack reporting `degraded` here is working as designed.

Two endpoints, because they answer two different questions:

    GET /health         Is this container alive, and what is it missing?
    GET /health/models  Which model services are up, and what did each one say?

`/health` is what the compose healthcheck curls every ten seconds, so its cost matters.
The four model probes run concurrently under a single timeout ceiling
(`HEALTH_PROBE_TIMEOUT_S`, 1.5 s), which means an entirely dead model layer adds that
ceiling once — not four times, and never unbounded.
"""

import asyncio
import time
from typing import Any

import httpx
from fastapi import APIRouter, Response
from sqlalchemy import text

from config import (
    HEALTH_PROBE_TIMEOUT_S,
    MODEL_SERVICES,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    VERSION,
)
from database import engine

router = APIRouter(tags=["health"])

# Status vocabulary, closed on purpose so the frontend can switch on it.
#
#   ok           reachable and answering 2xx
#   unreachable  no answer: not started, not built, DNS failure, or timed out
#   error        answered, but not with a 2xx — the service is up and unwell,
#                which is a different problem from it being absent
OK = "ok"
UNREACHABLE = "unreachable"
ERROR = "error"


async def _probe_database() -> dict[str, Any]:
    """Round-trip a `SELECT 1`.

    Timed because the number is the useful part: a database that answers in 40 ms
    rather than 1 ms is a finding, and a health endpoint that only ever says "ok"
    would hide it.
    """
    started = time.perf_counter()
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        return {
            "status": ERROR,
            "detail": f"{type(exc).__name__}: {exc}",
        }
    return {
        "status": OK,
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
    }


async def _probe_service(
    client: httpx.AsyncClient, name: str, url: str
) -> dict[str, Any]:
    """Ask one model service how it is.

    Every failure mode collapses to `unreachable` with the exception type preserved in
    `detail`. That is deliberate: from here, "the container was never started", "the
    service is not deployed" and "the host is down" are genuinely the same observation,
    and inventing a distinction the API cannot actually make would be a worse answer
    than the honest one.

    The service's own body is passed through under `reports`. The model services answer
    200 with `{"model_loaded": false}` while weights are still loading — a cold start is
    minutes and must not read as a crash — so "reachable" and "ready" are two different
    facts and both are reported.
    """
    started = time.perf_counter()
    try:
        response = await client.get(f"{url}/health")
    except Exception as exc:
        return {
            "status": UNREACHABLE,
            "url": url,
            "detail": f"{type(exc).__name__}: {exc}",
        }

    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    result: dict[str, Any] = {
        "status": OK if response.is_success else ERROR,
        "url": url,
        "latency_ms": elapsed_ms,
    }
    if not response.is_success:
        result["detail"] = f"HTTP {response.status_code}"
    try:
        body = response.json()
    except ValueError:
        return result
    if isinstance(body, dict):
        result["reports"] = body
    return result


def _with_tag(model: str) -> str:
    """`gemma3` and `gemma3:latest` are one model to Ollama, so compare them as one."""
    return model if ":" in model else f"{model}:latest"


async def _probe_llm(client: httpx.AsyncClient) -> dict[str, Any]:
    """Ask Ollama whether the configured model is there to answer.

    Ollama has no `/health`. `/api/tags` lists the models it has pulled, which is the
    question that matters: an Ollama without the model fails a conversation exactly as
    an absent Ollama does, because `POST /sessions` asks for the persona's opening line
    before it returns. So a missing model is `error` — up, and unable to serve — with the
    command that fixes it in `detail`, never `ok` with a flag the way a loading model
    service is. `ready` must be false whenever a conversation would fail.

    Cheap enough for a probe that runs every ten seconds: listing tags reads a manifest
    directory and loads no weights.
    """
    url = OLLAMA_BASE_URL
    started = time.perf_counter()
    try:
        response = await client.get(f"{url}/api/tags")
    except Exception as exc:
        return {
            "status": UNREACHABLE,
            "url": url,
            "detail": f"{type(exc).__name__}: {exc}",
        }

    result: dict[str, Any] = {
        "status": ERROR,
        "url": url,
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
    }
    if not response.is_success:
        result["detail"] = f"HTTP {response.status_code}"
        return result
    try:
        pulled = {
            _with_tag(entry.get("name") or entry.get("model") or "")
            for entry in response.json()["models"]
        }
    except (ValueError, KeyError, TypeError, AttributeError):
        result["detail"] = "answered, but not with Ollama's model list"
        return result

    result["reports"] = {"model": OLLAMA_MODEL}
    if _with_tag(OLLAMA_MODEL) not in pulled:
        result["detail"] = (
            f"{OLLAMA_MODEL} is not pulled. Run: ollama pull {OLLAMA_MODEL}"
        )
        return result
    result["status"] = OK
    return result


async def probe_model_services() -> dict[str, dict[str, Any]]:
    """Probe all four concurrently. Never raises.

    One client for the four requests, and `asyncio.gather` rather than a loop, so the
    wall-clock cost of a completely absent model layer is one timeout rather than four.
    """
    async with httpx.AsyncClient(timeout=HEALTH_PROBE_TIMEOUT_S) as client:
        names = list(MODEL_SERVICES)
        *services, llm = await asyncio.gather(
            *(_probe_service(client, name, MODEL_SERVICES[name]) for name in names),
            _probe_llm(client),
        )
    return {**dict(zip(names, services)), "llm": llm}


@router.get("/health")
async def health(response: Response) -> dict[str, Any]:
    """Overall liveness.

    200 whenever the database answers, whatever the model services are doing. 503 only
    when it does not — the one condition that makes this container genuinely useless.

    Returning 503 because `pron` is down would take the compose healthcheck with it,
    which would take `depends_on: service_healthy` with it, which would stop the
    frontend from starting because a milestone eight steps away has not been built yet.
    """
    database, models = await asyncio.gather(_probe_database(), probe_model_services())

    if database["status"] != OK:
        status = "unavailable"
        response.status_code = 503
    elif any(service["status"] != OK for service in models.values()):
        status = "degraded"
    else:
        status = OK

    return {
        "status": status,
        "version": VERSION,
        "database": database,
        "models": models,
    }


@router.get("/health/models")
async def health_models() -> dict[str, Any]:
    """The model layer on its own, always 200.

    A monitoring endpoint, not a liveness one: it reports on services this container
    depends on for *features*, not for *running*, so a non-2xx here would be a category
    error. `ready` is the single boolean worth acting on — it is false whenever any
    model-backed feature would currently fail.
    """
    models = await probe_model_services()
    return {
        "ready": all(service["status"] == OK for service in models.values()),
        "services": models,
    }
