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
    assert set(body["models"]) == set(MODEL_SERVICES) | {"llm"}


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


async def test_a_model_that_is_not_pulled_is_enough_to_degrade_the_stack(
    client, monkeypatch
):
    """The fresh-clone state this probe was added for: every container healthy, Ollama
    running, and the model never pulled. Every conversation fails in that state, so
    neither endpoint may call it fine."""

    async def _all_but_the_model():
        models = await _all_ok()
        models["llm"] = {
            "status": "error",
            "url": "http://host.docker.internal:11434",
            "detail": "gemma3:4b is not pulled. Run: ollama pull gemma3:4b",
        }
        return models

    monkeypatch.setattr(health_module, "probe_model_services", _all_but_the_model)

    assert (await client.get("/health")).json()["status"] == "degraded"
    assert (await client.get("/health/models")).json()["ready"] is False


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


# ── The LLM probe ───────────────────────────────────────────────────────────
#
# Ollama has no /health; the question is whether the configured model is in the list
# /api/tags returns. The shapes below are Ollama's own: each entry carries `name` and
# `model`, both the tagged name.


MEASURED = "c6eb396dbd5992bbe3f5cdb947e8bbc0ee413d7c17e2beaae69f5d569cf982eb"
OTHER = "7fbdbf8f5e45" + "0" * 52


def _entry(name: str, digest: str = MEASURED) -> dict:
    return {
        "name": name,
        "model": name,
        "digest": digest,
        "size": 9608350718,
        "details": {"parameter_size": "8.0B", "quantization_level": "Q4_K_M"},
    }


def _ollama(*entries, version: str = "0.34.2"):
    """Ollama answering both calls the probe makes: the model list and its version."""
    models = [_entry(e) if isinstance(e, str) else e for e in entries]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": version})
        assert request.url.path == "/api/tags"
        return httpx.Response(200, json={"models": models})

    return handler


def _tags(*names: str):
    return _ollama(*names)


@pytest.fixture
def pinned(monkeypatch):
    """The measured model configured, with its digest expected."""
    monkeypatch.setattr(health_module, "OLLAMA_MODEL", "gemma4:e4b")
    monkeypatch.setattr(health_module, "OLLAMA_MODEL_DIGEST", MEASURED)
    monkeypatch.setattr(health_module, "OLLAMA_MIN_VERSION", "0.20.0")


async def test_llm_probe_is_ok_when_the_configured_model_is_pulled(monkeypatch):
    monkeypatch.setattr(health_module, "OLLAMA_MODEL", "gemma3:4b")
    monkeypatch.setattr(health_module, "OLLAMA_MODEL_DIGEST", "")

    async with _mock_client(_tags("mistral:7b", "gemma3:4b")) as mock:
        result = await health_module._probe_llm(mock)

    assert result["status"] == "ok"
    assert result["reports"]["model"] == "gemma3:4b"
    assert "latency_ms" in result


async def test_llm_probe_reports_the_build_it_found(pinned):
    """A tag is a pointer; the digest is the build. The report carries both, with the
    size and quantisation Ollama lists, so `make llm-check` can print what is running.
    """
    async with _mock_client(_ollama("gemma4:e4b")) as mock:
        result = await health_module._probe_llm(mock)

    assert result["status"] == "ok"
    assert result["reports"] == {
        "model": "gemma4:e4b",
        "ollama_version": "0.34.2",
        "digest": MEASURED,
        "size_bytes": 9608350718,
        "parameter_size": "8.0B",
        "quantization_level": "Q4_K_M",
    }


async def test_a_pulled_build_that_is_not_the_measured_one_is_degraded(pinned):
    """It answers, so a conversation works; the published figures describe another
    build, so it is not `ok`. The detail names both builds and the command."""
    async with _mock_client(_ollama(_entry("gemma4:e4b", OTHER))) as mock:
        result = await health_module._probe_llm(mock)

    assert result["status"] == "degraded"
    assert result["reports"]["digest"] == OTHER
    assert "7fbdbf8f5e45" in result["detail"]
    assert "c6eb396dbd59" in result["detail"]
    assert "ollama pull gemma4:e4b" in result["detail"]


async def test_no_expected_digest_means_any_build_is_ok(monkeypatch):
    monkeypatch.setattr(health_module, "OLLAMA_MODEL", "gemma4:e4b")
    monkeypatch.setattr(health_module, "OLLAMA_MODEL_DIGEST", "")

    async with _mock_client(_ollama(_entry("gemma4:e4b", OTHER))) as mock:
        result = await health_module._probe_llm(mock)

    assert result["status"] == "ok"


async def test_a_drifted_build_leaves_the_stack_ready(client, monkeypatch, pinned):
    """`ready` is false only when a feature would fail. A different build answers."""

    async def degraded_llm(_client):
        return {"status": "degraded", "url": "x", "detail": "another build"}

    async def ok_service(*_args, **_kwargs):
        return {"status": "ok", "url": "x", "latency_ms": 1}

    monkeypatch.setattr(health_module, "_probe_llm", degraded_llm)
    monkeypatch.setattr(health_module, "_probe_service", ok_service)

    body = (await client.get("/health/models")).json()
    assert body["ready"] is True
    assert body["services"]["llm"]["status"] == "degraded"
    assert (await client.get("/health")).json()["status"] == "degraded"


async def test_a_missing_model_on_an_old_ollama_names_the_version_first(pinned):
    """`ollama pull` on an Ollama older than the model needs fails with a message about
    the file format; the probe says which version is needed before that happens."""
    async with _mock_client(_ollama("mistral:7b", version="0.19.0")) as mock:
        result = await health_module._probe_llm(mock)

    assert result["status"] == "error"
    assert result["detail"].startswith("Ollama 0.19.0 is older than 0.20.0")
    assert "https://ollama.com/download" in result["detail"]
    assert "ollama pull gemma4:e4b" in result["detail"]
    assert result["reports"]["ollama_version"] == "0.19.0"


async def test_a_missing_model_on_a_new_enough_ollama_names_the_pull(pinned):
    async with _mock_client(_ollama("mistral:7b", version="0.20.0")) as mock:
        result = await health_module._probe_llm(mock)

    assert result["detail"] == "gemma4:e4b is not pulled. Run: ollama pull gemma4:e4b"


@pytest.mark.parametrize(
    ("found", "needed", "older"),
    [
        ("0.19.0", "0.20.0", True),
        ("0.20.0", "0.20.0", False),
        ("0.34.2", "0.20.0", False),
        ("0.9.9", "0.20.0", True),
        ("0.20.0-rc1", "0.20.0", False),
        ("garbage", "0.20.0", False),
    ],
)
def test_version_comparison_is_numeric_not_lexical(monkeypatch, found, needed, older):
    monkeypatch.setattr(health_module, "OLLAMA_MIN_VERSION", needed)
    assert health_module._too_old(found) is older


async def test_llm_probe_names_the_pull_command_when_the_model_is_missing(
    monkeypatch,
):
    """Ollama answering is not the same as a conversation working. A different size of
    the same family does not count either — the model that is configured is the one the
    persona is sent to."""
    monkeypatch.setattr(health_module, "OLLAMA_MODEL", "gemma3:4b")
    monkeypatch.setattr(health_module, "OLLAMA_MODEL_DIGEST", "")

    async with _mock_client(_tags("gemma3:12b", "mistral:7b")) as mock:
        result = await health_module._probe_llm(mock)

    assert result["status"] == "error"
    assert result["detail"] == "gemma3:4b is not pulled. Run: ollama pull gemma3:4b"


@pytest.mark.parametrize(
    ("configured", "pulled"),
    [("gemma3", "gemma3:latest"), ("gemma3:latest", "gemma3")],
)
async def test_llm_probe_treats_an_untagged_name_as_latest(
    monkeypatch, configured, pulled
):
    monkeypatch.setattr(health_module, "OLLAMA_MODEL", configured)
    monkeypatch.setattr(health_module, "OLLAMA_MODEL_DIGEST", "")

    async with _mock_client(_tags(pulled)) as mock:
        result = await health_module._probe_llm(mock)

    assert result["status"] == "ok"


async def test_llm_probe_never_raises_when_ollama_is_not_running():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    async with _mock_client(handler) as mock:
        result = await health_module._probe_llm(mock)

    assert result["status"] == "unreachable"
    assert "ConnectError" in result["detail"]


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500, text="internal error"),
        httpx.Response(200, text="<html>not ollama</html>"),
        httpx.Response(200, json={"something": "else"}),
        httpx.Response(200, json={"models": ["gemma3:4b"]}),
    ],
    ids=["http-500", "not-json", "no-model-list", "entries-not-objects"],
)
async def test_llm_probe_calls_anything_else_that_answers_an_error(response):
    """Something answered at the configured address and it was not a usable model list.
    That is up and unwell, not absent — and never `ok`."""
    async with _mock_client(lambda request: response) as mock:
        result = await health_module._probe_llm(mock)

    assert result["status"] == "error"
    assert result["detail"]


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


_EVERY_PROBE = {**MODEL_SERVICES, "llm": "http://host.docker.internal:11434"}


async def _all_unreachable():
    return {
        name: {"status": "unreachable", "url": url, "detail": "ConnectError: no route"}
        for name, url in _EVERY_PROBE.items()
    }


async def _all_ok():
    return {
        name: {"status": "ok", "url": url, "latency_ms": 1.0}
        for name, url in _EVERY_PROBE.items()
    }
