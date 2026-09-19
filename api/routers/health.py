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
import re
import time
from typing import Any

import httpx
from fastapi import APIRouter, Response
from sqlalchemy import text

from config import (
    HEALTH_PROBE_TIMEOUT_S,
    MODEL_SERVICES,
    OLLAMA_BASE_URL,
    OLLAMA_MIN_VERSION,
    OLLAMA_MODEL,
    OLLAMA_MODEL_DIGEST,
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
#   degraded     answering, and able to serve, but not with what was measured: the
#                pulled model is a different build from the one every published
#                figure describes
OK = "ok"
UNREACHABLE = "unreachable"
ERROR = "error"
DEGRADED = "degraded"
# The statuses under which a feature still works. `ready` is computed over these.
SERVING = {OK, DEGRADED}


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


def _version_key(version: str) -> tuple[int, ...]:
    """`0.20.0` before `0.34.2`; a suffix such as `-rc1` is ignored."""
    numbers = re.match(r"\d+(?:\.\d+)*", version.strip())
    if numbers is None:
        return ()
    return tuple(int(part) for part in numbers.group(0).split("."))


def _too_old(ollama_version: str | None) -> bool:
    if not ollama_version or not OLLAMA_MIN_VERSION:
        return False
    found, needed = _version_key(ollama_version), _version_key(OLLAMA_MIN_VERSION)
    return bool(found) and bool(needed) and found < needed


async def _probe_llm(client: httpx.AsyncClient) -> dict[str, Any]:
    """Ask Ollama whether the configured model is there to answer, and which build it is.

    Ollama has no `/health`. `/api/tags` lists the models it has pulled, which is the
    question that matters: an Ollama without the model fails a conversation exactly as
    an absent Ollama does, because `POST /sessions` asks for the persona's opening line
    before it returns. So a missing model is `error` — up, and unable to serve — with the
    command that fixes it in `detail`, never `ok` with a flag the way a loading model
    service is. `ready` must be false whenever a conversation would fail.

    The list also carries each model's manifest digest, size and quantisation, and they
    are reported beside the name, because a tag is a pointer and a digest is a build. A
    pulled model whose digest is not the one the published figures were measured on is
    `degraded`: it answers, so `ready` stays true, but the numbers no longer describe it.

    `/api/version` is asked at the same time. A model that needs a newer Ollama than the
    one installed fails at `ollama pull` with a message about the file format, so when the
    model is missing and Ollama is too old, `detail` says that first.

    Cheap enough for a probe that runs every ten seconds: both calls read local state and
    load no weights.
    """
    url = OLLAMA_BASE_URL
    started = time.perf_counter()
    try:
        tags, version = await asyncio.gather(
            client.get(f"{url}/api/tags"), client.get(f"{url}/api/version")
        )
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
    if not tags.is_success:
        result["detail"] = f"HTTP {tags.status_code}"
        return result
    try:
        pulled = {
            _with_tag(entry.get("name") or entry.get("model") or ""): entry
            for entry in tags.json()["models"]
        }
    except (ValueError, KeyError, TypeError, AttributeError):
        result["detail"] = "answered, but not with Ollama's model list"
        return result

    ollama_version: str | None = None
    if version.is_success:
        try:
            ollama_version = str(version.json().get("version") or "") or None
        except (ValueError, AttributeError):
            ollama_version = None

    result["reports"] = {"model": OLLAMA_MODEL, "ollama_version": ollama_version}
    entry = pulled.get(_with_tag(OLLAMA_MODEL))
    if entry is None:
        if _too_old(ollama_version):
            result["detail"] = (
                f"Ollama {ollama_version} is older than {OLLAMA_MIN_VERSION}, which "
                f"{OLLAMA_MODEL} needs. Update it from https://ollama.com/download, "
                f"then run: ollama pull {OLLAMA_MODEL}"
            )
        else:
            result["detail"] = (
                f"{OLLAMA_MODEL} is not pulled. Run: ollama pull {OLLAMA_MODEL}"
            )
        return result

    details = entry.get("details") if isinstance(entry.get("details"), dict) else {}
    digest = entry.get("digest")
    result["reports"].update(
        {
            "digest": digest,
            "size_bytes": entry.get("size"),
            "parameter_size": details.get("parameter_size"),
            "quantization_level": details.get("quantization_level"),
        }
    )
    if OLLAMA_MODEL_DIGEST and digest != OLLAMA_MODEL_DIGEST:
        result["status"] = DEGRADED
        result["detail"] = (
            f"{OLLAMA_MODEL} is pulled as build {str(digest or '')[:12] or 'unknown'}, "
            f"not {OLLAMA_MODEL_DIGEST[:12]}, the build the published figures were "
            f"measured on. Run: ollama pull {OLLAMA_MODEL}. If the build stays, the "
            "library has moved on and the figures are due a new measurement; "
            "OLLAMA_MODEL_DIGEST accepts a build."
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
        "ready": all(service["status"] in SERVING for service in models.values()),
        "services": models,
    }
