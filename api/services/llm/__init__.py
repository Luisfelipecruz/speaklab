"""The generation layer, behind one import.

`conversation.py` imports from here and never from `ollama.py`, which is what makes the
provider replaceable — and, more immediately, what lets the whole conversation loop be
tested against a stub with no model, no network and no 3-second turn.

`get_provider` is a function rather than a module-level singleton because a module-level
instance would be constructed at import time, which means at test-collection time, which
means the test suite would build an HTTP client pointed at a host that may not exist.
It is cheap: an `httpx.AsyncClient` is created per call inside the provider, not here.
"""

from services.llm.base import (
    ChatMessage,
    Completion,
    LlmError,
    LlmProtocolError,
    LlmProvider,
    LlmRejected,
    LlmUnavailable,
    estimate_messages,
    estimate_tokens,
)
from services.llm.ollama import OllamaProvider

__all__ = [
    "ChatMessage",
    "Completion",
    "LlmError",
    "LlmProtocolError",
    "LlmProvider",
    "LlmRejected",
    "LlmUnavailable",
    "OllamaProvider",
    "estimate_messages",
    "estimate_tokens",
    "get_provider",
]


def get_provider() -> LlmProvider:
    """The configured provider.

    One implementation exists, so this reads like ceremony. It is not: it is the single
    place a FastAPI dependency override can reach, and every test of the conversation
    loop — the ten-turn scripted conversation, the budget, the summarisation, the
    provider-down 503 — replaces exactly this function. Without it each of those tests
    would have to patch an import inside a module it does not own.
    """
    return OllamaProvider()
