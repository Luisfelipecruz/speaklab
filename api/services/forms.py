"""Which verb form a correction was made in, and how correctly each form is used.

**The join.** An error is filed under a taxonomy category and a form is counted by the
parser, and the two meet only here. A correction is applied to the transcript, the
corrected text is parsed, and the verb phrases under the correction are compared before
and after. A phrase whose words the correction left as they were is not the one it
corrects; what remains on each side is the form that was said and the form that was
needed. `I never went` corrected to `I have never been` was said in the past simple and
needed the present perfect. `She going` said no finite form at all and needed the present
continuous. `I have went` needed the form it was said in, built differently.

**Both sides, because either alone misleads.** Counting only the form that was said files
`I never went to London` under the past simple, and a learner who never attempts the
present perfect never sees it fail — which is exactly the learner who most needs to.
Counting only the form that was needed loses the over-use: a present perfect said where
the past simple belonged is a present perfect that went wrong.

**Only corrections of a verb's form.** Tense, agreement and a missing auxiliary or copula.
`did a mistake` corrected to `made a mistake` changes a verb's words and not its form, and
filing it under the past simple would be the invented join this module exists to avoid.

**One phrase, one correction.** When two corrections change the same verb phrase — a rule
and the model disagreeing about the same words — the first links and the second does not,
so one phrase is never counted wrong twice.

**Accuracy is target-like use.** For each form: the times it was right, over the times it
was said plus the times it was needed and something else was said. A form used five times
correctly and needed twice more where the learner said something else is five of seven.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol

from services import grammar

# Categories whose correction is a correction of a verb's form.
FORM_CATEGORIES: frozenset[str] = frozenset(
    {"VERB_TENSE", "SUBJECT_VERB_AGREEMENT", "OMISSION"}
)


class Correction(Protocol):
    """Anything located in a transcript with a replacement for it."""

    category: str
    span_start: int | None
    span_end: int | None
    correction: str


@dataclass(frozen=True)
class Link:
    """The form a correction's words were said in, and the form its correction needs."""

    form: str | None = None
    corrected_form: str | None = None

    @property
    def linked(self) -> bool:
        return self.form is not None or self.corrected_form is not None


UNLINKED = Link()


def link(transcript: str, corrections: Sequence[Correction], doc=None) -> list[Link]:
    """One link per correction, in order. `doc` is the transcript's parse, if made."""
    if not any(_links(correction) for correction in corrections):
        return [UNLINKED for _ in corrections]

    said = grammar.verb_phrases(doc if doc is not None else grammar.parse(transcript))
    claimed: set[int] = set()
    links: list[Link] = []
    for correction in corrections:
        if not _links(correction):
            links.append(UNLINKED)
            continue
        start, end = correction.span_start, correction.span_end
        rewritten = transcript[:start] + correction.correction + transcript[end:]
        needed = grammar.verb_phrases(grammar.parse(rewritten))

        before = [phrase for phrase in said if phrase.overlaps(start, end)]
        after = [
            phrase
            for phrase in needed
            if phrase.overlaps(start, start + len(correction.correction))
        ]
        before, after = _changed(before, after)

        if any(phrase.head in claimed for phrase in before):
            links.append(UNLINKED)
            continue
        claimed.update(phrase.head for phrase in before)
        links.append(
            Link(
                form=before[0].form if before else None,
                corrected_form=after[0].form if after else None,
            )
        )
    return links


def _links(correction: Correction) -> bool:
    return (
        correction.category in FORM_CATEGORIES
        and correction.span_start is not None
        and correction.span_end is not None
    )


def _changed(
    before: list[grammar.Phrase], after: list[grammar.Phrase]
) -> tuple[list[grammar.Phrase], list[grammar.Phrase]]:
    """The phrases on each side the correction actually rewrote.

    A phrase whose words are the same on both sides is under the correction's span and
    untouched by it — `think` in `think that she go` → `think that she goes`.
    """
    unchanged = Counter(phrase.words for phrase in before) & Counter(
        phrase.words for phrase in after
    )
    return _without(before, unchanged), _without(after, unchanged)


def _without(phrases: list[grammar.Phrase], unchanged: Counter) -> list[grammar.Phrase]:
    left = Counter(unchanged)
    kept = []
    for phrase in phrases:
        if left[phrase.words]:
            left[phrase.words] -= 1
        else:
            kept.append(phrase)
    return kept


# ── Accuracy per form ───────────────────────────────────────────────────────


@dataclass
class FormTally:
    """How one form was used: said, said wrongly, and needed where it was not said."""

    used: int = 0
    wrong: int = 0
    missed: int = 0

    @property
    def right(self) -> int:
        return max(0, self.used - self.wrong)

    @property
    def contexts(self) -> int:
        """Every time this form was said or needed — the denominator."""
        return self.used + self.missed

    @property
    def accuracy(self) -> float | None:
        return round(self.right / self.contexts, 4) if self.contexts else None

    def as_dict(self) -> dict:
        return {
            "used": self.used,
            "right": self.right,
            "wrong": self.wrong,
            "missed": self.missed,
            "accuracy": self.accuracy,
        }


def tally(used: dict[str, int], links: Iterable[Link]) -> dict[str, FormTally]:
    """Accuracy per verb form, from the forms counted and the corrections linked.

    `used` is the repertoire's counts — the same numbers the breadth chart shows — and
    `links` are those of the corrections allowed to reach a rate. A form appears when it
    was used or needed.
    """
    tallies = {
        form: FormTally(used=int(used[form]))
        for form in grammar.VERB_FORMS
        if used.get(form)
    }
    for found in links:
        if found.form is not None:
            tallies.setdefault(found.form, FormTally()).wrong += 1
        if found.corrected_form is not None and found.corrected_form != found.form:
            tallies.setdefault(found.corrected_form, FormTally()).missed += 1
    return {form: tallies[form] for form in grammar.VERB_FORMS if form in tallies}
