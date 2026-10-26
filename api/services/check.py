"""English the person wrote, checked: spelling by a dictionary, grammar as a conversation's.

Three layers, each with its own source, and every fix says which:

- **Spelling**, from the dictionary in `services/spelling.py`, at confidence 1.0, under
  `SPELLING`: a category only written text can have, since speech is never spelled.
- **The rule layer**, agreement and missing articles from the parse.
- **The language model's proposals**, inside the closed taxonomy and located in the text,
  through the same detector and gate a conversation turn goes through.

**Grammar is checked on the text with its spelling already fixed.** A model shown
"recieved" would file it under some category of its own; shown "received", it looks at
the grammar. Its spans are then mapped back onto what the person wrote, so every fix
underlines the person's own words.

**Corrected** is the person's text with every fix applied: spelling, then grammar, the
smallest edits, nothing reworded. Where two fixes overlap the rule's is kept, then the
model's, by position. With the model down, it is the dictionary's and the rules' fixes
only, and `detail` says so.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from services import errors as error_detector
from services import grammar, rules, spelling
from services.llm import LlmProvider

SPELLING = "SPELLING"

log = logging.getLogger("speaklab.check")


@dataclass(frozen=True)
class Fix:
    """One mistake in the person's text and its correction, located in that text."""

    category: str
    subcategory: str | None
    span_start: int
    span_end: int
    original: str
    correction: str
    explanation: str | None
    detector: str
    confidence: float


@dataclass
class Checked:
    """Everything one check produced."""

    text: str
    corrected: str
    fixes: list[Fix] = field(default_factory=list)
    forms: dict[str, int] = field(default_factory=dict)
    model: str | None = None
    detail: str | None = None
    rejects: list[dict] = field(default_factory=list)


def _apply(text: str, edits: list[tuple[int, int, str]]) -> str:
    """`text` with each (start, end, replacement) applied; the edits must not overlap."""
    out, cursor = [], 0
    for start, end, replacement in sorted(edits):
        out.append(text[cursor:start])
        out.append(replacement)
        cursor = end
    out.append(text[cursor:])
    return "".join(out)


class _Offsets:
    """Positions in the spelling-corrected text, mapped back to the person's own."""

    def __init__(self, edits: list[tuple[int, int, str]]) -> None:
        # (start in theirs, end in theirs, start in ours, end in ours), in order.
        self._regions = []
        shift = 0
        for start, end, replacement in sorted(edits):
            ours = start + shift
            self._regions.append((start, end, ours, ours + len(replacement)))
            shift += len(replacement) - (end - start)

    def back(self, position: int, end: bool = False) -> int:
        shift = 0
        for theirs_start, theirs_end, ours_start, ours_end in self._regions:
            if position < ours_start or (end and position == ours_start):
                break
            if position < ours_end or (end and position == ours_end):
                return theirs_end if end else theirs_start
            shift = theirs_end - ours_end
        return position + shift


def _overlaps(start: int, end: int, taken: list[tuple[int, int]]) -> bool:
    return any(
        start < other_end and other_start < end for other_start, other_end in taken
    )


def _forms(doc) -> dict[str, int]:
    try:
        return grammar.count(doc) if doc is not None else {}
    except (
        Exception
    ):  # noqa: BLE001 — forms are reported beside the fixes, not needed by them
        log.exception("counting the forms failed on a check")
        return {}


async def check(
    provider: LlmProvider, text: str, known: list[str] | None = None
) -> Checked:
    """Spelling, the rules and the model on `text`. Never raises: a model that is down
    leaves the dictionary's and the rules' fixes, and a `detail` that says so."""
    text = text.strip()
    misspelled = spelling.check(text, known or [])
    spelled = [(m.span_start, m.span_end, m.correction) for m in misspelled]
    respelled = _apply(text, spelled)
    offsets = _Offsets(spelled)

    doc, ruled, broken = None, [], None
    try:
        doc = await asyncio.to_thread(grammar.parse, respelled)
        ruled = rules.propose(doc) if doc is not None else []
    except Exception as exc:  # noqa: BLE001 — the spelling and the model still stand
        log.exception("the parse or the rules failed on a check")
        broken = f"The grammar rules could not run ({type(exc).__name__})."
    detection = await error_detector.detect(provider, respelled, None, ruled)

    fixes = [
        Fix(
            category=SPELLING,
            subcategory="misspelling",
            span_start=m.span_start,
            span_end=m.span_end,
            original=m.original,
            correction=m.correction,
            explanation=f"Spelled {m.correction}.",
            detector="dictionary",
            confidence=spelling.CONFIDENCE,
        )
        for m in misspelled
    ]

    # Grammar, on the respelled text: rules before the model, then by position, so an
    # overlap keeps the rule's fix.
    chosen: list[error_detector.DetectedError] = []
    taken: list[tuple[int, int]] = []
    order = sorted(
        detection.errors,
        key=lambda found: (found.detector != "rule", found.accepted.span_start),
    )
    for found in order:
        span = (found.accepted.span_start, found.accepted.span_end)
        if _overlaps(*span, taken):
            continue
        chosen.append(found)
        taken.append(span)

    for found in chosen:
        accepted = found.accepted
        start = offsets.back(accepted.span_start)
        end = offsets.back(accepted.span_end, end=True)
        fixes.append(
            Fix(
                category=accepted.category,
                subcategory=accepted.subcategory,
                span_start=start,
                span_end=end,
                original=text[start:end],
                correction=accepted.correction,
                explanation=accepted.explanation,
                detector=found.detector,
                confidence=accepted.confidence,
            )
        )

    corrected = _apply(
        respelled,
        [
            (f.accepted.span_start, f.accepted.span_end, f.accepted.correction)
            for f in chosen
        ],
    )
    detail = broken
    if detection.status not in ("ok", "skipped"):
        detail = " ".join(
            part
            for part in (
                "The language model did not answer, so only spelling and the grammar "
                "rules were checked.",
                broken,
            )
            if part
        )
    return Checked(
        text=text,
        corrected=corrected,
        fixes=sorted(fixes, key=lambda fix: (fix.span_start, fix.span_end)),
        forms=_forms(doc),
        model=detection.model,
        detail=detail,
        rejects=detection.not_stored(),
    )
