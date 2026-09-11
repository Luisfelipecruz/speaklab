"""Word error rate, and the normalisation that decides what it measures.

Forty lines rather than a dependency, for one reason: **the normalisation is the part
that moves the number, and it has to be readable.** A WER of 3% and a WER of 11% on the
same transcripts is entirely a question of whether "didn't" matches "did not" and
whether "20" matches "twenty". Importing that decision from a library makes it invisible
in review, and every published WER in this project is a claim somebody should be able to
check.

What `normalise` does, and each of these is a decision that could have gone the other
way:

- **Case-folds.** LibriSpeech references are upper-case; Whisper's output is sentence
  case. Counting that as an error would measure the corpus's formatting.
- **Drops punctuation, keeping apostrophes inside words.** The references are
  unpunctuated, so scoring Whisper's commas would penalise it for being more useful.
  `don't` stays one token because `dont` and `do not` are different words.
- **Leaves numbers alone.** `20` against `TWENTY` counts as a substitution, and that is
  the honest reading: this system feeds transcripts to a grammar analyser, and a
  numeral is genuinely not the word the speaker said. Silently mapping them would hide
  a real difference between models.
"""

import re
from dataclasses import dataclass

# Anything that is not a letter, a digit, whitespace or an apostrophe. Applied after
# case-folding, so only the lower-case ranges are needed.
_PUNCTUATION = re.compile(r"[^a-z0-9'\s]")

# A leading or trailing apostrophe is quoting, not contraction: 'twas keeps its mark,
# but the closing one in 'hello' does not survive as part of the word.
_EDGE_APOSTROPHE = re.compile(r"(?<!\w)'|'(?!\w)")


def normalise(text: str) -> list[str]:
    """Text to a comparable word list. See the module docstring for what is dropped."""
    lowered = text.lower()
    stripped = _PUNCTUATION.sub(" ", lowered)
    return _EDGE_APOSTROPHE.sub(" ", stripped).split()


@dataclass(frozen=True)
class WerResult:
    """The counts, not just the rate.

    The rate alone cannot distinguish a model that drops words from one that invents
    them, and those are very different problems in a system that scores fluency from
    word timings: a deletion loses a real pause, an insertion invents a word the
    speaker never said and gives it a duration.
    """

    substitutions: int
    deletions: int
    insertions: int
    reference_words: int

    @property
    def errors(self) -> int:
        return self.substitutions + self.deletions + self.insertions

    @property
    def rate(self) -> float:
        """Errors per reference word. Can exceed 1.0 — insertions are unbounded."""
        if self.reference_words == 0:
            return 0.0 if self.errors == 0 else 1.0
        return self.errors / self.reference_words


@dataclass(frozen=True)
class Step:
    """One step of an alignment: a reference word, a heard word, or one of each.

    Indices into the two word lists. Both set is a match or a substitution — the words
    say which; only `ref` is a word not heard; only `hyp` is a word heard that is not in
    the reference.
    """

    ref: int | None
    hyp: int | None


def wer(reference: str, hypothesis: str) -> WerResult:
    """Levenshtein alignment over words, with the three edit types counted separately."""
    ref = normalise(reference)
    hyp = normalise(hypothesis)

    substitutions = deletions = insertions = 0
    for step in align(ref, hyp):
        if step.hyp is None:
            deletions += 1
        elif step.ref is None:
            insertions += 1
        elif ref[step.ref] != hyp[step.hyp]:
            substitutions += 1

    return WerResult(
        substitutions=substitutions,
        deletions=deletions,
        insertions=insertions,
        reference_words=len(ref),
    )


def align(ref: list[str], hyp: list[str]) -> list[Step]:
    """Which heard word stands for which reference word, in order.

    The standard dynamic program, with the back-pointer walk that recovers *which* edits
    were used rather than only how many. Two rows of the matrix at a time would be
    enough for the total, but not for the breakdown or for the pairing, and those are
    why this function is not a one-liner. Where two alignments cost the same, the walk
    prefers a match, then a substitution, then a word not heard.
    """
    rows, cols = len(ref) + 1, len(hyp) + 1
    cost = [[0] * cols for _ in range(rows)]
    for i in range(rows):
        cost[i][0] = i
    for j in range(cols):
        cost[0][j] = j

    for i in range(1, rows):
        for j in range(1, cols):
            if ref[i - 1] == hyp[j - 1]:
                cost[i][j] = cost[i - 1][j - 1]
            else:
                cost[i][j] = 1 + min(
                    cost[i - 1][j - 1],  # substitution
                    cost[i - 1][j],  # deletion
                    cost[i][j - 1],  # insertion
                )

    steps: list[Step] = []
    i, j = len(ref), len(hyp)
    while i > 0 or j > 0:
        if (
            i > 0
            and j > 0
            and ref[i - 1] == hyp[j - 1]
            and cost[i][j] == cost[i - 1][j - 1]
        ):
            steps.append(Step(i - 1, j - 1))
            i, j = i - 1, j - 1
        elif i > 0 and j > 0 and cost[i][j] == cost[i - 1][j - 1] + 1:
            steps.append(Step(i - 1, j - 1))
            i, j = i - 1, j - 1
        elif i > 0 and cost[i][j] == cost[i - 1][j] + 1:
            steps.append(Step(i - 1, None))
            i -= 1
        else:
            steps.append(Step(None, j - 1))
            j -= 1

    steps.reverse()
    return steps
