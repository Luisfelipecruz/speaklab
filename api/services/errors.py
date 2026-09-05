"""Error detection: what a language model proposes, and what survives the gate.

**The model proposes; it does not decide.** Everything it returns passes through
`services/taxonomy.py`, which checks the label against a closed vocabulary and finds the
quoted text in the transcript itself. What comes out of here is a list of errors that are
in the vocabulary and point at words the speaker actually produced, plus a list of what
was refused and why. The refusals are the interesting half: their rate is the measurement
that says whether the model behind this is strong enough for the job, and it cannot be
recovered later from a table of the proposals that happened to pass.

**Two things this deliberately does not do.**

It does not correct spelling, capitalisation or punctuation. The input is speech
recognition output — the speaker never produced a capital letter — so a "correction"
there is a correction of the recogniser, delivered to somebody who cannot act on it.

It does not decide whether a word was heard correctly. It marks the errors that sit on
words the recogniser was unsure of, and leaves them in. A mishearing labelled as a grammar
error is a correction the speaker cannot act on and a trend that moves for a reason that
is not them; a mishearing silently deleted is a transcript the learner cannot make sense
of. So they are kept, marked, and kept out of the trends.

**The gate is per word.** The turn-level confidence is the mean of the per-word scores, so
one badly heard word inside a confident turn is averaged away and no turn-level threshold
can reach it. That is not hypothetical: a stored turn scored 0.899 while containing
"department" where the speaker said "the apartment", at a word probability of 0.41.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field

from config import (
    ANALYSIS_MAX_TOKENS,
    ANALYSIS_TEMPERATURE,
    ASR_CONFIDENCE_FLOOR,
    ERROR_MAX_SPAN_WORDS,
)
from services.llm import ChatMessage, LlmError, LlmProvider
from services.taxonomy import (
    CATEGORY_GLOSS,
    TAXONOMY,
    Accepted,
    Rejected,
    validate,
)

log = logging.getLogger("speaklab.errors")


@dataclass
class DetectedError:
    """One accepted proposal, with what the confidence gate says about its location."""

    accepted: Accepted

    # The recogniser was unsure of at least one word under this span. The error is stored
    # and shown; it must not reach an accuracy trend.
    asr_suspect: bool


@dataclass
class Detection:
    """Everything one turn's labelling produced, including what it refused."""

    errors: list[DetectedError] = field(default_factory=list)
    rejected: list[Rejected] = field(default_factory=list)
    model: str | None = None
    status: str = "ok"
    detail: str | None = None

    @property
    def proposed(self) -> int:
        return len(self.errors) + len(self.rejected)

    @property
    def rejection_rate(self) -> float | None:
        return round(len(self.rejected) / self.proposed, 4) if self.proposed else None


def _taxonomy_block() -> str:
    """The vocabulary as the model sees it: each category glossed, then its subcategories."""
    lines = []
    for category, subcategories in sorted(TAXONOMY.items()):
        lines.append(f"{category} — {CATEGORY_GLOSS[category]}")
        lines.append(f"    {', '.join(sorted(subcategories))}")
    return "\n".join(lines)


INSTRUCTION = f"""
You are marking one utterance from a spoken English lesson. The learner's first language
is Spanish. The text is speech-recognition output, so it has no reliable capitalisation
and no reliable punctuation.

Answer strictly as a JSON object: {{"errors": [ ... ]}}. Each entry has:

  "category"     one of the categories below, exactly as written
  "subcategory"  one of that category's subcategories, exactly as written
  "original"     the exact words from the utterance that are wrong, copied character for
                 character. Three to six words: enough to appear only once, and no more
                 than {ERROR_MAX_SPAN_WORDS}. Never a whole sentence.
  "correction"   those words, corrected
  "explanation"  one short sentence the learner can act on
  "confidence"   a number from 0 to 1

Categories and their subcategories:
{_taxonomy_block()}

Rules:
- Use only the categories and subcategories above. Do not invent one. If a mistake does
  not fit any of them, leave it out.
- Choose the category by what is wrong with the words, not by where they sit. WORD_ORDER
  is only for words that are all correct and in the wrong sequence.
- Quote the smallest phrase that contains the mistake. If your quote is longer than
  {ERROR_MAX_SPAN_WORDS} words it will be discarded.
- "original" must be copied from the utterance exactly. Do not rephrase it and do not
  quote words that are not there.
- Never correct capitalisation, punctuation or spelling, and never quote a comma or a
  question mark as the mistake. They come from the recogniser and the speaker did not
  produce them.
- The correction must change a word. If your correction differs from the original only in
  punctuation or capitalisation, leave that entry out.
- Some words may be misheard. If a phrase is not English at all, leave it alone rather
  than inventing a grammar rule for it.
- Mark every error you find, including several in one sentence.
- If the utterance has no errors, answer {{"errors": []}}. That is a normal answer.

Output the JSON object and nothing else.
""".strip()


# Invented sentences, not corpus turns. The golden set is what precision is measured
# against, so an example drawn from it would be marking the model's own homework — the
# score would rise and mean nothing. These carry the shape of the answer and the habit of
# finding more than one error in a sentence, which is what a 4B model needs shown rather
# than told.
EXAMPLES: tuple[tuple[str, dict], ...] = (
    (
        "yesterday I go to the office and I speak with my manager about the project",
        {
            "errors": [
                {
                    "category": "VERB_TENSE",
                    "subcategory": "missing_past_marker",
                    "original": "I go to the office",
                    "correction": "I went to the office",
                    "explanation": "Yesterday needs the past simple.",
                    "confidence": 0.95,
                },
                {
                    "category": "VERB_TENSE",
                    "subcategory": "missing_past_marker",
                    "original": "I speak with my manager",
                    "correction": "I spoke with my manager",
                    "explanation": "The second verb is in the past too.",
                    "confidence": 0.9,
                },
            ]
        },
    ),
    (
        "she work in a bank and is very interesting job for she",
        {
            "errors": [
                {
                    "category": "SUBJECT_VERB_AGREEMENT",
                    "subcategory": "third_person_s",
                    "original": "she work in a bank",
                    "correction": "she works in a bank",
                    "explanation": "Third person singular takes -s.",
                    "confidence": 0.95,
                },
                {
                    "category": "ARTICLE",
                    "subcategory": "missing_indefinite",
                    "original": "is very interesting job",
                    "correction": "is a very interesting job",
                    "explanation": "A singular countable noun needs an article.",
                    "confidence": 0.9,
                },
                {
                    "category": "PRONOUN",
                    "subcategory": "case",
                    "original": "job for she",
                    "correction": "job for her",
                    "explanation": "After a preposition, use the object pronoun.",
                    "confidence": 0.9,
                },
            ]
        },
    ),
    (
        "I finished the report and sent it to the client this morning",
        {"errors": []},
    ),
)


def _messages(transcript: str) -> list[ChatMessage]:
    """The instruction, the worked examples, then the utterance being marked."""
    messages = [ChatMessage(role="system", content=INSTRUCTION)]
    for utterance, answer in EXAMPLES:
        messages.append(ChatMessage(role="user", content=f"Utterance:\n{utterance}"))
        messages.append(
            ChatMessage(role="assistant", content=json.dumps(answer, indent=2))
        )
    messages.append(ChatMessage(role="user", content=f"Utterance:\n{transcript}"))
    return messages


async def detect(
    provider: LlmProvider, transcript: str, words: list[dict] | None
) -> Detection:
    """Label one turn. Never raises: a failure is a status, not an exception.

    Analysis runs behind the conversation and nobody is waiting for it, so a model that
    is down must leave a turn marked as unanalysed and retryable rather than taking the
    job down with it.
    """
    text = (transcript or "").strip()
    if not text:
        return Detection(status="skipped", detail="the turn has no transcript")

    try:
        completion = await provider.complete(
            _messages(text),
            max_tokens=ANALYSIS_MAX_TOKENS,
            # Zero, because this is a measurement. The same utterance has to produce the
            # same errors on a re-run, or a backfill would rewrite a learner's history
            # every time it was run.
            temperature=ANALYSIS_TEMPERATURE,
        )
    except LlmError as exc:
        return Detection(status="unavailable", detail=f"{type(exc).__name__}: {exc}")

    proposals = _proposals(completion.text)
    if proposals is None:
        return Detection(
            status="unparseable",
            model=completion.model,
            detail=completion.text[:300],
        )

    suspect = low_confidence_spans(text, words)
    detection = Detection(model=completion.model)
    taken: set[tuple[int, int]] = set()

    for raw in proposals:
        outcome = validate(raw, text, taken)
        if isinstance(outcome, Rejected):
            detection.rejected.append(outcome)
            continue
        detection.errors.append(
            DetectedError(
                accepted=outcome,
                asr_suspect=_overlaps(outcome, suspect),
            )
        )

    if detection.rejected:
        log.info(
            "error labelling on %d chars: %d accepted, %d rejected (%s)",
            len(text),
            len(detection.errors),
            len(detection.rejected),
            ", ".join(sorted({r.reason for r in detection.rejected})),
        )
    return detection


def low_confidence_spans(
    transcript: str, words: list[dict] | None, floor: float | None = None
) -> list[tuple[int, int]]:
    """Character ranges covering the words the recogniser was least sure of.

    Words are matched forward through the transcript rather than assumed to join with
    single spaces. They do join that way today — every stored turn reproduces its
    transcript exactly when its words are joined — but that is a property of one
    recogniser's output, and a change to it should cost a missed marker rather than a set
    of spans silently off by one word.
    """
    cutoff = math.log(ASR_CONFIDENCE_FLOOR if floor is None else floor)
    spans: list[tuple[int, int]] = []
    cursor = 0

    for word in words or []:
        if not isinstance(word, dict):
            continue
        token = str(word.get("w", ""))
        if not token:
            continue
        found = transcript.find(token, cursor)
        if found == -1:
            # Out of step with the transcript. Skip it rather than guessing: a span in
            # the wrong place would mark a correct error as doubtful.
            continue
        cursor = found + len(token)
        logprob = word.get("logprob")
        if isinstance(logprob, (int, float)) and float(logprob) < cutoff:
            spans.append((found, cursor))

    return spans


def _overlaps(error: Accepted, spans: list[tuple[int, int]]) -> bool:
    return any(
        error.span_start < end and start < error.span_end for start, end in spans
    )


# A small model wraps JSON in a fence more often than not, and an analysis that failed
# because of three backticks would be reporting on the fence rather than on the model.
def _proposals(text: str) -> list | None:
    """The `errors` array out of a model reply, or None if there is no usable object.

    A bare array is accepted as well as the object that was asked for. It is the one
    deviation worth tolerating: the content is exactly right and the wrapper is missing,
    and counting that as a whole unparseable turn would throw away good labelling to
    enforce a brace.
    """
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = candidate.strip("`")
        if candidate.lower().startswith("json"):
            candidate = candidate[4:]
        candidate = candidate.strip()

    # Whichever bracket opens first is the outer one. Trying the object first would find
    # the brace of the first element inside a bare array and read one error as the whole
    # answer.
    openers = [
        (candidate.find(opener), opener, closer)
        for opener, closer in (("{", "}"), ("[", "]"))
        if candidate.find(opener) != -1
    ]
    for _, opener, closer in sorted(openers):
        start, end = candidate.find(opener), candidate.rfind(closer)
        if start == -1 or end <= start:
            continue
        try:
            parsed = json.loads(candidate[start : end + 1])
        except ValueError:
            continue
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            errors = parsed.get("errors")
            return errors if isinstance(errors, list) else []
    return None
