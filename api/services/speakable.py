"""Which words this system will say out loud, and why that list is closed.

A screen that names a sound should be able to play it, and the shortest way to build
that would be a route that synthesises whatever text it is given. This is not that.
An open synthesis endpoint is a different product with a different cost — anybody with
an account could drive the voice with arbitrary text — and the requirement that exists
is *let me hear this sound in a word I have to say*, which needs a vocabulary and not a
text box.

So a word is speakable when the system itself already chose it:

- it is the example word in one of the phone names, which this project wrote; or
- it appears in one of the shipped passages; or
- it appears in a script the requester wrote themselves.

Somebody else's script is not in the set. Two accounts asking for the same word can get
different answers, and that is the point: the third rule is about the asker's own text,
so what it grants is bounded by what they already had.

**A word outside the set is a 404 rather than a 400.** The caller is not owed the
difference between *that is not a word* and *that is not a word you may hear*, and a 400
would confirm the shape of the set to somebody probing it.

The tokeniser is `wer.normalise`, the one that compares a script with what the
recogniser heard. That is deliberate: the words offered to hear are then exactly the
words the differences screen shows, rather than a second, slightly different idea of
what a word is.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db_models import Passage, Presentation, PresentationSection, User
from services import phone_names, wer

# Every example word, for the lookup that needs no database at all. These are the
# product's own words about English and belong to no account.
EXAMPLE_WORDS: frozenset[str] = frozenset(phone_names.EXAMPLE_WORDS.values())


def _one_word(requested: str) -> str | None:
    """The single normalised word in `requested`, or None if it is not one word.

    Two words fail here, and so do marks that normalise away to none. A request for
    `see the` is not a request for a word, and answering it with the first one would be
    guessing at what was meant.

    A figure does not fail here. `2026` is one word to this tokeniser, so it goes on to
    be judged by whether the asker's own text contains it, like anything else — there is
    no separate rule about numbers, and inventing one would mean deciding on the
    caller's behalf which of their own words they may hear.
    """
    words = wer.normalise(requested)
    return words[0] if len(words) == 1 else None


def _contains(column, word: str):
    """A case-insensitive substring test, used only to narrow before tokenising.

    It cannot miss a real hit — a word that is a token is also a substring — and the
    hits it adds (`is` inside `this`) are removed by the tokeniser afterwards. The
    order matters for cost: the database discards most rows, and only the survivors are
    split into words in this process.
    """
    return column.ilike(f"%{word}%")


async def word_to_speak(db: AsyncSession, user: User, requested: str) -> str | None:
    """The word this account may hear, normalised, or None if it may not hear it.

    Returning the normalised word rather than True is what lets the caller synthesise
    the form the system holds — `Fewer?` becomes `fewer` — instead of passing the
    request's own spelling to the voice.
    """
    word = _one_word(requested)
    if word is None:
        return None

    if word in EXAMPLE_WORDS:
        return word

    passages = await db.execute(
        select(Passage.body).where(Passage.is_active, _contains(Passage.body, word))
    )
    for body in passages.scalars():
        if word in wer.normalise(body):
            return word

    sections = await db.execute(
        select(PresentationSection.body)
        .join(Presentation, PresentationSection.presentation_id == Presentation.id)
        .where(
            Presentation.user_id == user.id,
            _contains(PresentationSection.body, word),
        )
    )
    for body in sections.scalars():
        if word in wer.normalise(body):
            return word

    return None


__all__ = ["EXAMPLE_WORDS", "word_to_speak"]
