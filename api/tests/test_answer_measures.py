"""The spoken answer drill, measured.

How an answer is built is counted by `services/structure.py`, and each measure is scored
here against answers a person labelled (`tests/answer_labels.py`): the development set
the counter was written against, and the held-out set it was not. A measure reaches a
learner only if it clears its bar on the held-out set, and the last test asserts that
every measure `structure.SHOWN` names does — so a change to the counter that drops one
below its bar fails here, in CI, rather than on a learner's screen.

None of it needs a model. It runs in `make test` and in CI, and `make eval` collects its
figures for the report.
"""

from __future__ import annotations

import json
import statistics
from collections import Counter

import httpx
import pytest

from config import ANSWER_REWRITE_MAX_INVENTED, OLLAMA_BASE_URL, OLLAMA_MODEL
from scripts.seed import SEEDS_DIR
from services import answer_feedback, structure
from services.answer_feedback import invented
from services.llm import OllamaProvider
from tests import rewrite_labels
from tests.answer_labels import DEVELOPMENT, HELD_OUT, KINDS, Answer
from tests.eval_out import load_harness, record

PROMPTS = {
    item["slug"]: item["prompt"]
    for item in json.loads((SEEDS_DIR / "prompts.json").read_text())
}


def score(answers: list[Answer]) -> dict[str, dict]:
    """Per kind: marked, found, found where marked, and what was missed or extra.

    A found item counts where it overlaps a marked stretch of the same kind, each mark
    and each find used once.
    """
    tallies = {
        kind: {"marked": 0, "found": 0, "matched": 0, "missed": [], "extra": []}
        for kind in KINDS
    }
    for answer in answers:
        found = structure.analyse(answer.transcript).found
        for kind in KINDS:
            marked = answer.of(kind)
            finds = [item for item in found if item.kind == kind]
            used: set[int] = set()
            tally = tallies[kind]
            for left, right in marked:
                hit = next(
                    (
                        index
                        for index, item in enumerate(finds)
                        if index not in used and item.start < right and left < item.end
                    ),
                    None,
                )
                if hit is None:
                    tally["missed"].append(_context(answer.transcript, left, right))
                else:
                    used.add(hit)
                    tally["matched"] += 1
            for index, item in enumerate(finds):
                if index not in used:
                    tally["extra"].append(
                        _context(answer.transcript, item.start, item.end)
                    )
            tally["marked"] += len(marked)
            tally["found"] += len(finds)
    return tallies


def _context(text: str, left: int, right: int) -> str:
    """The stretch in brackets with a few words either side."""
    before = text[max(0, left - 40) : left].split(" ", 1)[-1]
    after = text[right : right + 40].rsplit(" ", 1)[0]
    return f"…{before}[{text[left:right]}]{after}…"


def clears(tally: dict) -> bool:
    """Whether a measure clears its bar: precision, recall, and enough instances."""
    if tally["marked"] < structure.MIN_INSTANCES or not tally["found"]:
        return False
    precision = tally["matched"] / tally["found"]
    recall = tally["matched"] / tally["marked"]
    return precision >= structure.MIN_PRECISION and recall >= structure.MIN_RECALL


def test_how_an_answer_is_built_is_counted_against_answers_held_out(capsys):
    scoring = load_harness("scoring")
    held_out = score(HELD_OUT)
    development = score(DEVELOPMENT)

    with capsys.disabled():
        print(
            f"\n  bars: precision {structure.MIN_PRECISION}, recall "
            f"{structure.MIN_RECALL}, {structure.MIN_INSTANCES} marked"
        )
        for name, tallies in (("development", development), ("held out", held_out)):
            print(f"  {name}")
            for kind, tally in tallies.items():
                precision = scoring.proportion(tally["matched"], tally["found"])
                recall = scoring.proportion(tally["matched"], tally["marked"])
                print(
                    f"    {kind:<9} precision {precision.format()}   "
                    f"recall {recall.format()}"
                    + ("" if name == "development" or clears(tally) else "   BELOW")
                )
        for kind, tally in held_out.items():
            for item in tally["missed"]:
                print(f"    held out, {kind} missed: {item}")
            for item in tally["extra"]:
                print(f"    held out, {kind} extra:  {item}")

    record(
        "structure",
        {
            "status": "measured",
            "bars": {
                "precision": structure.MIN_PRECISION,
                "recall": structure.MIN_RECALL,
                "instances": structure.MIN_INSTANCES,
            },
            "answers": {"development": len(DEVELOPMENT), "held_out": len(HELD_OUT)},
            "held_out": held_out,
            "development": {
                kind: {key: tally[key] for key in ("marked", "found", "matched")}
                for kind, tally in development.items()
            },
            "shown": sorted(structure.SHOWN),
        },
    )

    below = [
        kind for kind in KINDS if kind in structure.SHOWN and not clears(held_out[kind])
    ]
    assert (
        not below
    ), f"shown to learners but below the bar on the held-out set: {below}"


# ── The check on the model's rewrite ────────────────────────────────────────


def check_rewrites(items: list[rewrite_labels.Rewrite]) -> dict:
    """How the check does on rewrites marked as adding a fact or not."""
    tally = {
        "adds_a_fact": 0,
        "adds_a_fact_withheld": 0,
        "faithful": 0,
        "faithful_shown": 0,
        "wrong": [],
    }
    for item in items:
        words = invented(item.answer, PROMPTS[item.prompt], item.rewrite)
        withheld = len(words) > ANSWER_REWRITE_MAX_INVENTED
        if item.adds_a_fact:
            tally["adds_a_fact"] += 1
            tally["adds_a_fact_withheld"] += withheld
        else:
            tally["faithful"] += 1
            tally["faithful_shown"] += not withheld
        if withheld != item.adds_a_fact:
            tally["wrong"].append({"rewrite": item.rewrite, "invented": words})
    return tally


def test_the_rewrite_check_against_rewrites_written_to_add_a_fact_or_not(capsys):
    development = check_rewrites(rewrite_labels.DEVELOPMENT)
    held_out = check_rewrites(rewrite_labels.HELD_OUT)

    with capsys.disabled():
        print(f"\n  limit: more than {ANSWER_REWRITE_MAX_INVENTED} new content words")
        for name, tally in (("development", development), ("held out", held_out)):
            print(
                f"  {name:<12} adds a fact, withheld {tally['adds_a_fact_withheld']} of "
                f"{tally['adds_a_fact']}; faithful, shown {tally['faithful_shown']} of "
                f"{tally['faithful']}"
            )
            for wrong in tally["wrong"]:
                print(f"    wrong: {wrong['invented']} in {wrong['rewrite']!r}")

    record(
        "rewrite_check",
        {
            "status": "measured",
            "limit": ANSWER_REWRITE_MAX_INVENTED,
            "development": development,
            "held_out": held_out,
        },
    )

    # The limit was chosen on the development rewrites, which it separates.
    assert development["wrong"] == []
    # The bar set before the held-out rewrites were scored.
    assert held_out["adds_a_fact_withheld"] >= held_out["adds_a_fact"] - 1
    assert held_out["faithful_shown"] >= held_out["faithful"] - 1


# ── The model's feedback on the labelled answers ────────────────────────────


def _model_ready() -> tuple[bool, str]:
    try:
        response = httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5.0)
    except httpx.RequestError as exc:
        return False, f"{OLLAMA_BASE_URL} is not answering ({type(exc).__name__})"
    names = {model.get("name") for model in response.json().get("models", [])}
    if OLLAMA_MODEL not in names:
        return False, f"{OLLAMA_MODEL} is not pulled on {OLLAMA_BASE_URL}"
    return True, ""


READY, WHY_NOT = _model_ready()
needs_model = pytest.mark.skipif(not READY, reason=WHY_NOT or "no model")


@needs_model
async def test_the_models_feedback_on_the_labelled_answers(capsys):
    """Every labelled answer given to the model as a learner's answer would be.

    What is counted is what the product has to be able to say about the model: how often
    it answers in the shape asked for, how often its shorter version brings in words the
    speaker never said and is withheld for it, whether the shorter version really has
    fewer sentences, and how often it comments on how an answer sounded, which it cannot
    have heard. Reported, not asserted, beyond the call working; one model.
    """
    provider = OllamaProvider()
    answers = DEVELOPMENT + HELD_OUT
    statuses: Counter[str] = Counter()
    # Withheld per set: the instruction was revised against the development answers, so
    # the held-out ones are the figure that says whether the revision generalised.
    by_set = {
        name: {"answers": len(items), "withheld": 0}
        for name, items in (("development", DEVELOPMENT), ("held_out", HELD_OUT))
    }
    invented_counts: list[int] = []
    shorter = dropped = 0
    latencies: list[int] = []
    withheld: list[dict] = []

    for index, answer in enumerate(answers):
        result = await answer_feedback.ask(
            provider, PROMPTS[answer.prompt], answer.transcript
        )
        statuses[result["status"]] += 1
        if result["status"] == "refused":
            by_set["development" if index < len(DEVELOPMENT) else "held_out"][
                "withheld"
            ] += 1
        if result["status"] not in ("ok", "refused"):
            continue
        latencies.append(result["latency_ms"])
        dropped += result.get("dropped_notes", 0)
        rewrite = result.get("rewrite") or result.get("withheld_rewrite")
        if not rewrite:
            continue
        invented_counts.append(len(result["invented"]))
        if len(structure.sentences(rewrite)) < len(
            structure.sentences(answer.transcript)
        ):
            shorter += 1
        if result["status"] == "refused":
            withheld.append({"prompt": answer.prompt, "invented": result["invented"]})

    rewrites = len(invented_counts)
    with capsys.disabled():
        print(f"\n  {OLLAMA_MODEL}: {len(answers)} labelled answers")
        print(f"  statuses {dict(statuses)}; withheld by set {by_set}")
        print(
            f"  rewrites {rewrites}: with a new content word "
            f"{sum(1 for n in invented_counts if n)}, withheld {statuses['refused']}, "
            f"fewer sentences than the answer {shorter}; notes about sound dropped "
            f"{dropped}"
        )
        for item in withheld:
            print(f"    withheld ({item['prompt']}): {item['invented']}")

    record(
        "answers",
        {
            "status": "measured",
            "model": OLLAMA_MODEL,
            "answers": len(answers),
            "statuses": dict(statuses),
            "by_set": by_set,
            "limit": ANSWER_REWRITE_MAX_INVENTED,
            "rewrites": rewrites,
            "with_new_words": sum(1 for n in invented_counts if n),
            "new_words": sum(invented_counts),
            "withheld": statuses["refused"],
            "shorter": shorter,
            "dropped_notes": dropped,
            "median_latency_ms": statistics.median(latencies) if latencies else None,
            "withheld_examples": withheld,
        },
    )

    assert sum(statuses.values()) == len(answers)
    # The call, not the model's judgement: a model that never answers is not measured.
    assert statuses["unavailable"] == 0
