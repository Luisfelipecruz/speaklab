"""Passage wire shapes.

`body` is absent from the list row and present in the detail. Twelve passages of ~80
words each is not a payload worth worrying about; the reason is that the list is a
chooser and the body is the exercise, and a list endpoint that returns everything
invites a client to render from it and then never fetch the passage it is scoring
against — at which point the text on screen and the text the WER is computed from are
two different strings that only agree by luck.
"""

from pydantic import Field, field_validator

from models.common import ARPABET_PHONES, CEFRBand, ORMModel, SeedModel, Slug


class PassageSummary(ORMModel):
    slug: str
    title: str
    cefr_band: CEFRBand
    phoneme_focus: list[str]

    # Stored, not derived on read. It is what the chooser shows as "about 40 seconds",
    # and a test checks it against `body` so an edited passage cannot keep a stale one.
    word_count: int


class PassageDetail(PassageSummary):
    body: str


class PassageSeed(SeedModel):
    """One record in `seeds/passages.json`.

    `word_count` is absent by design: it is a fact about `body`, and a seed file that
    states it separately is a seed file that can disagree with itself. The loader
    computes it with the same function the test checks against.
    """

    slug: Slug
    title: str = Field(min_length=1)
    body: str = Field(min_length=1)
    cefr_band: CEFRBand
    phoneme_focus: list[str] = Field(min_length=1)
    is_active: bool = True

    @field_validator("phoneme_focus")
    @classmethod
    def _known_arpabet(cls, phones: list[str]) -> list[str]:
        """Reject a phone the system cannot score.

        A passage declaring `["Θ"]` or `["th"]` or `["TH0"]` would load, appear in the
        filter list, and match nothing — a passage that exists and is unreachable. The
        failure belongs at seed time, where it names the symbol.
        """
        unknown = [p for p in phones if p not in ARPABET_PHONES]
        if unknown:
            raise ValueError(
                f"not ARPAbet: {unknown}. The 39 valid symbols are in "
                f"models/common.py — uppercase and unstressed, e.g. 'TH', not 'th'."
            )
        return phones


def word_count(body: str) -> int:
    """Whitespace-separated tokens.

    Naive on purpose and stated so: "twenty-one" is one word and "e.g." is one word.
    What matters is that the seed loader and the test that checks it use the same
    function, so the stored number means one thing rather than approximately one thing.
    """
    return len(body.split())
