"""The Ollama provider, driven against a mock transport rather than a running daemon.

Every interesting case here is a failure, and none of them can be produced on demand by
a server that is working: a connection refused, a 404 for a model nobody pulled, an
`{"error": ...}` object arriving halfway through a stream, a 200 carrying HTML. So the
transport is mocked and the daemon is left out of it — `test_conversation_live.py` is
where a real one is used, and it skips when there is none.

The three-way taxonomy is what most of this file is about. `LlmUnavailable`,
`LlmRejected` and `LlmProtocolError` mean different things and produce different HTTP
status codes upstream, and the failure mode being guarded against is somebody
simplifying them into one `except Exception` — after which a mis-pulled model becomes an
infinite retry against a request that cannot ever succeed.
"""

import json

import httpx
import pytest

from services.llm import (
    ChatMessage,
    Completion,
    LlmProtocolError,
    LlmRejected,
    LlmUnavailable,
    OllamaProvider,
    estimate_messages,
    estimate_tokens,
)

MESSAGES = [ChatMessage(role="user", content="Hello.")]


def provider_with(handler) -> OllamaProvider:
    return OllamaProvider(
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )


def chat_response(text: str, **extra) -> httpx.Response:
    body = {
        "model": "gemma3:4b",
        "message": {"role": "assistant", "content": text},
        "done": True,
        "done_reason": "stop",
        "prompt_eval_count": 46,
        "eval_count": 45,
        "load_duration": 2_610_010_584,
        **extra,
    }
    return httpx.Response(200, json=body)


def ndjson(*records) -> httpx.Response:
    return httpx.Response(
        200,
        content="\n".join(json.dumps(record) for record in records).encode(),
        headers={"content-type": "application/x-ndjson"},
    )


def delta(text: str) -> dict:
    return {"message": {"role": "assistant", "content": text}, "done": False}


def final(**extra) -> dict:
    return {
        "model": "gemma3:4b",
        "message": {"role": "assistant", "content": ""},
        "done": True,
        "prompt_eval_count": 120,
        "eval_count": 20,
        **extra,
    }


# ── The happy paths ─────────────────────────────────────────────────────────


async def test_a_completion_carries_the_counts_the_server_reported():
    """Not the estimate. The stored `turns.prompt_tokens` has to be a measurement, or
    the token budget is a claim nothing ever checks."""
    completion = await provider_with(
        lambda request: chat_response("Hi there.")
    ).complete(MESSAGES)

    assert completion.text == "Hi there."
    assert completion.prompt_tokens == 46
    assert completion.completion_tokens == 45
    assert completion.model == "gemma3:4b"


async def test_a_cold_model_load_is_reported_separately_from_generation():
    """2.6 s of model loading inside a 3 s turn budget is the whole budget. Reported on
    its own so a p95 cannot silently be one cold start wearing twenty turns as a
    disguise."""
    completion = await provider_with(lambda request: chat_response("Hi.")).complete(
        MESSAGES
    )

    assert completion.load_ms == 2610


async def test_the_stream_yields_deltas_and_then_exactly_one_completion():
    def handler(request):
        return ndjson(delta("Hello"), delta(" there"), delta("."), final())

    events = [event async for event in provider_with(handler).stream(MESSAGES)]

    assert [event for event in events if isinstance(event, str)] == [
        "Hello",
        " there",
        ".",
    ]
    completions = [event for event in events if isinstance(event, Completion)]
    assert len(completions) == 1
    assert completions[0].text == "Hello there."
    assert completions[0].prompt_tokens == 120


async def test_the_context_window_is_stated_on_every_request():
    """The measurement in config.LLM_NUM_CTX is only worth anything if the option is
    actually sent. Ollama's own default has changed between versions, and the failure it
    produces is a silently halved prompt rather than an error."""
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content)["options"])
        return chat_response("ok")

    await provider_with(handler).complete(MESSAGES)

    from config import LLM_NUM_CTX

    assert seen["num_ctx"] == LLM_NUM_CTX
    assert seen["num_predict"] > 0


# ── The taxonomy ────────────────────────────────────────────────────────────


async def test_a_refused_connection_is_unavailable():
    def handler(request):
        raise httpx.ConnectError("[Errno 111] Connection refused")

    with pytest.raises(LlmUnavailable, match="ConnectError"):
        await provider_with(handler).complete(MESSAGES)


async def test_a_model_that_was_never_pulled_is_a_rejection_not_an_outage():
    """The distinction that matters: retrying an unpulled model forever is a loop that
    cannot terminate. It is still a 503 to the browser — the speaker cannot fix it — but
    it must not be retried, and the detail has to name the model for whoever can."""

    def handler(request):
        return httpx.Response(
            404, json={"error": 'model "gemma3:4b" not found, try pulling it first'}
        )

    with pytest.raises(LlmRejected) as raised:
        await provider_with(handler).complete(MESSAGES)

    assert raised.value.status_code == 404
    assert "not found" in raised.value.detail


async def test_a_500_is_unavailable_and_not_a_rejection():
    def handler(request):
        return httpx.Response(500, json={"error": "out of memory"})

    with pytest.raises(LlmUnavailable, match="out of memory"):
        await provider_with(handler).complete(MESSAGES)


async def test_a_200_that_is_not_json_is_a_protocol_error():
    """A reverse proxy answering 200 with an HTML error page is a real thing, and it
    must not read as a reply the persona produced."""

    def handler(request):
        return httpx.Response(200, text="<html><body>502 Bad Gateway</body></html>")

    with pytest.raises(LlmProtocolError, match="not JSON"):
        await provider_with(handler).complete(MESSAGES)


async def test_a_200_without_message_content_is_a_protocol_error():
    def handler(request):
        return httpx.Response(200, json={"done": True})

    with pytest.raises(LlmProtocolError, match="message.content"):
        await provider_with(handler).complete(MESSAGES)


async def test_an_error_object_mid_stream_is_unavailable_not_a_short_reply():
    """The headers are long gone by the time this arrives, so the status code cannot
    say anything. Swallowing it would store half a sentence as the persona's turn."""

    def handler(request):
        return ndjson(delta("I think we should"), {"error": "context canceled"})

    with pytest.raises(LlmUnavailable, match="mid-stream"):
        async for _ in provider_with(handler).stream(MESSAGES):
            pass


async def test_a_stream_that_stops_without_a_done_line_is_a_protocol_error():
    """The most dangerous shape in this file: the text so far reads like a finished
    reply and is a sentence short. Nothing downstream could tell."""

    def handler(request):
        return ndjson(delta("That sounds difficult."))

    with pytest.raises(LlmProtocolError, match="truncated"):
        async for _ in provider_with(handler).stream(MESSAGES):
            pass


async def test_a_line_that_is_not_json_is_a_protocol_error():
    def handler(request):
        return httpx.Response(200, content=b"not json at all\n")

    with pytest.raises(LlmProtocolError, match="not JSON"):
        async for _ in provider_with(handler).stream(MESSAGES):
            pass


# ── The estimator ───────────────────────────────────────────────────────────


def test_an_empty_message_still_costs_something():
    """The chat template wraps every message in turn delimiters. A message list whose
    estimate can be zero is a budget that can be talked past with empty turns."""
    assert estimate_tokens("") >= 1
    assert estimate_messages([ChatMessage(role="user", content="")]) >= 4


def test_the_estimate_grows_with_the_text():
    short = estimate_tokens("Hello.")
    long = estimate_tokens("Hello. " * 100)
    assert long > short * 50


def test_the_per_message_overhead_is_counted():
    """Two messages of n characters must estimate higher than one of 2n. The difference
    is the delimiters, and over a forty-message history it decides whether the prompt
    fits."""
    one = estimate_messages([ChatMessage(role="user", content="a" * 200)])
    two = estimate_messages(
        [
            ChatMessage(role="user", content="a" * 100),
            ChatMessage(role="assistant", content="a" * 100),
        ]
    )
    assert two > one
