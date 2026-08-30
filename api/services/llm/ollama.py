"""The one provider that exists: local Ollama over HTTP.

Ollama runs on the **host**, not in Compose, and that is a measured decision rather than
a convenience (handoff §2.1): Docker Desktop on macOS cannot pass the Apple GPU into a
Linux container, so a containerised Ollama runs on CPU while the host's runs on Metal —
the same model, several times slower, for nothing. `OLLAMA_BASE_URL` defaults to
`host.docker.internal:11434` and `extra_hosts` in docker-compose.yml makes that resolve
on Linux too.

Two things about this API are worth knowing before reading the code, both measured on
2026-08-30 against Ollama 0.33.1 and `gemma3:4b`:

**1. An over-long prompt is not refused.** Exceed `num_ctx` by one token and llama.cpp
shifts the context, discarding half of it, and answers anyway with a 200. A 4200-token
prompt under `num_ctx: 4096` came back with `prompt_eval_count: 2051`. Nothing in the
response says so. This is why `num_ctx` is sent explicitly on every request rather than
inherited from whatever the host's default happens to be this version.

**2. The token counts only arrive at the end.** On a streamed response they are on the
final line, alongside `done: true`. That is the whole reason `stream` yields a
`Completion` as its last item instead of only yielding text.
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

from config import (
    LLM_MAX_OUTPUT_TOKENS,
    LLM_NUM_CTX,
    LLM_TIMEOUT_S,
    OLLAMA_BASE_URL,
    OLLAMA_KEEP_ALIVE,
    OLLAMA_MODEL,
)
from services.llm.base import (
    ChatMessage,
    Completion,
    LlmProtocolError,
    LlmProvider,
    LlmRejected,
    LlmUnavailable,
)


def _detail_of(response: httpx.Response) -> str:
    """Ollama's `{"error": ...}`, or the raw text when it is not that."""
    try:
        body = response.json()
    except ValueError:
        return response.text[:200]
    if isinstance(body, dict) and "error" in body:
        return str(body["error"])
    return response.text[:200]


def _ms(nanoseconds: Any) -> int | None:
    """Ollama reports durations in nanoseconds. Nothing else in this codebase does."""
    if not isinstance(nanoseconds, (int, float)):
        return None
    return round(nanoseconds / 1_000_000)


class OllamaProvider(LlmProvider):
    """`POST /api/chat`, streamed or not.

    `client` is injectable for the same reason it is on the other two service clients:
    the cases worth testing are a connection refused, a 404 for a model nobody pulled,
    and a 200 carrying a body this code cannot parse — and none of those can be produced
    on demand by a server that is working.
    """

    def __init__(
        self,
        model: str = OLLAMA_MODEL,
        base_url: str = OLLAMA_BASE_URL,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._client = client

    @property
    def model(self) -> str:
        return self._model

    def _payload(
        self, messages: list[ChatMessage], max_tokens: int | None, stream: bool
    ) -> dict[str, Any]:
        return {
            "model": self._model,
            "messages": [message.model_dump() for message in messages],
            "stream": stream,
            "options": {
                "num_predict": max_tokens or LLM_MAX_OUTPUT_TOKENS,
                # Stated, never inherited. See the module docstring and config.LLM_NUM_CTX.
                "num_ctx": LLM_NUM_CTX,
            },
            # How long the weights stay resident after this call. The default is five
            # minutes, which means a user who stops to think for six pays the ~2.6 s
            # load again on their next turn — a cold start wearing the costume of a slow
            # model. It costs host RAM and no container RAM, so it does not count
            # against the PRD's 8 GB stack ceiling.
            "keep_alive": OLLAMA_KEEP_ALIVE,
        }

    def _client_or_new(self) -> tuple[httpx.AsyncClient, bool]:
        if self._client is not None:
            return self._client, False
        return httpx.AsyncClient(timeout=LLM_TIMEOUT_S), True

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code >= 500:
            raise LlmUnavailable(f"HTTP {response.status_code}: {_detail_of(response)}")
        if response.status_code >= 400:
            # A 404 here is almost always "model not pulled". It is a rejection because
            # retrying changes nothing, and it is *our* misconfiguration rather than the
            # speaker's — the endpoint maps it to 503, not 422.
            raise LlmRejected(_detail_of(response), response.status_code)

    def _completion(self, record: dict[str, Any], started: float) -> Completion:
        latency_ms = round((time.perf_counter() - started) * 1000)
        try:
            content = record["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise LlmProtocolError(f"no message.content in response: {exc!r}") from exc
        return Completion(
            text=content,
            model=record.get("model", self._model),
            prompt_tokens=record.get("prompt_eval_count"),
            completion_tokens=record.get("eval_count"),
            latency_ms=latency_ms,
            load_ms=_ms(record.get("load_duration")),
        )

    async def complete(
        self, messages: list[ChatMessage], max_tokens: int | None = None
    ) -> Completion:
        """The whole reply in one call. Used when synthesis is not being overlapped."""
        client, owned = self._client_or_new()
        started = time.perf_counter()
        try:
            try:
                response = await client.post(
                    f"{self._base_url}/api/chat",
                    json=self._payload(messages, max_tokens, stream=False),
                )
            except httpx.RequestError as exc:
                raise LlmUnavailable(f"{type(exc).__name__}: {exc}") from exc

            self._raise_for_status(response)

            try:
                record = response.json()
            except ValueError as exc:
                raise LlmProtocolError(
                    f"200 whose body is not JSON: {response.text[:120]!r}"
                ) from exc
            return self._completion(record, started)
        finally:
            if owned:
                await client.aclose()

    async def stream(
        self, messages: list[ChatMessage], max_tokens: int | None = None
    ) -> AsyncIterator[str | Completion]:
        """Deltas as NDJSON lines arrive, then one `Completion` carrying the totals.

        A failure after the first line cannot change the status code — the headers are
        long gone — so Ollama reports it as an `{"error": ...}` object mid-stream. It is
        raised as `LlmUnavailable` rather than swallowed, so a caller that stops at the
        first exception cannot mistake half a reply for a whole one. The same shape as
        `tts_client.speak_stream`, for the same reason.
        """
        client, owned = self._client_or_new()
        started = time.perf_counter()
        accumulated: list[str] = []
        finished = False
        try:
            try:
                async with client.stream(
                    "POST",
                    f"{self._base_url}/api/chat",
                    json=self._payload(messages, max_tokens, stream=True),
                ) as response:
                    if response.status_code >= 400:
                        # Nothing has been read yet on a streaming response, and
                        # `_detail_of` needs a body.
                        await response.aread()
                        self._raise_for_status(response)

                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            record = json.loads(line)
                        except ValueError as exc:
                            raise LlmProtocolError(
                                f"line is not JSON: {line[:120]!r}"
                            ) from exc

                        if "error" in record:
                            raise LlmUnavailable(
                                f"generation failed mid-stream: {record['error']}"
                            )

                        delta = record.get("message", {}).get("content", "")
                        if delta:
                            accumulated.append(delta)
                            yield delta

                        if record.get("done"):
                            finished = True
                            record["message"] = {"content": "".join(accumulated)}
                            yield self._completion(record, started)
            except httpx.RequestError as exc:
                raise LlmUnavailable(f"{type(exc).__name__}: {exc}") from exc

            if not finished:
                # The stream ended without a `done` line. The text so far may look
                # complete and be a sentence short, which is the one outcome that must
                # not be stored as a reply.
                raise LlmProtocolError(
                    "stream ended without a done line; the reply is truncated"
                )
        finally:
            if owned:
                await client.aclose()
