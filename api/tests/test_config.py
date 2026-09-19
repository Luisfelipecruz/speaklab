"""The defaults a fresh clone runs with, as they stand in the module."""

import importlib
import re

import config


def _reloaded_default(monkeypatch, name: str):
    """The value the module gives `name` when the environment does not set it."""
    for variable in ("OLLAMA_MODEL", "OLLAMA_MODEL_DIGEST", "OLLAMA_MIN_VERSION"):
        monkeypatch.delenv(variable, raising=False)
    try:
        return getattr(importlib.reload(config), name)
    finally:
        monkeypatch.undo()
        importlib.reload(config)


def test_the_default_model_is_a_named_build_never_latest(monkeypatch):
    """A tag with a size in it pulls the same build on every machine; `latest` pulls
    whatever the library points at on the day."""
    model = _reloaded_default(monkeypatch, "OLLAMA_MODEL")
    assert ":" in model
    assert not model.endswith(":latest")
    assert model == config.MEASURED_MODEL


def test_the_measured_digest_is_a_whole_sha256(monkeypatch):
    digest = _reloaded_default(monkeypatch, "MEASURED_MODEL_DIGEST")
    assert re.fullmatch(r"[0-9a-f]{64}", digest)
    assert _reloaded_default(monkeypatch, "OLLAMA_MODEL_DIGEST") == digest


def test_another_model_expects_no_digest_unless_one_is_given(monkeypatch):
    monkeypatch.setenv("OLLAMA_MODEL", "gemma3:4b")
    monkeypatch.delenv("OLLAMA_MODEL_DIGEST", raising=False)
    try:
        assert importlib.reload(config).OLLAMA_MODEL_DIGEST == ""
        monkeypatch.setenv("OLLAMA_MODEL_DIGEST", "abc")
        assert importlib.reload(config).OLLAMA_MODEL_DIGEST == "abc"
    finally:
        monkeypatch.undo()
        importlib.reload(config)


def test_the_minimum_ollama_version_is_dotted_numbers(monkeypatch):
    version = _reloaded_default(monkeypatch, "OLLAMA_MIN_VERSION")
    assert re.fullmatch(r"\d+\.\d+\.\d+", version)
