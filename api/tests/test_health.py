"""Health endpoint behaviour.

The property under test is not "the endpoint returns 200". It is the asymmetry: the
database is a hard dependency and the model services are not. Getting that backwards
is what would make `docker compose up -d` fail on a machine where nobody has built
`pron`, which is the default state of a fresh clone.
"""

import importlib.util

import httpx
import pytest

from config import MODEL_SERVICES
from routers import health as health_module


def _mock_client(handler) -> httpx.AsyncClient:
    """An httpx client whose transport is a function, so no socket is opened."""
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


# ── The endpoint ────────────────────────────────────────────────────────────


async def test_health_returns_200_and_the_documented_shape(client):
    response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"status", "version", "database", "models"}
    assert body["status"] in {"ok", "degraded"}
    assert body["database"]["status"] == "ok"
    assert set(body["models"]) == set(MODEL_SERVICES)


async def test_unreachable_model_services_are_degraded_not_fatal(client, monkeypatch):
    """The state a machine is in before any model service has been started.

    Every model service is absent. The API must still answer 200, must name each one,
    and must say `degraded` rather than pretending everything is fine.
    """
    monkeypatch.setattr(
        health_module,
        "probe_model_services",
        _all_unreachable,
    )

    response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    for name in MODEL_SERVICES:
        assert body["models"][name]["status"] == "unreachable"


async def test_health_is_ok_when_every_model_service_answers(client, monkeypatch):
    monkeypatch.setattr(health_module, "probe_model_services", _all_ok)

    body = (await client.get("/health")).json()

    assert body["status"] == "ok"


async def test_health_is_503_only_when_the_database_is_gone(client, monkeypatch):
    async def _database_down():
        return {"status": "error", "detail": "OSError: connection refused"}

    monkeypatch.setattr(health_module, "_probe_database", _database_down)

    response = await client.get("/health")

    assert response.status_code == 503
    assert response.json()["status"] == "unavailable"


async def test_health_models_is_200_even_with_nothing_running(client, monkeypatch):
    """A monitoring endpoint, not a liveness one — a non-2xx here would be a category
    error. `ready` is the boolean worth acting on."""
    monkeypatch.setattr(health_module, "probe_model_services", _all_unreachable)

    response = await client.get("/health/models")

    assert response.status_code == 200
    assert response.json()["ready"] is False


# ── The probe ───────────────────────────────────────────────────────────────


async def test_probe_passes_through_a_loading_service_body():
    """`reachable` and `ready` are two different facts and both must survive.

    A model service answers 200 with `model_loaded: false` while its weights download.
    Flattening that to "ok" would make a five-minute cold start indistinguishable from
    a warm service, and the first request would fail for no visible reason.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "ok", "model_loaded": False})

    async with _mock_client(handler) as mock:
        result = await health_module._probe_service(mock, "asr", "http://asr:8101")

    assert result["status"] == "ok"
    assert result["reports"]["model_loaded"] is False
    assert "latency_ms" in result


async def test_probe_distinguishes_answering_badly_from_not_answering():
    """A 500 is `error`, not `unreachable`. Up and unwell is a different problem from
    absent, and it needs a different response from whoever reads this."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="model failed to load")

    async with _mock_client(handler) as mock:
        result = await health_module._probe_service(mock, "pron", "http://pron:8103")

    assert result["status"] == "error"
    assert result["detail"] == "HTTP 500"


async def test_probe_never_raises_when_the_host_does_not_resolve():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("nodename nor servname provided")

    async with _mock_client(handler) as mock:
        result = await health_module._probe_service(mock, "tts", "http://tts:8102")

    assert result["status"] == "unreachable"
    assert "ConnectError" in result["detail"]


async def test_probe_survives_a_service_answering_with_something_that_is_not_json():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>nginx</html>")

    async with _mock_client(handler) as mock:
        result = await health_module._probe_service(mock, "asr", "http://asr:8101")

    assert result["status"] == "ok"
    assert "reports" not in result


# ── Invariant I5 ────────────────────────────────────────────────────────────


def test_the_api_image_contains_no_torch():
    """Invariant I5, asserted rather than commented.

    torch is ~2 GB and belongs to `pron`. Nothing in this image imports it today, but
    dependencies acquire dependencies: this test is what turns "we added a library and
    the image grew by two gigabytes" from something noticed at deploy time into a red
    test in CI.
    """
    assert importlib.util.find_spec("torch") is None, (
        "torch is installed in the API image. Model weights and torch live in "
        "asr/tts/pron, and this image must stay small enough to start in seconds."
    )


@pytest.mark.parametrize("package", ["transformers", "faster_whisper", "piper"])
def test_the_api_image_contains_no_model_runtimes(package):
    assert (
        importlib.util.find_spec(package) is None
    ), f"{package} is installed in the API image; model runtimes live in asr/tts/pron."


# ── Fakes ───────────────────────────────────────────────────────────────────


async def _all_unreachable():
    return {
        name: {"status": "unreachable", "url": url, "detail": "ConnectError: no route"}
        for name, url in MODEL_SERVICES.items()
    }


async def _all_ok():
    return {
        name: {"status": "ok", "url": url, "latency_ms": 1.0}
        for name, url in MODEL_SERVICES.items()
    }
