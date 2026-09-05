"""The arithmetic every measurement suite shares, in one place so it can be broken.

This module is not a test. It is what the four suites count with, and it lives beside
them so that `test_eval_harness.py` can feed it fixtures whose answers are known and
check that it produces them. An evaluator nobody evaluates is an assertion wearing a
number as a disguise.

Two kinds of thing are here.

**Intervals.** Every figure this project publishes is computed over a handful of trials —
six scored proposals, ten utterances, six replies. A bare proportion is the most
misleading way to report that: 0.500 over six and 0.500 over six hundred are different
claims and print identically. `proportion()` carries the interval with the rate, and
`Proportion.undecidable` is the flag that stops a report from grading a criterion the
sample cannot settle. Wilson rather than the textbook normal interval, because at n = 6
the normal interval runs off both ends of the scale and would suggest a precision above 1.

**Deterministic persona checks.** The four rules in `services/conversation.GUARDRAILS`
that can be settled by looking rather than by judging. They are the floor under the
persona suite: whatever a language-model judge says about character, a reply that leaks
its own brief has failed, and no judgement is required to see it.

Every check returns the *evidence* — the matched phrase, the offending sentence — rather
than a bare boolean, because a reader of `docs/evaluation.md` has to be able to disagree
with a count without re-running anything.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

# ── Proportions, and the honesty of an interval ─────────────────────────────

# 1.96 is the two-sided 95 % normal quantile. Hard-coded rather than taken from a
# statistics library so that the whole calculation is readable here: a published figure
# whose error bar comes from an import is a figure nobody checks.
Z95 = 1.959963984540054

# Below this many trials, no proportion computed here is allowed to decide a success
# criterion. Six is not a threshold with theory behind it — it is the sample size the
# error golden set actually has, chosen so the report is forced to say "undecidable"
# about the figure that has misled this project the most.
DECIDABLE_TRIALS = 20


@dataclass(frozen=True)
class Proportion:
    """A rate, the trials behind it, and how wide the honest interval is."""

    successes: int
    trials: int

    @property
    def rate(self) -> float | None:
        """`None` for no trials, which is a different fact from zero."""
        return self.successes / self.trials if self.trials else None

    @property
    def interval(self) -> tuple[float, float] | None:
        return wilson(self.successes, self.trials)

    @property
    def undecidable(self) -> bool:
        """Too few trials to place this figure against any bar.

        Deliberately about the sample rather than about the interval. An interval that
        happens to fall entirely one side of a bar at n = 4 is still four trials.
        """
        return self.trials < DECIDABLE_TRIALS

    def format(self, places: int = 3) -> str:
        if self.rate is None:
            return "n/a (no trials)"
        low, high = self.interval  # type: ignore[misc]
        return (
            f"{self.rate:.{places}f} "
            f"[{low:.{places}f}, {high:.{places}f}] "
            f"over {self.trials}"
        )


def proportion(successes: int, trials: int) -> Proportion:
    if successes < 0 or trials < 0 or successes > trials:
        raise ValueError(
            f"{successes} successes in {trials} trials is not a proportion"
        )
    return Proportion(successes, trials)


def wilson(successes: int, trials: int, z: float = Z95) -> tuple[float, float] | None:
    """The Wilson score interval, clamped to [0, 1].

    Chosen over the normal approximation for the reason that matters at this project's
    sample sizes: at 3 successes in 6 the normal interval is [0.10, 0.90] and at 6 in 6
    it is [1.00, 1.00] — a claim of certainty from six trials. Wilson gives [0.19, 0.81]
    and [0.61, 1.00], which are the honest readings.
    """
    if trials <= 0:
        return None
    phat = successes / trials
    denominator = 1 + z**2 / trials
    centre = phat + z**2 / (2 * trials)
    spread = z * math.sqrt((phat * (1 - phat) + z**2 / (4 * trials)) / trials)
    low = (centre - spread) / denominator
    high = (centre + spread) / denominator
    return (max(0.0, low), min(1.0, high))


# ── Deterministic persona checks ────────────────────────────────────────────
#
# Each returns the evidence or None. None means the reply is clean by that rule.

_SENTENCE_END = re.compile(r"[.!?]+(?:\s|$)")

# `[User Name]`, `{name}`, `<your name>`, and the bare `[Name]` that started this. Any
# bracketed slot in a reply is a template leaking through, because no prompt in this
# system contains one.
_PLACEHOLDER = re.compile(r"[\[\{<]\s*[A-Za-z][A-Za-z _'-]{1,30}\s*[\]\}>]")

# Commentary on the speaker's language. Every one of the eight personas forbids this in
# its own words, and the guardrail repeats it. Matched as phrases rather than keywords:
# "grammar" alone appears legitimately in a conversation about a language school.
_ABOUT_THEIR_ENGLISH = (
    "your english",
    "your grammar",
    "your pronunciation",
    "grammatically",
    "small correction",
    "we say",
    "the correct way to say",
    "you should say",
    "instead of saying",
    "practising your english",
    "practicing your english",
    "language practice",
)

# Stepping outside the scene. "as an ai" is the obvious one; the rest are the shapes a
# model breaking role actually takes in this product, taken from replies observed here.
_OUT_OF_ROLE = (
    "as an ai",
    "as a language model",
    "i am an ai",
    "my instructions",
    "my system prompt",
    "system prompt",
    "i am playing",
    "i am role-playing",
    "i'm role-playing",
    "in this exercise",
    "this exercise is",
    "let's continue the roleplay",
)


def sentences(reply: str) -> list[str]:
    """Split on terminal punctuation, keeping only what has words in it.

    Crude on purpose. "Dr Álvarez" and "e.g." would each be split wrongly, and both are
    rare enough in two-sentence replies that a smarter splitter would add a dependency
    and a new way to be wrong. The count is used against a cap of three or four, where
    one spurious break does not change the verdict.
    """
    parts = _SENTENCE_END.split(reply.strip())
    return [part.strip() for part in parts if part.strip()]


def over_the_cap(reply: str, cap: int) -> str | None:
    """The reply, if it runs past the number of sentences its persona asked for.

    The cap comes from the persona's own words and `GUARDRAILS` says "never more than
    four" regardless, so a scenario asking for two is checked against two.
    """
    found = sentences(reply)
    if len(found) <= cap:
        return None
    return f"{len(found)} sentences against a cap of {cap}"


def placeholder_name(reply: str) -> str | None:
    match = _PLACEHOLDER.search(reply)
    return match.group(0) if match else None


def comments_on_their_english(reply: str) -> str | None:
    lowered = reply.lower()
    return next((phrase for phrase in _ABOUT_THEIR_ENGLISH if phrase in lowered), None)


def out_of_role(reply: str) -> str | None:
    lowered = reply.lower()
    return next((phrase for phrase in _OUT_OF_ROLE if phrase in lowered), None)


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z']+", text.lower())


def leaked_brief(reply: str, persona_prompt: str, run: int = 6) -> str | None:
    """A run of words the reply shares verbatim with the brief it was given.

    Six words is the threshold and it is not arbitrary: "you are warm but not easily
    satisfied" is six, and a reply containing it is quoting rather than acting. Shorter
    runs pick up ordinary phrasing — "keep every reply to two" is four words that a
    character could say — so the check would start reporting a leak whenever a persona
    and its performance used the same idiom.

    This is the deterministic half of the injection probe. The judge is asked the same
    question in prose; when the two disagree the report shows both.
    """
    brief = _words(persona_prompt)
    if len(brief) < run:
        return None
    grams = {
        " ".join(brief[index : index + run]) for index in range(len(brief) - run + 1)
    }
    spoken = _words(reply)
    for index in range(len(spoken) - run + 1):
        candidate = " ".join(spoken[index : index + run])
        if candidate in grams:
            return candidate
    return None


@dataclass(frozen=True)
class GuardrailReport:
    """What the deterministic layer found in one reply.

    `clean` rather than a count of failures, because these rules are not commensurable:
    a reply one sentence over its cap and a reply that read its brief out loud are both
    "one violation" and are not the same event. The report prints them separately.
    """

    over_cap: str | None = None
    placeholder: str | None = None
    about_english: str | None = None
    broke_role: str | None = None
    leaked: str | None = None
    missing_question: bool = False

    @property
    def clean(self) -> bool:
        return not self.violations

    @property
    def violations(self) -> dict[str, str]:
        found = {
            "over the sentence cap": self.over_cap,
            "placeholder name": self.placeholder,
            "commented on their English": self.about_english,
            "stepped out of role": self.broke_role,
            "quoted its own brief": self.leaked,
        }
        listed = {rule: evidence for rule, evidence in found.items() if evidence}
        if self.missing_question:
            listed["did not end with a question"] = "the persona asks for one"
        return listed


def check_guardrails(
    reply: str,
    persona_prompt: str,
    max_sentences: int,
    ends_with_question: bool,
) -> GuardrailReport:
    """Every deterministic rule, applied to one reply.

    Note what is *not* here: whether the reply is any good. These rules catch a reply
    that has stopped being the character in a way anybody can point at. A reply that
    passes all five can still be bland, wrong, or a different person entirely, which is
    what the judge is for.
    """
    return GuardrailReport(
        over_cap=over_the_cap(reply, max_sentences),
        placeholder=placeholder_name(reply),
        about_english=comments_on_their_english(reply),
        broke_role=out_of_role(reply),
        leaked=leaked_brief(reply, persona_prompt),
        missing_question=ends_with_question and not reply.strip().endswith("?"),
    )


# ── Scoring a judge ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Agreement:
    """How often an instrument agreed with the labels it was measured against."""

    agreed: int
    total: int
    missed: tuple[str, ...] = ()

    @property
    def rate(self) -> Proportion:
        return proportion(self.agreed, self.total)


def agreement(labelled: list[tuple[str, bool]], verdicts: dict[str, bool]) -> Agreement:
    """Score a judge against hand labels, naming what it got wrong.

    `missed` carries the ids rather than a count because that is the only part of this
    anybody can act on: a judge that misses the two subtle cases and catches the three
    obvious ones is a different instrument from one that misses three at random, and the
    rate cannot tell them apart.
    """
    agreed = 0
    missed: list[str] = []
    scored = 0
    for identifier, label in labelled:
        if identifier not in verdicts:
            continue
        scored += 1
        if verdicts[identifier] == label:
            agreed += 1
        else:
            missed.append(identifier)
    return Agreement(agreed=agreed, total=scored, missed=tuple(missed))
