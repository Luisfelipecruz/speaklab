"""Word/phone alignment for the reference text — the tokeniser, and what it fixed.

`infra/pron/g2p.py` converts a passage to canonical phones *whole*, because part-of-speech
context is what resolves homographs, and then has to attribute the flat result back to
individual words so the heatmap can tint them. That re-attribution is what breaks, and it
broke here:

    The m0 spike's rule — a surface word is a whitespace token with `.,!?;:` stripped —
    **desyncs on 2 of the 12 seeded passages.** Both contain a standalone em dash, which
    survives that strip, counts as a word, and produces no phones: 79 surface words
    against 78 phone groups, and `spike/gop.py` raises on it. Read-aloud would have been
    broken on a sixth of the shipped corpus, presenting as an alignment bug rather than a
    tokenisation one.

The rule now is *a token containing at least one letter*, and the counts below are the
regression test for it, over the real seed file rather than a fixture that cannot notice
the corpus changing.

**These tests do not import `g2p_en`**, which is not in the API image and never will be.
Everything asserted here is a pure function of strings: `surface_words` takes text,
`phone_groups` takes a token list, and `words_with_phones` takes its converter as an
argument — which is why a stub can drive it. The other half, that real `g2p_en` output
still agrees with these counts, is `test_gop.py`, which runs against the live service.
"""

import importlib.util
import json
import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_CANDIDATES = [
    "/pron",
    os.path.normpath(os.path.join(_HERE, "..", "..", "infra", "pron")),
]
PRON_SRC = next(
    (p for p in _CANDIDATES if os.path.isfile(os.path.join(p, "g2p.py"))), None
)

pytestmark = pytest.mark.skipif(
    PRON_SRC is None, reason=f"infra/pron not reachable; looked in {_CANDIDATES}"
)

SEEDS = os.path.join(_HERE, "..", "seeds", "passages.json")

# Word count and phone count for each seeded passage, produced by real `g2p_en` 2.1.0
# through `words_with_phones`. The word counts are asserted here; the phone counts are
# what `test_gop.py` checks against the live service, and they are recorded together so
# the two halves of the contract sit in one place.
#
# 12 of 12 align. Before the tokeniser fix, two did not.
EXPECTED = {
    "third-street-theatre": (79, 250),
    "they-gathered-there": (78, 260),
    "the-village-above-the-river": (79, 254),
    "the-zoo-on-tuesday": (76, 255),
    "a-pleasure-to-measure": (78, 262),
    "the-ship-and-the-sheep": (79, 229),
    "the-cat-and-the-cup": (76, 225),
    "spring-street-school": (75, 297),
    "the-young-singer": (73, 262),
    "the-rural-library": (73, 253),
    "in-june-the-judge": (72, 257),
    "she-asked-for-the-texts": (79, 287),
}
TOTAL_PHONES = 3091


def load_g2p_module():
    sys.modules.pop("pron_g2p", None)
    spec = importlib.util.spec_from_file_location(
        "pron_g2p", os.path.join(PRON_SRC, "g2p.py")
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["pron_g2p"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def g2p_module():
    return load_g2p_module()


@pytest.fixture(scope="module")
def passages():
    with open(SEEDS, encoding="utf-8") as handle:
        return {p["slug"]: p for p in json.load(handle)}


# ── The regression ──────────────────────────────────────────────────────────


def test_a_standalone_em_dash_is_not_a_word(g2p_module):
    """The exact shape that desynced two passages.

    An em dash between spaces is punctuation a reader pauses on, not a word they say. It
    produces no phones, so counting it as a word guarantees one more surface word than
    there are phone groups — and the alignment that follows attributes every phone from
    that point on to the word before it.
    """
    assert g2p_module.surface_words("casual, almost unusual — she should share") == [
        "casual",
        "almost",
        "unusual",
        "she",
        "should",
        "share",
    ]


@pytest.mark.parametrize("mark", ["—", "–", "-", "…", "'", '"', "(", ")"])
def test_no_punctuation_only_token_is_ever_a_word(g2p_module, mark):
    """The general form of the same bug.

    Parameterised rather than written once for the em dash, because the failure was not
    "we forgot the em dash" — it was "the rule was a list of punctuation somebody thought
    of". The rule that replaced it is *contains a letter*, and this is what says so.
    """
    assert g2p_module.surface_words(f"alpha {mark} beta") == ["alpha", "beta"]


def test_every_seeded_passage_aligns(g2p_module, passages):
    """All 12, by word count, against the counts real g2p_en produces.

    Over the seed file the product actually ships rather than over a fixture: a passage
    added next month with a number or an abbreviation in it fails here, which is a
    thirty-second fix, rather than at the first person who tries to read it aloud.
    """
    for slug, (words, _phones) in EXPECTED.items():
        assert slug in passages, f"{slug} is no longer in the seed file"
        counted = len(g2p_module.surface_words(passages[slug]["body"]))
        assert counted == words, f"{slug}: {counted} surface words, expected {words}"


def test_the_seed_file_has_not_grown_without_this_test_noticing(passages):
    """A new passage with no entry above is a passage nobody checked the alignment of."""
    assert set(passages) == set(EXPECTED)


# ── The grouping and the desync check ───────────────────────────────────────


def test_punctuation_tokens_do_not_close_a_word(g2p_module):
    """`g2p_en` emits raw punctuation alongside phones; only a space ends a word."""
    tokens = ["DH", "AH0", " ", "K", "AE1", "T", " ", ",", " ", "S", "AE1", "T"]
    assert g2p_module.phone_groups(tokens) == [
        ["DH", "AH0"],
        ["K", "AE1", "T"],
        ["S", "AE1", "T"],
    ]


def test_a_desync_raises_and_says_what_it_saw(g2p_module):
    """When the two sequences disagree, nothing is scored.

    A misaligned passage does not produce slightly-wrong scores; it produces every phone
    attributed to the wrong word from the divergence onward. The check exists because
    passages are authored content and the corpus will grow — `$5` becomes two phone
    groups for one token, `Dr.` becomes three phones plus a stray group — and a 422 that
    names the passage is a bug report, where a scored misalignment is a screen full of
    confident nonsense.
    """

    def stub(_text):
        return ["K", "AE1", "T"]  # one group for a two-word text

    with pytest.raises(g2p_module.TextAlignmentError) as raised:
        g2p_module.words_with_phones("the cat", stub)
    message = str(raised.value)
    assert "2 words" in message and "1 phone groups" in message


def test_words_carry_their_own_index_and_surface_form(g2p_module):
    """The heatmap tints by `word_idx`; the tooltip shows `word`. Both come from here."""

    def stub(_text):
        return ["DH", "AH0", " ", "K", "AE1", "T"]

    words = g2p_module.words_with_phones("The cat.", stub)
    assert [(w.index, w.surface, w.phones) for w in words] == [
        (0, "the", ["DH", "AH0"]),
        (1, "cat", ["K", "AE1", "T"]),
    ]


def test_flatten_is_the_single_definition_of_position_n(g2p_module):
    """Targets are built in this order and the aligner's output is read back in it.

    One function decides what position *n* means, so the two cannot drift. If they did,
    every phone would be attributed to a neighbouring word and nothing would look wrong.
    """

    def stub(_text):
        return ["DH", "AH0", " ", "K", "AE1", "T"]

    flat = g2p_module.flatten(g2p_module.words_with_phones("The cat.", stub))
    assert flat == [
        (0, "the", 0, "DH"),
        (0, "the", 1, "AH0"),
        (1, "cat", 0, "K"),
        (1, "cat", 1, "AE1"),
        (1, "cat", 2, "T"),
    ]
