"""What a language model says about a spoken answer, and what the code checks of it.

One call after the answer is counted: the point to say first, the points made without a
reason or an example, and the speaker's own answer said in fewer sentences. It sits beside
the counts and never replaces them — nothing here is drawn over time, and no count on the
page comes from it.

**The shorter version is checked, not trusted.** A model asked to tighten an answer will
improve it, and improving it means adding: a figure the speaker never gave, a product
they never named, a cause they did not offer. Shown as "your answer, shorter", that would
put words in the speaker's mouth. So every content word in the rewrite is looked for in
the answer and the prompt, and a rewrite that brings in more than
`ANSWER_REWRITE_MAX_INVENTED` new ones is withheld. The refusal is recorded with the words
that caused it, so how often the model invents is counted rather than hidden.

**It did not hear the answer.** It reads a transcript, so it is told not to comment on
how anything sounded; a note that does anyway — about pronunciation, accent or tone — is
dropped and counted, because a claim about sound from something that never processed the
sound is exactly what this product does not make.

**It never raises.** A model that is down, slow or answers in prose leaves the answer
stored and counted, with a status that says what happened, as the session report's
narrative does.
"""

from __future__ import annotations

import asyncio
import re

from config import (
    ANALYSIS_TEMPERATURE,
    ANSWER_FEEDBACK_MAX_TOKENS,
    ANSWER_FEEDBACK_TIMEOUT_S,
    ANSWER_REWRITE_MAX_INVENTED,
)
from services.conversation import _json_object
from services.grammar import parse
from services.llm import ChatMessage, LlmError, LlmProvider
from services.structure import PHRASES, sentences, words_of

FEEDBACK_CAVEAT = (
    "Written by a language model reading the transcript. It did not hear you, so it says "
    "nothing about how you sounded, and nothing it writes is counted or drawn over time. "
    "Its shorter version is checked for words you never said, and not shown if it added "
    f"more than {ANSWER_REWRITE_MAX_INVENTED}."
)

INSTRUCTION = """
You are helping someone practise explaining an idea out loud in English at work. You get
the question they were answering and a transcript of their spoken answer, written by
speech recognition. Answer strictly as JSON with these keys:

  "lead"     one sentence: the main point of their answer, which they should say first
  "gaps"     a list of at most two points they made without giving a reason or an
             example, each in their own words; an empty list if every point has one
  "rewrite"  their own answer said again in fewer sentences, built only from their own
             words: cut words, drop what they repeated, and join their sentences with
             "and", "so", "because" or "but". Do not replace their words with other
             words, even better ones, and add nothing they did not say — no new facts,
             figures, names, examples or reasons

Do not judge whether their answer is right. Do not comment on grammar, vocabulary,
pronunciation, accent or how they sounded: you are reading text, and you did not hear
them. Output the JSON object and nothing else.
""".strip()

# Parts of speech that carry content. A rewrite joining two sentences may add "and" or
# "which"; a new noun, verb, adjective or number is something the speaker did not say.
_CONTENT = frozenset({"NOUN", "PROPN", "VERB", "ADJ", "NUM"})

# Words that say how an answer is built rather than what it says: a rewrite that names
# "the main reason" or "one example" has added structure, not content.
_STRUCTURE_WORDS = frozenset(
    {
        "reason",
        "example",
        "point",
        "thing",
        "way",
        "result",
        "summary",
        "main",
        "key",
        "first",
        "second",
        "third",
        "last",
        "final",
        "short",
    }
    | {word for phrases in PHRASES.values() for p in phrases for word in p.split()}
)

# A note about the sound of the answer, which a transcript cannot support.
_HEARD = re.compile(
    r"\b(pronunc\w*|accent\w*|intonation|tone of voice|sounded|sound(s|ing)? (confident"
    r"|nervous|clear|unsure)|your voice|stress(ed)? (the|on)|fluen\w*)\b",
    re.IGNORECASE,
)


def _vocabulary(text: str) -> set[str]:
    doc = parse(text)
    if doc is None:
        return set()
    known = set()
    for token in doc:
        if token.is_punct or token.is_space:
            continue
        known.add(token.lower_)
        known.add(token.lemma_.lower())
    return known


def invented(answer: str, context: str, rewrite: str) -> list[str]:
    """Content words in `rewrite` that are in neither `answer` nor `context`, once each.

    Compared by word and by lemma, so "failed" in the answer covers "fails" in the
    rewrite. Stop words and the words of signposts never count.
    """
    known = _vocabulary(answer) | _vocabulary(context)
    doc = parse(rewrite)
    if doc is None:
        return []
    found: list[str] = []
    seen: set[str] = set()
    for token in doc:
        if token.pos_ not in _CONTENT or token.is_stop:
            continue
        low, lemma = token.lower_, token.lemma_.lower()
        if not any(character.isalnum() for character in low):
            continue
        if low in known or lemma in known or lemma in _STRUCTURE_WORDS:
            continue
        if lemma in seen:
            continue
        seen.add(lemma)
        found.append(token.text)
    return found


def _text(value, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.split())
    return cleaned[:limit] or None


async def ask(provider: LlmProvider, prompt: str, transcript: str) -> dict:
    """The model's feedback on one answer, checked. Never raises.

    The dict is what `answers.feedback` stores: `status` always, and on `ok` or `refused`
    the notes, the rewrite or the words that withheld it.
    """
    if not words_of(transcript):
        return {"status": "skipped", "detail": "nothing was heard in the answer"}

    try:
        completion = await asyncio.wait_for(
            provider.complete(
                [
                    ChatMessage(role="system", content=INSTRUCTION),
                    ChatMessage(
                        role="user",
                        content=(
                            f"The question: {prompt}\n\n"
                            f"Their answer, as the recogniser wrote it:\n{transcript}"
                        ),
                    ),
                ],
                max_tokens=ANSWER_FEEDBACK_MAX_TOKENS,
                temperature=ANALYSIS_TEMPERATURE,
            ),
            timeout=ANSWER_FEEDBACK_TIMEOUT_S,
        )
    except TimeoutError:
        return {
            "status": "unavailable",
            "detail": f"no answer within {ANSWER_FEEDBACK_TIMEOUT_S:.0f} s",
        }
    except LlmError as exc:
        return {"status": "unavailable", "detail": f"{type(exc).__name__}: {exc}"}

    parsed = _json_object(completion.text)
    if parsed is None:
        return {
            "status": "unparseable",
            "model": completion.model,
            "detail": completion.text[:300],
        }

    notes = [_text(parsed.get("lead"), 400)]
    raw_gaps = parsed.get("gaps")
    notes += [
        _text(gap, 400) for gap in (raw_gaps if isinstance(raw_gaps, list) else [])
    ]
    kept = [note for note in notes if note and not _HEARD.search(note)]
    dropped = [note for note in notes if note and _HEARD.search(note)]
    lead = notes[0] if notes[0] in kept else None
    gaps = [note for note in kept if note is not lead][:2]

    rewrite = _text(parsed.get("rewrite"), 2000)
    if rewrite and _HEARD.search(rewrite):
        dropped.append(rewrite)
        rewrite = None
    added = invented(transcript, prompt, rewrite) if rewrite else []
    refused = len(added) > ANSWER_REWRITE_MAX_INVENTED

    return {
        "status": "refused" if refused else "ok",
        "by": "llm",
        "model": completion.model,
        "latency_ms": completion.latency_ms,
        "lead": lead,
        "gaps": gaps,
        "rewrite": None if refused else rewrite,
        # Kept so the refusal can be read and counted; never sent to the page.
        "withheld_rewrite": rewrite if refused else None,
        "rewrite_sentences": len(sentences(rewrite)) if rewrite else None,
        "invented": added,
        "dropped_notes": len(dropped),
    }
