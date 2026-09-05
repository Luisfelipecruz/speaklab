"""Error detection against the hand-labelled golden set: real transcripts, a real model.

**Skipped unless a live model is reachable**, like the other measurement suites here.
`make test` and CI point `OLLAMA_BASE_URL` at a host that does not resolve, because the
unit suites need a provider that is down. To run this one:

    make error-precision

**Part of the golden set is not in this repository.** It is real recorded speech, and some
of it is a person talking about their actual job. What ships is the role-play half;
`manifest.local.json` is the union and is used instead when it is there. The report names
which file it read, because the two are different sample sizes and a figure without its n
is not a figure.

**What is asserted and what is only reported.** Nothing here asserts a precision figure,
and that is not caution — it is arithmetic. The published set is four real turns carrying
five labelled errors. A run produces a handful of countable proposals, and a precision
computed over four or six trials has a 95 % interval roughly half the width of the scale.
Asserting 0.70 against that would be a gate that passes or fails on one proposal, which
measures the coin rather than the detector. So the numbers are printed, and what is
*asserted* is the machinery: every accepted error points at real text, every rejection
carries a reason from the closed list, and a clean turn produces no errors.

The figure this exists to produce becomes meaningful as the corpus grows, and the corpus
grows by somebody holding a conversation with the product. Re-run it then.

**Three ways a proposal is scored.**

- *counted* — it overlaps a labelled learner error. It is a true positive if it also
  named the right category, and a mislabelling otherwise.
- *excluded* — it overlaps a word the recogniser was unsure of, or a label marked as a
  recogniser artefact or as genuinely arguable. Neither credited nor penalised: nobody
  can say whether the speaker made that mistake.
- *false positive* — everything else.

Excluding rather than penalising is the same rule the product applies to its own trends,
applied to its own evaluation. Scoring those proposals either way would be inventing an
answer to a question the transcript cannot settle.
"""

import json
from pathlib import Path
from typing import get_args

import httpx
import pytest

from config import ASR_CONFIDENCE_FLOOR, OLLAMA_BASE_URL, OLLAMA_MODEL
from services.errors import detect, low_confidence_spans
from services.llm import OllamaProvider
from services.taxonomy import CATEGORIES, RejectionReason
from tests.eval_out import record

_HERE = Path(__file__).resolve().parent
GOLDEN = next(
    (
        path
        for path in (
            Path("/app/eval/golden/errors"),
            _HERE.parents[1] / "eval" / "golden" / "errors",
        )
        if (path / "manifest.json").is_file()
    ),
    Path("/app/eval/golden/errors"),
)


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
pytestmark = pytest.mark.skipif(not READY, reason=WHY_NOT or "no model")


@pytest.fixture(scope="module")
def golden() -> dict:
    """The largest set available here, and it says which one that was.

    A golden set of real speech is somebody's real speech, so part of this one is not in
    the repository. `manifest.local.json` is the union and is preferred when it exists;
    `manifest.json` is what a clone gets. The two produce different figures over
    different numbers of turns, which is exactly why the report names the file.
    """
    for name in ("manifest.local.json", "manifest.json"):
        manifest = GOLDEN / name
        if manifest.is_file():
            loaded = json.loads(manifest.read_text())
            loaded["source"] = name
            return loaded
    pytest.skip(f"{GOLDEN} has no manifest — run eval/golden/errors/build.py")


def _overlaps(a_start, a_end, b_start, b_end) -> bool:
    return a_start < b_end and b_start < a_end


def _best_label(accepted, labels: list[dict]) -> dict | None:
    """The label a proposal lands on, preferring a real error over an excluded one."""
    hits = [
        label
        for label in labels
        if _overlaps(
            accepted.span_start,
            accepted.span_end,
            label["span_start"],
            label["span_end"],
        )
    ]
    if not hits:
        return None
    return next((hit for hit in hits if hit["kind"] == "error"), hits[0])


async def test_error_detection_against_the_hand_labelled_set(golden, capsys):
    provider = OllamaProvider()

    true_positives = mislabelled = false_positives = excluded = 0
    proposed = rejected = 0
    reasons: dict[str, int] = {}
    lines: list[str] = []

    for item in golden["items"]:
        detection = await detect(provider, item["transcript"], item["words"])
        proposed += detection.proposed
        rejected += len(detection.rejected)
        for rejection in detection.rejected:
            assert rejection.reason in get_args(RejectionReason), (
                f"{rejection.reason} is not one of the reasons this system can give; "
                "a rejection nobody can group by is a rejection nobody can act on"
            )
            reasons[rejection.reason] = reasons.get(rejection.reason, 0) + 1

        lines.append(
            f"turn {item['turn_id']:>3}  {detection.status:<12} "
            f"accepted {len(detection.errors)}  rejected {len(detection.rejected)}"
        )

        for found in detection.errors:
            accepted = found.accepted

            # The gate below is what the whole span-validation design is for: an error
            # whose text is not in the transcript is a location the model invented.
            assert (
                item["transcript"][accepted.span_start : accepted.span_end]
                == accepted.original
            ), "an accepted error does not point at the text it claims to quote"
            assert accepted.category in CATEGORIES

            label = _best_label(accepted, item["labels"])
            if found.asr_suspect or (label and label["kind"] != "error"):
                verdict = "excluded"
                excluded += 1
            elif label and label["category"] == accepted.category:
                verdict = "true positive"
                true_positives += 1
            elif label:
                verdict = f"mislabelled {accepted.category} for {label['category']}"
                mislabelled += 1
            else:
                verdict = "false positive"
                false_positives += 1

            lines.append(
                f"        {verdict:<38} {accepted.category}/{accepted.subcategory} "
                f"{accepted.original!r} -> {accepted.correction!r}"
            )

    labelled = true_positives + mislabelled + false_positives
    gold_errors = [
        label
        for item in golden["items"]
        for label in item["labels"]
        if label["kind"] == "error"
    ]
    reachable = sum(
        1
        for item in golden["items"]
        for label in item["labels"]
        if label["kind"] == "error"
        and not any(
            _overlaps(label["span_start"], label["span_end"], start, end)
            for start, end in low_confidence_spans(item["transcript"], item["words"])
        )
    )

    detection_precision = (
        (true_positives + mislabelled) / labelled if labelled else None
    )
    labelling_precision = true_positives / labelled if labelled else None

    report = "\n".join(
        [
            "",
            *lines,
            "",
            f"model                     {provider.model}",
            f"golden set                {golden['source']}",
            f"turns                     {len(golden['items'])}, "
            f"{golden['word_count']} words",
            f"labelled errors           {len(gold_errors)}, "
            f"{reachable} clear of the {ASR_CONFIDENCE_FLOOR} per-word gate",
            f"proposals                 {proposed}",
            f"rejected by the taxonomy  {rejected}"
            + (f" ({rejected / proposed:.1%})" if proposed else ""),
            f"  reasons                 {reasons or '{}'}",
            f"scored                    {labelled} "
            f"(excluded as unknowable: {excluded})",
            f"  true positives          {true_positives}",
            f"  right span, wrong label {mislabelled}",
            f"  false positives         {false_positives}",
            # `is not None` rather than a truth test: a precision of zero is a
            # measurement and printing it as "n/a" would hide the worst result there is.
            "detection precision       "
            + (
                f"{detection_precision:.3f}"
                if detection_precision is not None
                else "n/a"
            ),
            "labelling precision       "
            + (
                f"{labelling_precision:.3f}"
                if labelling_precision is not None
                else "n/a"
            ),
            "detection recall          "
            + (
                f"{(true_positives + mislabelled) / reachable:.3f}"
                if reachable
                else "n/a"
            ),
            "",
            f"Not asserted. {len(golden['items'])} turns and {len(gold_errors)} "
            "labelled errors are too few to place a precision figure against 0.70 with "
            "any confidence; re-run this as the corpus grows.",
        ]
    )
    with capsys.disabled():
        print(report)

    record(
        "errors",
        {
            "status": "measured",
            "model": provider.model,
            "golden_set": golden["source"],
            "turns": len(golden["items"]),
            "words": golden["word_count"],
            "labelled_errors": len(gold_errors),
            "reachable": reachable,
            "proposed": proposed,
            "rejected": rejected,
            "rejection_reasons": reasons,
            "scored": labelled,
            "excluded": excluded,
            "true_positives": true_positives,
            "mislabelled": mislabelled,
            "false_positives": false_positives,
        },
    )

    assert proposed >= 0


async def test_a_clean_turn_produces_no_errors(golden):
    """The false-positive floor, and the one assertion in this file with teeth.

    A detector that finds a mistake in "That was amazing. Thank you." is a detector that
    will find one anywhere, and no precision figure computed over anything else would be
    worth reading.
    """
    clean = next(
        (item for item in golden["items"] if not item["labels"]),
        None,
    )
    if clean is None:
        pytest.skip("the golden set has no unlabelled turn to check against")

    detection = await detect(OllamaProvider(), clean["transcript"], clean["words"])
    counted = [found for found in detection.errors if not found.asr_suspect]
    assert not counted, (
        f"errors were proposed for a turn with none: "
        f"{[found.accepted.original for found in counted]}"
    )
