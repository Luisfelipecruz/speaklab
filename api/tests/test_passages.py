"""Passage browsing, and the integrity of the passage content itself.

A passage makes a promise its text has to keep. `phoneme_focus: ["TH"]` says the text
was engineered to force /θ/ repeatedly, not to mention it once — a passage with two
instances of its target sound wastes an attempt, and no phoneme trend is plotted until
five attempts are behind it. The density check below is deliberately crude, because the
honest version needs G2P, which is not in this image; what it can catch is a passage that
does not exercise its focus at all.
"""

import re

import pytest
from sqlalchemy import select

from db_models import Passage
from models.common import ARPABET_PHONES
from models.passage import word_count

pytestmark = pytest.mark.usefixtures("seeded")

# Rough orthographic evidence that a phone is being exercised. Not a G2P: "ph" is /f/
# and "though" ends in nothing at all. It is a floor, not a measure — a passage that
# fails this is certainly not dense in its target sound.
ORTHOGRAPHY = {
    "TH": r"th",
    "DH": r"th",
    "V": r"v",
    "B": r"b",
    "S": r"s",
    "Z": r"[sz]",
    "SH": r"sh|ti|ci",
    "ZH": r"s|g",
    "IH": r"i",
    "IY": r"e{2}|ea|e",
    "AE": r"a",
    "AH": r"u|o",
    "T": r"t",
    "K": r"c|k",
    "P": r"p",
    "NG": r"ng|n",
    "N": r"n",
    "R": r"r",
    "L": r"l",
    "JH": r"j|g",
    "Y": r"y|u",
    "D": r"d",
}


async def test_the_list_returns_the_twelve_seeded_passages(client):
    response = await client.get("/passages")

    assert response.status_code == 200
    assert len(response.json()) == 12


async def test_the_list_row_omits_the_body(client):
    """The list is a chooser; the body is the exercise.

    A client that renders the reading from the list row and never fetches the passage
    is scoring against a string it did not get from the endpoint the WER uses.
    """
    row = (await client.get("/passages")).json()[0]

    assert set(row) == {"slug", "title", "cefr_band", "phoneme_focus", "word_count"}


async def test_band_filter_returns_only_that_band(client):
    body = (await client.get("/passages", params={"band": "A2"})).json()

    assert body
    assert {row["cefr_band"] for row in body} == {"A2"}


async def test_an_unknown_band_is_rejected(client):
    assert (await client.get("/passages", params={"band": "Z9"})).status_code == 422


async def test_phoneme_focus_filter_finds_the_passages_for_one_sound(client):
    """The query a recommendation is built on: give me something that exercises the
    phone this user is worst at."""
    body = (await client.get("/passages", params={"phoneme_focus": "TH"})).json()

    assert {row["slug"] for row in body} == {"third-street-theatre"}

    voiced = (await client.get("/passages", params={"phoneme_focus": "DH"})).json()
    assert {row["slug"] for row in voiced} == {"they-gathered-there"}


async def test_a_phone_no_passage_targets_is_an_empty_list(client):
    response = await client.get("/passages", params={"phoneme_focus": "OY"})

    assert response.status_code == 200
    assert response.json() == []


async def test_one_passage_by_slug_carries_the_body(client):
    response = await client.get("/passages/the-ship-and-the-sheep")

    assert response.status_code == 200
    body = response.json()
    assert "sheep" in body["body"]
    assert body["phoneme_focus"] == ["IH", "IY"]


async def test_an_unknown_slug_is_a_404_that_says_which_slug(client):
    response = await client.get("/passages/no-such-passage")

    assert response.status_code == 404
    assert "no-such-passage" in response.json()["detail"]


# ── The seed content itself ─────────────────────────────────────────────────


async def test_stored_word_count_matches_the_body(seeded):
    """The stored number is a fact about the text, and this is what stops it becoming
    a stale one after an edit. The loader derives it with this same function."""
    passages = (await seeded.scalars(select(Passage))).all()

    for passage in passages:
        assert passage.word_count == word_count(passage.body), (
            f"{passage.slug}: stored {passage.word_count}, "
            f"body has {word_count(passage.body)}"
        )


async def test_every_phoneme_focus_is_a_phone_the_system_can_score(seeded):
    """A phone set that drifts, caught at the content end.

    A passage declaring 'th' or 'TH1' would load, appear in the filter list, and match
    nothing the pron service ever emits — a passage that exists and is unreachable.
    """
    passages = (await seeded.scalars(select(Passage))).all()

    for passage in passages:
        assert passage.phoneme_focus
        for phone in passage.phoneme_focus:
            assert phone in ARPABET_PHONES, f"{passage.slug}: {phone!r} is not ARPAbet"


async def test_every_passage_shows_orthographic_evidence_of_its_focus(seeded):
    """Crude, and the docstring at the top of this file says why.

    A real density measure needs G2P over the body, which this image does not have. What
    this catches is the mistake that actually happens when a passage is edited: the text
    is rewritten, the focus is left behind, and the passage stops exercising the sound
    it claims to.
    """
    passages = (await seeded.scalars(select(Passage))).all()

    for passage in passages:
        body = passage.body.lower()
        for phone in passage.phoneme_focus:
            hits = len(re.findall(ORTHOGRAPHY[phone], body))
            assert hits >= 10, (
                f"{passage.slug} declares {phone} but its text shows only {hits} "
                f"plausible instances — that is not a phoneme-dense passage"
            )


async def test_passages_are_long_enough_to_be_worth_scoring(seeded):
    """Under ~50 words there are too few instances of any phone for a mean GOP to mean
    anything, and a trend is gated at 5 attempts — short passages make that gate take
    longer to open for no benefit."""
    passages = (await seeded.scalars(select(Passage))).all()

    for passage in passages:
        assert (
            50 <= passage.word_count <= 150
        ), f"{passage.slug} is {passage.word_count} words"
