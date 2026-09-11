"""Error detection against the hand-labelled golden set: real transcripts, a real model.

**The golden-set test is skipped unless a live model is reachable**, like the other
measurement suites here. `make test` and CI point `OLLAMA_BASE_URL` at a host that does
not resolve, because the unit suites need a provider that is down. To run it:

    make error-precision

**Part of the golden set is not in this repository.** It is real recorded speech, and some
of it is a person talking about their actual job. What ships is the role-play half;
`manifest.local.json` is the union and is used instead when it is there. The report names
which file it read, because the two are different sample sizes and a figure without its n
is not a figure.

**Three readings of one run.** There are two detectors — the language model, and the rule
layer in `services/rules.py` — and one product, which stores what the rules proposed and
what the model proposed that a rule had not already. Each is scored on its own. The model
is scored on everything it proposed that passed the gate, including what a rule
superseded, so its figure is the model's and not the model's plus a rule's. A layer that
improved the product while hiding the model's own rate would read as the model getting
better, and it did not.

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

**And two measurements that need no model.** The golden set holds almost nothing the rule
layer covers, so on its own it cannot say what the layer is worth. Planted errors can: the
native English in `tests/native_text.py`, with one verb put out of agreement or one
indefinite article taken away at a time, each copy handed to the rules. What comes back
says how many of the two errors the layer catches when a learner makes them and whether
its correction restores the words that were there.

The second is the join that files a correction under the verb form it corrects, against
the hand labels in `tests/form_labels.py` and the golden set's own. Both run everywhere,
CI included, because nothing in them is a model.
"""

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import get_args

import httpx
import pytest

from config import ASR_CONFIDENCE_FLOOR, OLLAMA_BASE_URL, OLLAMA_MODEL
from services import grammar, rules
from services.errors import detect, low_confidence_spans
from services.llm import OllamaProvider
from services.taxonomy import CATEGORIES, RejectionReason
from tests.eval_out import record
from tests.form_labels import HELD_OUT, LABELLED, golden_cases, link_one, verdict
from tests.native_text import native_texts

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
needs_model = pytest.mark.skipif(not READY, reason=WHY_NOT or "no model")


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


@dataclass
class Tally:
    """One detector's proposals, scored the three ways the module docstring gives."""

    true_positives: int = 0
    mislabelled: int = 0
    false_positives: int = 0
    excluded: int = 0

    @property
    def scored(self) -> int:
        return self.true_positives + self.mislabelled + self.false_positives

    def score(self, found, labels: list[dict]) -> str:
        accepted = found.accepted
        label = _best_label(accepted, labels)
        if found.asr_suspect or (label and label["kind"] != "error"):
            self.excluded += 1
            return "excluded"
        if label and label["category"] == accepted.category:
            self.true_positives += 1
            return "true positive"
        if label:
            self.mislabelled += 1
            return f"mislabelled {accepted.category} for {label['category']}"
        self.false_positives += 1
        return "false positive"

    def as_record(self) -> dict:
        return {
            "scored": self.scored,
            "excluded": self.excluded,
            "true_positives": self.true_positives,
            "mislabelled": self.mislabelled,
            "false_positives": self.false_positives,
        }

    def lines(self, name: str, reachable: int) -> list[str]:
        hits = self.true_positives + self.mislabelled

        def ratio(top: int, bottom: int) -> str:
            # "n/a" only for nothing scored: a precision of zero is a measurement, and
            # printing it as "n/a" would hide the worst result there is.
            return f"{top / bottom:.3f}" if bottom else "n/a"

        return [
            f"{name}",
            f"  scored                  {self.scored} "
            f"(excluded as unknowable: {self.excluded})",
            f"  true positives          {self.true_positives}",
            f"  right span, wrong label {self.mislabelled}",
            f"  false positives         {self.false_positives}",
            f"  detection precision     {ratio(hits, self.scored)}",
            f"  labelling precision     {ratio(self.true_positives, self.scored)}",
            f"  detection recall        {ratio(hits, reachable)}",
        ]


@needs_model
async def test_error_detection_against_the_hand_labelled_set(golden, capsys):
    provider = OllamaProvider()

    product, model, rule = Tally(), Tally(), Tally()
    proposed = rejected = superseded = 0
    reasons: dict[str, int] = {}
    lines: list[str] = []

    for item in golden["items"]:
        ruled = rules.propose(grammar.parse(item["transcript"]))
        detection = await detect(provider, item["transcript"], item["words"], ruled)
        proposed += detection.proposed
        rejected += len(detection.rejected)
        superseded += len(detection.superseded)
        for rejection in detection.rejected:
            assert rejection.reason in get_args(RejectionReason), (
                f"{rejection.reason} is not one of the reasons this system can give; "
                "a rejection nobody can group by is a rejection nobody can act on"
            )
            reasons[rejection.reason] = reasons.get(rejection.reason, 0) + 1

        lines.append(
            f"turn {item['turn_id']:>3}  {detection.status:<12} "
            f"stored {len(detection.errors)}  rejected {len(detection.rejected)}  "
            f"superseded {len(detection.superseded)}"
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

            verdict = product.score(found, item["labels"])
            (rule if found.detector == "rule" else model).score(found, item["labels"])
            lines.append(
                f"        {verdict:<38} {found.detector:<4} "
                f"{accepted.category}/{accepted.subcategory} "
                f"{accepted.original!r} -> {accepted.correction!r}"
            )

        for found in detection.superseded:
            verdict = model.score(found, item["labels"])
            lines.append(
                f"        {'superseded, ' + verdict:<38} llm  "
                f"{found.accepted.category}/{found.accepted.subcategory} "
                f"{found.accepted.original!r}"
            )

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
            f"model proposals           {proposed}",
            f"rejected by the taxonomy  {rejected}"
            + (f" ({rejected / proposed:.1%})" if proposed else ""),
            f"  reasons                 {reasons or '{}'}",
            f"superseded by a rule      {superseded}",
            "",
            *product.lines("the product — what a learner is shown", reachable),
            "",
            *model.lines(f"the model alone — {provider.model}", reachable),
            "",
            *rule.lines("the rule layer alone", reachable),
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
            "superseded": superseded,
            # The product's figures at the top, because the product is what S5 is about.
            **product.as_record(),
            "by_detector": {"llm": model.as_record(), "rule": rule.as_record()},
        },
    )

    assert proposed >= 0


@needs_model
async def test_a_clean_turn_produces_no_errors(golden):
    """The false-positive floor, and the one assertion in this file with teeth.

    A detector that finds a mistake in "That was amazing. Thank you." is a detector that
    will find one anywhere, and no precision figure computed over anything else would be
    worth reading. Both detectors are held to it.
    """
    clean = next(
        (item for item in golden["items"] if not item["labels"]),
        None,
    )
    if clean is None:
        pytest.skip("the golden set has no unlabelled turn to check against")

    ruled = rules.propose(grammar.parse(clean["transcript"]))
    detection = await detect(
        OllamaProvider(), clean["transcript"], clean["words"], ruled
    )
    counted = [found for found in detection.errors if not found.asr_suspect]
    assert not counted, (
        f"errors were proposed for a turn with none: "
        f"{[(found.detector, found.accepted.original) for found in counted]}"
    )


# ── The three newest scenarios' mistakes, written down ─────────────────────


@needs_model
async def test_articles_prepositions_and_false_friends_are_found(capsys):
    """The mistakes the three newest scenarios are written to draw out, each in a sentence
    with nothing else wrong in it, handed to both detectors as the recogniser would write
    it — and the corrected sentence after it.

    A scenario draws out a kind of mistake, as far as the product can tell, only if the
    detector files what it draws out under that kind. So per kind: found where the mistake
    is and filed under it; found there under another kind; not found. Of those found, how
    many carry the labelled correction — a proposal on the right words can still put the
    wrong ones in. Anything proposed elsewhere in the sentence, or anywhere in the
    corrected one, is proposed on English that is right. Reported, not asserted, beyond
    every proposal pointing at real text.
    """
    from services.wer import normalise
    from tests.category_labels import CASES

    provider = OllamaProvider()
    categories = sorted({case.category for case in CASES})
    tally = {
        category: Counter(
            sentences=0,
            found=0,
            fixed=0,
            other_kind=0,
            missed=0,
            elsewhere=0,
            corrected_flagged=0,
            failed=0,
            found_by_rule=0,
            found_by_llm=0,
        )
        for category in categories
    }
    rows: list[dict] = []
    lines: list[str] = []

    for case in CASES:
        counts = tally[case.category]
        counts["sentences"] += 1

        said = await detect(
            provider,
            case.transcript,
            None,
            rules.propose(grammar.parse(case.transcript)),
        )
        corrected = await detect(
            provider,
            case.corrected,
            None,
            rules.propose(grammar.parse(case.corrected)),
        )
        if "failed" in (said.status, corrected.status):
            counts["failed"] += 1
            lines.append(f"  failed   {case.transcript!r}")
            continue

        for text, detection in ((case.transcript, said), (case.corrected, corrected)):
            for found in detection.errors:
                accepted = found.accepted
                assert text[accepted.span_start : accepted.span_end] == (
                    accepted.original
                ), "an accepted error does not point at the text it claims to quote"

        on_it = [
            found
            for found in said.errors
            if _overlaps(
                found.accepted.span_start,
                found.accepted.span_end,
                case.span_start,
                case.span_end,
            )
        ]
        right = [found for found in on_it if found.accepted.category == case.category]
        if right:
            outcome = "found"
            counts[f"found_by_{right[0].detector}"] += 1
            accepted = right[0].accepted
            applied = (
                case.transcript[: accepted.span_start]
                + accepted.correction
                + case.transcript[accepted.span_end :]
            )
            counts["fixed"] += normalise(applied) == normalise(case.corrected)
        elif on_it:
            outcome = "other_kind"
        else:
            outcome = "missed"
        counts[outcome] += 1
        counts["elsewhere"] += len(said.errors) - len(on_it)
        counts["corrected_flagged"] += len(corrected.errors)

        proposals = [
            {
                "detector": found.detector,
                "category": found.accepted.category,
                "subcategory": found.accepted.subcategory,
                "original": found.accepted.original,
                "correction": found.accepted.correction,
            }
            for found in said.errors
        ]
        on_correct = [
            {
                "detector": found.detector,
                "category": found.accepted.category,
                "original": found.accepted.original,
                "correction": found.accepted.correction,
            }
            for found in corrected.errors
        ]
        rows.append(
            {
                "category": case.category,
                "transcript": case.transcript,
                "quote": case.quote,
                "correction": case.correction,
                "outcome": outcome,
                "proposals": proposals,
                "on_the_corrected_sentence": on_correct,
            }
        )
        lines.append(
            f"  {outcome:<10} {case.category:<15} {case.quote!r} -> "
            f"{case.correction!r}: "
            + (
                ", ".join(
                    f"{item['detector']} {item['category']} {item['original']!r}"
                    f"->{item['correction']!r}"
                    for item in proposals
                )
                or "nothing proposed"
            )
            + (f"  | corrected: {len(on_correct)} proposed" if on_correct else "")
        )

    with capsys.disabled():
        print("")
        print("\n".join(lines))
        print(f"\n  model {provider.model}, {len(CASES)} labelled sentences")
        for category in categories:
            counts = tally[category]
            print(
                f"  {category:<15} found {counts['found']:>2} of "
                f"{counts['sentences']} (rule {counts['found_by_rule']}, model "
                f"{counts['found_by_llm']}; {counts['fixed']} with the labelled "
                f"correction), under another kind "
                f"{counts['other_kind']}, missed {counts['missed']}, elsewhere "
                f"{counts['elsewhere']}, on the corrected sentence "
                f"{counts['corrected_flagged']}, failed {counts['failed']}"
            )

    record(
        "categories_detected",
        {
            "status": "measured",
            "model": provider.model,
            "by_category": {category: dict(tally[category]) for category in categories},
            "rows": rows,
        },
    )

    assert sum(counts["sentences"] for counts in tally.values()) == len(CASES)
    assert all(counts["failed"] < counts["sentences"] for counts in tally.values())


# ── Planted errors: the rule layer, with no model ───────────────────────────


def _planted(doc):
    """Every single-word error the rule layer claims to catch, planted one at a time.

    Yields (family, the text with the error in it, where the error is, the text as it
    was). The error forms are written out here rather than borrowed from the rule
    layer's own inflection, so the layer is not grading its own spelling.
    """
    text = doc.text
    for token in doc:
        lower = token.lower_
        if lower.startswith(("'", "’")):
            continue

        wrong = None
        if token.tag_ == "VBZ":
            wrong = {"is": "are", "has": "have", "does": "do"}.get(lower)
            if wrong is None and token.lemma_.lower() != lower:
                wrong = token.lemma_.lower()
        elif token.tag_ == "VBP" and lower != "am":
            wrong = {"are": "is", "have": "has", "do": "does"}.get(lower)
            if wrong is None and lower.isalpha():
                wrong = lower + (
                    "es" if lower.endswith(("s", "x", "ch", "sh", "o")) else "s"
                )
        if wrong is not None and any(
            child.dep_ in ("nsubj", "nsubjpass", "expl")
            for child in (
                token.head if token.dep_ in ("aux", "auxpass") else token
            ).children
        ):
            if token.text[:1].isupper():
                wrong = wrong[:1].upper() + wrong[1:]
            planted = text[: token.idx] + wrong + text[token.idx + len(token.text) :]
            yield "agreement", planted, (token.idx, token.idx + len(wrong)), text

        if (
            lower in ("a", "an")
            and token.dep_ == "det"
            and token.head.tag_ == "NN"
            and text[token.idx + len(token.text) : token.idx + len(token.text) + 1]
            == " "
        ):
            planted = text[: token.idx] + text[token.idx + len(token.text) + 1 :]
            yield "article", planted, (token.idx, token.idx + 1), text


def test_the_rule_layer_on_planted_errors(capsys):
    """How many of the errors it covers the rule layer finds, and whether it fixes them.

    Recall is printed and not asserted: it is a property of how narrow the rules were
    made on purpose, and a floor on it would be a reason to widen them. What is asserted
    is that a correction, when the layer makes one, puts back exactly the words that were
    there — a caught error with a wrong fix is a correction that is itself a mistake.
    """
    texts = native_texts()
    tally: dict[str, Counter] = {"agreement": Counter(), "article": Counter()}
    wrong_fixes: list[str] = []

    for where, text in texts:
        for family, planted, (start, end), original in _planted(grammar.parse(text)):
            found = rules.propose(grammar.parse(planted))
            here = [
                f
                for f in found
                if _overlaps(f.accepted.span_start, f.accepted.span_end, start, end)
            ]
            tally[family]["planted"] += 1
            tally[family]["elsewhere"] += len(found) - len(here)
            if not here:
                tally[family]["missed"] += 1
                continue
            accepted = here[0].accepted
            fixed = (
                planted[: accepted.span_start]
                + accepted.correction
                + planted[accepted.span_end :]
            )
            if fixed == original:
                tally[family]["caught"] += 1
            else:
                tally[family]["wrong_fix"] += 1
                wrong_fixes.append(
                    f"{where}: {accepted.original!r} -> {accepted.correction!r}"
                )

    words = sum(len(text.split()) for _, text in texts)
    lines = ["", f"planted errors in {len(texts)} native texts, {words} words"]
    for family, counts in tally.items():
        planted = counts["planted"]
        lines.append(
            f"  {family:<10} planted {planted:>4}  caught {counts['caught']:>3} "
            f"({counts['caught'] / planted:.1%})  wrong fix {counts['wrong_fix']}  "
            f"missed {counts['missed']:>4}  proposed elsewhere {counts['elsewhere']}"
            if planted
            else f"  {family:<10} nothing planted"
        )
    print("\n".join(lines))

    record(
        "rules",
        {
            "status": "measured",
            "texts": len(texts),
            "words": words,
            "planted": {family: dict(counts) for family, counts in tally.items()},
        },
    )

    assert all(
        counts["planted"] for counts in tally.values()
    ), "nothing was planted in one family, so this measured nothing about it"
    assert not wrong_fixes, f"a caught error was given the wrong fix: {wrong_fixes}"


def test_the_form_join_on_hand_labels(capsys):
    """How often a correction is linked to the forms a teacher would name, on three sets.

    A missing side is printed and not asserted: the parse of an unpunctuated transcript
    loses verbs, and a correction it cannot place is left out of every accuracy figure. A
    wrong form is asserted against, on every set, because it would count a mistake
    against a form the learner did not get wrong.
    """
    source, golden = golden_cases()
    sets = {"labelled": LABELLED, "held_out": HELD_OUT}
    if source is not None:
        sets["golden"] = golden

    results: dict[str, dict] = {}
    wrong: list[str] = []
    lines = [""]
    for name, cases in sets.items():
        counts = Counter({"exact": 0, "partial": 0, "wrong": 0})
        for case in cases:
            found = link_one(case)
            said = verdict(case, found)
            counts[said] += 1
            if said != "exact":
                lines.append(
                    f"    {said:<8}{case.quote!r} labelled ({case.form}, "
                    f"{case.corrected_form}), linked ({found.form}, {found.corrected_form})"
                )
            if said == "wrong":
                wrong.append(f"{name}: {case.quote!r}")
        results[name] = {"cases": len(cases), **counts}
        lines.append(
            f"  {name:<9} {len(cases):>3} cases  exact {counts['exact']:>3}  "
            f"partial {counts['partial']}  wrong {counts['wrong']}"
        )
    print("\n".join(lines))

    record(
        "forms",
        {"status": "measured", "golden_set": source, "sets": results},
    )
    assert not wrong, f"a correction was linked to a form it was not in: {wrong}"
