"""The measurement suite: real audio, a real recogniser, a real model, a real voice.

**Skipped unless all three services answer**, which is the correct default and not a
compromise. `make test` and CI both point every model URL at a host that cannot resolve,
because the health tests need an absent model layer; a suite that quietly reached for
three containers and an LLM would not be a suite anybody runs on a laptop. To run it:

    make up            # postgres, api, asr, tts
    make turn-latency  # this file, against all of them

What is asserted versus what is reported follows the precedent m4 set and for the same
reason. **Reported:** every latency. They are taken on whatever machine happens to be
running, and a threshold in a unit test fails on a laptop mid-compile while the code is
perfect. **Asserted:** the things that are true or false regardless of speed — that a
turn returns a transcript, a reply and playable audio; that the persona is in the prompt;
that the token budget is respected in the counts the server itself reports.

The numbers this prints are the ones in `docs/decisions/0003-conversation-context-strategy.md`,
and that document is where the 3-second budget of PRD §9.1 is actually adjudicated.

**On the audio.** The four shortest clips of the m4 golden set, 4.45 s to 6.82 s, cycled.
LibriSpeech read speech is not conversational speech and the substitution is worth naming
— a real learner's turn is more disfluent and would transcribe slower — but the durations
land where §9.1's budget assumes (~6 s), which is the property the measurement needs.
"""

import json
import os
import statistics
import time
from pathlib import Path

import httpx
import pytest

from config import ASR_URL, OLLAMA_BASE_URL, TTS_URL
from services.conversation import build_messages, system_message
from services.llm import ChatMessage, OllamaProvider, estimate_messages
from tests.conftest import API_ROOT, register_account, unique_email

# The m4 golden set, in whichever layout this is running in: `/app/eval` when the suite
# runs in the container, and a sibling of `api/` on a CI runner. Copied from
# `test_asr_golden.py` rather than paraphrased, because paraphrasing it broke twice over:
#
#   * `Path(API_ROOT).parent` strips the trailing `..` instead of following it, so it
#     resolved to `api/tests/` — `.resolve()` first is what makes `.parent` mean the
#     repository root;
#   * and `next()` without a default raises `StopIteration` **at import**, which pytest
#     reports as a collection error and which aborts the entire suite rather than
#     skipping one module.
#
# Both only appear where `eval/` is a sibling of `api/`, which is never true in the
# container and always true on a runner — so CI was the only place either could be seen.
GOLDEN = next(
    (
        candidate
        for candidate in (
            Path("/app/eval/golden/asr"),
            Path(API_ROOT).resolve().parent / "eval/golden/asr",
        )
        if (candidate / "manifest.json").exists()
    ),
    None,
)

SLUG = "job-interview-backend"


def _answers(url: str, path: str = "/health") -> bool:
    try:
        return httpx.get(f"{url}{path}", timeout=3.0).is_success
    except Exception:
        return False


def _ollama_ready() -> bool:
    try:
        tags = httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=3.0)
        if not tags.is_success:
            return False
        model = os.environ.get("OLLAMA_MODEL", "gemma3:4b")
        return any(
            entry["name"].startswith(model.split(":")[0])
            for entry in tags.json().get("models", [])
        )
    except Exception:
        return False


live = pytest.mark.skipif(
    GOLDEN is None or not (_answers(ASR_URL) and _answers(TTS_URL) and _ollama_ready()),
    reason=(
        "needs the golden corpus plus a live asr, tts and Ollama. Run `make up` and then "
        f"`make turn-latency`; tried ASR_URL={ASR_URL} TTS_URL={TTS_URL} "
        f"OLLAMA_BASE_URL={OLLAMA_BASE_URL}, golden={GOLDEN}"
    ),
)


def clips() -> list[tuple[str, bytes, float]]:
    """The four shortest golden utterances: id, bytes, duration."""
    manifest = json.loads((GOLDEN / "manifest.json").read_text())
    chosen = sorted(manifest["items"], key=lambda item: item["duration_s"])[:4]
    return [
        (item["id"], (GOLDEN / item["file"]).read_bytes(), item["duration_s"])
        for item in chosen
    ]


def percentile(values: list[float], fraction: float) -> float:
    """Nearest-rank. Twenty samples, so an interpolating definition would invent
    precision the sample size does not support."""
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(fraction * len(ordered)) - 1))
    return ordered[index]


def load_average() -> str:
    """The machine's load at the moment of measurement.

    Printed beside every table because it is the single most important thing about a
    latency number taken on a developer's laptop, and because m5's suite established the
    habit for exactly this reason: the same code measured at load 3 and at load 40
    produces two numbers that otherwise look like a regression.
    """
    one, five, fifteen = os.getloadavg()
    return f"{one:.2f} {five:.2f} {fifteen:.2f}"


def report(label: str, values: list[float]) -> None:
    print(
        f"  {label:24} n={len(values):3}  "
        f"mean={statistics.mean(values):7.0f}  median={statistics.median(values):7.0f}  "
        f"p95={percentile(values, 0.95):7.0f}  max={max(values):7.0f}"
    )


# ── The whole turn ──────────────────────────────────────────────────────────


@live
async def test_a_whole_turn_end_to_end(seeded, client, audio_root):
    """The milestone's own gate: a real recording in, transcript + reply + audio out,
    twenty times, with the stage breakdown printed.

    The assertions are the ones that hold on any machine. The latency table is printed
    rather than asserted and lands in decision 0003, where it is compared against the
    §9.1 budget under stated conditions instead of against whatever else this laptop is
    doing.
    """
    import config

    await register_account(client, email=unique_email("live"))
    session = (await client.post("/sessions", json={"scenario_slug": SLUG})).json()
    assert session["turns"][0]["transcript"], "the persona produced no opening line"

    audio = clips()
    turns = 20

    totals, asr, generation, synthesis, replies = [], [], [], [], []
    prompt_tokens, completion_tokens, sentence_counts = [], [], []
    cold_loads = []

    print(f"\n\nstream_to_tts = {config.LLM_STREAM_TO_TTS}")
    print(f"audio: {', '.join(f'{d:.2f}s' for _, _, d in audio)}, cycled")
    print(f"load at start: {load_average()}\n")

    for number in range(turns):
        clip_id, data, _ = audio[number % len(audio)]
        started = time.perf_counter()
        response = await client.post(
            f"/sessions/{session['id']}/turns",
            files={"file": (f"{clip_id}.flac", data, "audio/flac")},
        )
        wall_ms = (time.perf_counter() - started) * 1000

        assert response.status_code == 201, response.text
        body = response.json()

        assert body["user_turn"]["transcript"], "no transcript"
        assert body["reply_turn"]["transcript"], "no reply"
        assert body["speech"]["status"] == "ok", body["speech"]
        assert body["reply_turn"]["audio_url"], "no reply audio"

        timing = body["timing"]
        totals.append(wall_ms)
        asr.append(timing["asr_ms"])
        generation.append(timing["generation_ms"])
        synthesis.append(timing["synthesis_ms"])
        replies.append(timing["reply_ms"])
        sentence_counts.append(body["speech"]["sentences"])
        if timing["prompt_tokens"]:
            prompt_tokens.append(timing["prompt_tokens"])
        if timing["completion_tokens"]:
            completion_tokens.append(timing["completion_tokens"])
        # A warm model still reports a load_duration of a millisecond or two. Only a
        # genuinely cold one — hundreds of milliseconds — is worth separating out.
        if (timing["model_load_ms"] or 0) > 250:
            cold_loads.append(timing["model_load_ms"])

    print("milliseconds, over the whole run:")
    report("turn, wall clock", totals)
    report("  asr", asr)
    report("  generation", generation)
    report("  synthesis (tail)", synthesis)
    report("  reply (gen+tts)", replies)
    # No within-run figure for what the overlap bought, and that is a considered
    # omission rather than a gap. Two attempts at one were both wrong: the sum of
    # per-sentence latencies counts the tts service's queue once per sentence, and the
    # makespan from first dispatch to last completion necessarily spans the generation it
    # overlaps. The honest instrument is the A/B — run `make turn-latency` and then
    # `make turn-latency-noflow` and compare the `synthesis (tail)` row, which means the
    # same thing in both configurations.
    print(
        f"  prompt tokens     median {statistics.median(prompt_tokens):.0f}, "
        f"max {max(prompt_tokens)} (budget {config.LLM_MAX_INPUT_TOKENS})"
    )
    print(
        f"  reply tokens      median {statistics.median(completion_tokens):.0f}, "
        f"max {max(completion_tokens)} (cap {config.LLM_MAX_OUTPUT_TOKENS})"
    )
    print(f"  sentences/reply   median {statistics.median(sentence_counts):.0f}")
    print(
        f"  cold model loads  {len(cold_loads)} of {turns}"
        + (f", {cold_loads} ms" if cold_loads else "")
    )
    print(f"  load at end       {load_average()}")

    budget = 3000
    p95 = percentile(totals, 0.95)
    print(
        f"\n  p95 = {p95:.0f} ms against a {budget} ms budget: "
        f"{'MET' if p95 <= budget else 'MISSED by ' + str(round(p95 - budget)) + ' ms'}\n"
    )

    # The token budget is asserted, because it is a correctness property rather than a
    # speed one. Exceeding it does not make a turn slow — it makes llama.cpp silently
    # discard half the prompt, persona included (config.LLM_NUM_CTX).
    assert max(prompt_tokens) <= config.LLM_MAX_INPUT_TOKENS, (
        f"a prompt of {max(prompt_tokens)} tokens was sent against a budget of "
        f"{config.LLM_MAX_INPUT_TOKENS}; the estimator is under-counting"
    )
    # No latency assertion, deliberately, and this is m4's precedent rather than a
    # concession. A threshold here fails on a laptop with a compile going while the code
    # is perfect — and on the machine this was written on it did exactly that, at load 23
    # with an Android emulator and two other Docker stacks running. What this suite
    # asserts is what is true at any speed: a turn returns a transcript, a reply and
    # playable audio, and the prompt stayed inside the budget. The p95 line above is
    # printed for a human, and decision 0003 is where it is adjudicated against §9.1
    # with the machine's load stated beside it.


# ── The fallback, measured against its control ──────────────────────────────


@live
async def test_the_estimator_against_the_count_the_server_reports():
    """How wrong `estimate_tokens` is, measured rather than assumed.

    The estimate decides what to send and Ollama's `prompt_eval_count` says what was
    actually read. The constant is 4.0 characters per token and English prose runs
    nearer 4.6, so this should over-count — and over-counting is the safe direction:
    it spends context that was available, where under-counting walks off the cliff in
    config.LLM_NUM_CTX and loses half the conversation with no error.
    """
    import config

    provider = OllamaProvider()
    prompts = {
        "short": [ChatMessage(role="user", content="Hello, how are you today?")],
        "persona-sized": [
            ChatMessage(
                role="system",
                content="You are Dana, a hiring manager. "
                + "Ask a follow-up question. " * 40,
            ),
            ChatMessage(role="user", content="I worked on payments for four years."),
        ],
        "long history": [
            ChatMessage(
                role="user" if index % 2 == 0 else "assistant",
                content=f"Turn {index}. "
                + "This is a sentence of ordinary prose. " * 6,
            )
            for index in range(30)
        ],
    }

    print("\n\n  prompt           estimated  actual   error")
    errors = []
    for label, messages in prompts.items():
        estimated = estimate_messages(messages)
        completion = await provider.complete(messages, max_tokens=1)
        actual = completion.prompt_tokens
        error = (estimated - actual) / actual
        errors.append(error)
        print(f"  {label:16} {estimated:9} {actual:7}  {error:+7.1%}")

    mean_error = statistics.mean(errors)
    worst = min(errors)
    print(f"\n  mean error {mean_error:+.1%}, worst under-count {worst:+.1%}")
    print(
        f"  LLM_ESTIMATOR_MARGIN is {config.LLM_ESTIMATOR_MARGIN}, so num_ctx is "
        f"{config.LLM_NUM_CTX} for a {config.LLM_MAX_INPUT_TOKENS}-token budget\n"
    )

    # The assertion is about the **margin**, not about the estimate. A heuristic over
    # characters cannot be accurate across text shapes — repeated instructions tokenise
    # near 3.7 characters per token, ordinary prose nearer 4.6 — and pretending otherwise
    # would mean tuning a constant until this passed. What has to remain true is that the
    # margin the context window is sized from still covers the error.
    assert worst > -(1 - 1 / config.LLM_ESTIMATOR_MARGIN), (
        f"the estimator under-counted by {worst:.1%}, which LLM_ESTIMATOR_MARGIN of "
        f"{config.LLM_ESTIMATOR_MARGIN} no longer covers. Raise the margin: the cost of "
        "getting this wrong is not a rejected request, it is half the prompt silently "
        "discarded (config.LLM_NUM_CTX)."
    )


@live
async def test_persona_adherence_over_a_long_conversation(seeded, db_session):
    """Does anchoring the persona twice do anything on a model with no system role?

    Measured with two **deterministic** proxies rather than a judge, because a language
    model grading a language model's persona adherence is exactly the shape invariant I1
    forbids, and m11 is where adherence gets evaluated properly. The seeded personas ask
    for two or three sentences and for a reply that ends with a question, so both are
    checkable by counting.

    **The history has to be long or this measures nothing.** The first version of this
    ran both arms against an empty conversation and returned 100 % on every cell — which
    is the correct answer to a question nobody was asking. R7 is about drift *over a long
    conversation*, and the whole reason for the tail anchor is that the front anchor ends
    up far from where the reply is written. So the arms differ only in whether the
    persona is repeated near the end, and both carry thirty turns of history.

    Reported, not asserted, and the sample size is stated with the result. Twenty-five
    replies an arm resolves a large effect and nothing subtler: at 25 the 95 % interval
    on a proportion near 1.0 is still several points wide, so "100 % versus 96 %" is one
    reply and means nothing. Decision 0003 says so beside the numbers.
    """
    from sqlalchemy import select

    from db_models import Scenario, Turn
    from services.conversation import _who_is_speaking

    scenario = await db_session.scalar(select(Scenario).where(Scenario.slug == SLUG))
    provider = OllamaProvider()
    rounds = int(os.environ.get("ADHERENCE_ROUNDS", "25"))

    # Thirty turns of plausible interview, unsaved. Enough that the front anchor is a
    # long way from the end of the prompt, which is the condition being tested.
    history = [
        Turn(
            idx=index,
            role="user" if index % 2 == 0 else "assistant",
            transcript=(
                f"In {2012 + index // 2} I worked on the billing platform and it was "
                "mostly queues and retries."
                if index % 2 == 0
                else "That is interesting. What did you change about it?"
            ),
        )
        for index in range(30)
    ]

    results = {}
    for arm in ("both anchors", "front anchor only"):
        within_cap, ends_with_question = 0, 0
        for index in range(rounds):
            utterance = f"I also led the migration for team number {index} that year."
            if arm == "both anchors":
                messages = build_messages(scenario, None, history, utterance)
            else:
                # The same prompt with the tail anchor removed: persona at the front,
                # then the history, then what was just said.
                messages = [system_message(scenario, None)]
                messages.extend(
                    ChatMessage(role=turn.role, content=turn.transcript)
                    for turn in history
                )
                messages.append(ChatMessage(role="user", content=utterance))

            completion = await provider.complete(messages, max_tokens=200)
            text = completion.text.strip()
            sentences = [
                part
                for part in text.replace("!", ".").replace("?", ".").split(".")
                if part.strip()
            ]
            within_cap += len(sentences) <= 4
            ends_with_question += text.endswith("?")

        results[arm] = (within_cap / rounds, ends_with_question / rounds)

    print(f"\n\n  persona: {_who_is_speaking(scenario.persona_prompt)}")
    print(f"  {len(history)} turns of history, n = {rounds} replies per arm\n")
    print(f"  {'arm':20} {'<= 4 sentences':>16} {'ends with ?':>13}")
    for arm, (cap, question) in results.items():
        print(f"  {arm:20} {cap:>15.0%} {question:>13.0%}")
    print()


@live
async def test_the_persona_never_addresses_the_speaker_by_a_placeholder():
    """The name guardrail, against the real model, on the scenario that reproduced it.

    **Found by using the product, not by a test.** A real nine-turn standup on 2026-08-30
    (session 13) had the scrum master say "Good morning, [User Name]." — three times in
    five replies. Across every session stored at that point the rate was 4 of 7 assistant
    turns on `daily-standup` and **0 on every other scenario**: the persona says "Greet the
    user", and a greeting in a standup is a template slot in most of the text gemma3:4b was
    trained on. No prompt in this system has ever contained a placeholder.

    The opening turn is where it is near-deterministic, which is why this measures that
    rather than a mid-conversation reply. Measured on 2026-08-30: **12/12 without the
    instruction, 0/12 with it.** The gate here is 0 out of 12 rather than "fewer than
    before", because a persona that addresses somebody as [User Name] is not a degraded
    experience, it is a broken one.
    """
    import re
    from types import SimpleNamespace

    from services import conversation as conversation_module

    placeholder = re.compile(r"\[[A-Za-z][A-Za-z ]*\]")
    persona = (
        "You are Marcus, the scrum master running a daily standup for a five-person team. "
        "Greet the user and ask for their update. Listen for three things — yesterday, "
        "today, blockers — and ask for whichever one they leave out."
    )
    scenario = SimpleNamespace(
        persona_prompt=persona, goal="Run a crisp standup and surface any blocker."
    )

    provider = OllamaProvider()
    n = 12
    hits: list[str] = []
    for _ in range(n):
        messages = conversation_module.build_messages(scenario, None, [], None)
        completion = await provider.complete(messages, max_tokens=120)
        found = placeholder.search(completion.text)
        if found:
            hits.append(completion.text.strip().splitlines()[0][:90])

    print(f"\n  opening turn, daily-standup persona, n = {n}")
    print(f"  replies containing a placeholder: {len(hits)}")
    for example in hits[:3]:
        print(f"    {example}")
    print("  measured 2026-08-30: 12/12 without the name guardrail, 0/12 with it")

    assert not hits, (
        f"{len(hits)}/{n} replies addressed the speaker by a placeholder. The name "
        f"guardrail in services/conversation.GUARDRAILS has stopped working."
    )
