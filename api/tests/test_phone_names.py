"""Naming the thirty-nine sounds, and keeping the table honest about the inventory.

The names are content rather than logic, so what is worth testing is not the wording of
any one of them: it is that every sound the scorer can emit has a name, that no name
exists for a sound it cannot, and that the stress a phone carries in the data does not
produce a second, nameless version of the same sound.
"""

from __future__ import annotations

import pytest

from models.common import ARPABET_PHONES
from services.phone_names import PHONE_NAMES, name_of


def test_every_sound_the_scorer_can_emit_has_a_name():
    assert set(PHONE_NAMES) == set(ARPABET_PHONES)
    assert len(PHONE_NAMES) == 39


@pytest.mark.parametrize("phone", ARPABET_PHONES)
def test_a_name_says_a_sound_and_an_example_word(phone):
    name = PHONE_NAMES[phone]

    assert name == name.lower()
    assert '"' in name, f"{phone} names no example word"
    assert not name.startswith("/"), f"{phone} is named in code, not in words"


def test_stress_is_folded_away_before_a_sound_is_named():
    assert name_of("IY0") == name_of("IY1") == name_of("IY") == 'the vowel in "see"'
    assert name_of("AH2") == 'the vowel in "cup"'


def test_a_sound_this_table_has_never_met_is_shown_as_its_code():
    # Never raises: a take already scored should still render if a future model emits a
    # symbol this table does not know.
    assert name_of("QQ") == "/QQ/"


def test_the_five_a_real_speaker_ran_into_are_named_the_way_they_were_written():
    assert name_of("IY") == 'the vowel in "see"'
    assert name_of("DH") == 'the "th" in "this"'
    assert name_of("NG") == 'the "ng" at the end of "sing"'
    assert name_of("Z") == 'the "z" at the end of "is"'
    assert name_of("ER") == 'the vowel in "her"'


def test_a_scored_phone_carries_its_name_beside_its_code():
    """The wire shape a reading and a take both send.

    Computed rather than stored, so a phone scored before this existed gains its name the
    moment it is read back, and the naming table stays in one place.
    """
    from models.attempt import PhonemeScoreOut

    scored = PhonemeScoreOut(
        word="see",
        word_idx=0,
        phone_idx=0,
        canonical_phone="IY1",
        recognized_phone="i",
        start_ms=0,
        end_ms=60,
        gop=-5.25,
        posterior=0.1,
    )

    assert scored.canonical_phone == "IY1"
    assert scored.canonical_name == 'the vowel in "see"'
