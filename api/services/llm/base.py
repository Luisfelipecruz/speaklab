"""The provider interface: what the conversation loop is allowed to assume about an LLM.

Three things live here — the message and completion shapes, the error taxonomy, and the
token estimator — and nothing that knows about HTTP or about Ollama. `conversation.py`
imports only from this module, which is what makes the provider swappable and, more
usefully, what makes the loop testable against a stub that never leaves the process.

**Not LangChain, and this file is the argument.** What a provider does here is: take a
list of messages, respect a token budget, and return text with the counts it actually
used. That is an HTTP call and an arithmetic problem. A framework would supply both, and
would also supply a chain abstraction, a memory abstraction and a prompt-template
abstraction — and the token budget, the part of this milestone most worth reviewing,
would end up configured inside one of them rather than written down where somebody can
disagree with it.

**The taxonomy is the same three-way split as `asr_client` and `tts_client`**, for the
same reason: *the system is broken*, *the request is broken*, and *the two ends disagree
about the protocol* need different handling, and collapsing them produces a retry loop
against a request that cannot ever succeed.

The one asymmetry worth naming, because it changes an HTTP status code upstream:
`AsrRejected` means the **user's** audio was bad and they can act on it by re-recording,
so it becomes a 422. `LlmRejected` means the prompt or the model name was bad, which is
*this system's* mistake and not something the speaker can do anything about — so it
becomes a 503 whose detail names the misconfiguration for whoever reads the logs.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Literal

from pydantic import BaseModel, Field

from config import LLM_CHARS_PER_TOKEN

Role = Literal["system", "user", "assistant"]


class ChatMessage(BaseModel):
    """One message in the list sent to the model.

    `system` is in the vocabulary because the provider protocol has it, **not because
    every model does**. Gemma 3 has no system turn at all: Ollama's template for it
    renders a system message as an ordinary user turn, in whatever position it sits.
    `conversation.py` is where that fact is dealt with; the type here stays honest about
    what was asked for, so the day a model with a real system channel is configured, the
    request already says which messages were meant to be one.
    """

    role: Role
    content: str


class Completion(BaseModel):
    """A finished reply, with what it cost.

    The token counts come from the provider's own accounting rather than from the
    estimator below, and the difference matters: the estimate decides what to send, the
    counts record what was actually read. `turns.prompt_tokens` stores this one, so a
    drifting estimator shows up as a widening gap between two stored numbers rather than
    as a context window that quietly overflows.
    """

    text: str
    model: str

    # Optional because a provider is not obliged to count, and a stub in a test does
    # not. A missing count is stored as NULL — which is "not measured", and is a
    # different fact from zero.
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)

    # Wall clock for the call as this process saw it.
    latency_ms: int = Field(ge=0)

    # How much of that was the model being loaded into memory rather than generating.
    # The first turn after a restart pays 2-3 seconds here and no later turn pays any
    # of it, so a latency table that does not separate the two reports a p95 that is
    # really one cold start wearing twenty turns as a disguise.
    load_ms: int | None = Field(default=None, ge=0)


class LlmError(Exception):
    """Base for every failure of a generation call."""


class LlmUnavailable(LlmError):
    """Nobody answered, or the provider failed on its own account.

    The reply must not be fabricated and must not be retried in a loop by this process.
    The endpoint turns this into a 503 with a plain message (plan §7 m6).
    """


class LlmRejected(LlmError):
    """The provider refused the request. The same request will be refused again.

    In practice: a model that is not pulled, or a malformed options block. Both are this
    system's misconfiguration rather than anything the speaker did.
    """

    def __init__(self, detail: str, status_code: int) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


class LlmProtocolError(LlmError):
    """A 200 whose body is not the agreed shape. Version skew, not a bad request."""


def estimate_tokens(text: str) -> int:
    """Roughly how many tokens `text` will become. Never exact, deliberately cheap.

    There is no Gemma tokenizer in this image and there will not be one: it means
    `transformers`, which means torch, which is precisely what invariant I5 keeps out of
    the API container. So the prompt is sized by a ratio.

    The ratio is measured rather than folklore — `tests/test_conversation_live.py`
    compares this against Ollama's own `prompt_eval_count` on real assembled prompts and
    prints the error, and decision 0003 records it. It errs high on purpose: English
    prose runs nearer 4.6 characters per token on this model, so assuming 4.0 over-counts,
    and over-counting spends context that was available while under-counting walks off
    the cliff in `config.LLM_NUM_CTX` — where the penalty is not a rejected request but
    half the conversation silently deleted.

    `max(1, ...)` because a message is never free: even an empty string costs the turn
    delimiters the template wraps it in.
    """
    return max(1, round(len(text) / LLM_CHARS_PER_TOKEN))


# Tokens the chat template adds per message — for Gemma 3, `<start_of_turn>user` and
# `<end_of_turn>` around every one. Real tokens the caller never wrote, which a naive sum
# over content lengths misses entirely. Small each; over a forty-message history it is
# the difference between fitting and shifting.
_PER_MESSAGE_TOKENS = 4

# And per request: the BOS token, and the `<start_of_turn>model` the template opens for
# the reply. Measured rather than reasoned about — without it a one-line prompt estimated
# at 10 tokens against an actual 17, which is a 41 % under-count and, at that size,
# seven tokens nobody would notice. It is here because an estimator that is wrong on the
# smallest input is an estimator nobody should trust on the largest.
_PER_REQUEST_TOKENS = 8


def estimate_messages(messages: list[ChatMessage]) -> int:
    """The estimated size of a whole message list."""
    if not messages:
        return 0
    return _PER_REQUEST_TOKENS + sum(
        estimate_tokens(message.content) + _PER_MESSAGE_TOKENS for message in messages
    )


class LlmProvider(ABC):
    """What `conversation.py` may call.

    Two methods rather than one, and they are genuinely different calls rather than one
    wrapping the other. `complete` asks for the whole reply; `stream` asks for it token
    by token so that finished sentences can be handed to the voice while the rest is
    still being written (PRD §9.1's first fallback). Both shapes are exercised, because
    `make turn-latency` measures them against each other — and a comparison where one arm
    is the other arm in a costume measures nothing.
    """

    @property
    @abstractmethod
    def model(self) -> str:
        """The model name to record on the turn."""

    @abstractmethod
    async def complete(
        self, messages: list[ChatMessage], max_tokens: int | None = None
    ) -> Completion:
        """The whole reply, in one call."""

    @abstractmethod
    def stream(
        self, messages: list[ChatMessage], max_tokens: int | None = None
    ) -> AsyncIterator[str | Completion]:
        """Deltas as they arrive, then exactly one `Completion` as the final item.

        The union return is the shape that keeps the token counts. They only exist on
        the provider's last line, so a stream that yielded only strings would force
        every streamed turn to store `prompt_tokens = NULL` — which is most turns, and
        which would make the FR-8 budget an unmeasured claim on the majority path.

        The terminal `Completion.text` is the full accumulated reply, so a caller that
        does not care about deltas can ignore every string and read the last item.
        """
