"""The phone map, against the model's real vocabulary and against this API's phone set.

**This is the test handoff trap 1 exists for**, and it is worth being explicit about what
it can and cannot catch. A wrong entry in `ARPABET_TO_IPA` does not raise, does not fail
a request, and does not look wrong in a heatmap. It produces a GOP number for every
recording forever, and that number measures the speaker's production of a sound they were
never asked to make. There is no downstream assertion that fails. So the check has to be
here, on the table itself, against the two things it has to agree with:

1. **The acoustic model's own `vocab.json`** — every token named in the map must exist,
   with the id the map thinks it has. `infra/pron/phone_map.py` asserts this at import;
   these tests assert that the assertion is real, by breaking it.
2. **`models/common.ARPABET_PHONES`** — the 39 symbols this API validates
   `passages.phoneme_focus` against. That tuple's own comment demands this: *"That module
   must assert its own keys equal this tuple: two copies of a phone set that drift apart
   is handoff trap 1, and a phone missing from one of them is a pronunciation error that
   is never scored and never reported as unscored."* This is where the two meet.

It runs with **no torch, no network and no 1.2 GB download**, which is the reason
`vocab.json` is vendored into the repository rather than fetched during the image build.
A test that only runs inside a 5 GB image is a test that stops being run.
"""

import importlib.util
import json
import os
import sys

import pytest

from models.common import ARPABET_PHONES

# The pron service's source, wherever it is. `/pron` is the read-only mount the test
# container gets (docker-compose.yml); the relative path is CI and a laptop, where the
# whole repository is checked out and api/ is a sibling of infra/.
_HERE = os.path.dirname(os.path.abspath(__file__))
_CANDIDATES = [
    "/pron",
    os.path.normpath(os.path.join(_HERE, "..", "..", "infra", "pron")),
]
PRON_SRC = next(
    (
        path
        for path in _CANDIDATES
        if os.path.isfile(os.path.join(path, "phone_map.py"))
    ),
    None,
)

pytestmark = pytest.mark.skipif(
    PRON_SRC is None,
    reason=f"infra/pron not reachable; looked in {_CANDIDATES}",
)


def load_phone_map(vocab_path: str | None = None):
    """Import `phone_map` fresh, optionally against a different vocabulary.

    Fresh every time because the interesting behaviour is at *import*: the table is built
    and asserted there, so a cached module would test nothing. `PRON_VOCAB_PATH` is the
    seam that lets a test point it at a deliberately broken vocabulary.
    """
    if vocab_path is not None:
        os.environ["PRON_VOCAB_PATH"] = vocab_path
    else:
        os.environ.pop("PRON_VOCAB_PATH", None)

    sys.modules.pop("phone_map", None)
    spec = importlib.util.spec_from_file_location(
        "phone_map", os.path.join(PRON_SRC, "phone_map.py")
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["phone_map"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def phone_map():
    module = load_phone_map()
    yield module
    os.environ.pop("PRON_VOCAB_PATH", None)
    sys.modules.pop("phone_map", None)


# ── The two phone sets agree ────────────────────────────────────────────────


def test_the_map_covers_exactly_this_apis_phone_set(phone_map):
    """39 symbols in `models/common`, 39 in the map, and they are the same 39.

    Set equality in both directions rather than a length check. A map with 39 entries one
    of which is `"TZ"` would pass a count, and the phone it displaced would silently never
    be scored.
    """
    assert set(phone_map.ARPABET_TO_IPA) == set(ARPABET_PHONES)
    assert len(ARPABET_PHONES) == 39


def test_every_phone_resolves_to_real_vocabulary_ids(phone_map):
    """No phone is unmapped, and every id is a real id in the model's vocabulary."""
    ids = set(phone_map.VOCAB.values())
    for symbol in ARPABET_PHONES:
        for stress in ("", "0", "1", "2"):
            mapped = phone_map.map_phone(symbol + stress, phone_map.TABLE)
            assert mapped, f"{symbol}{stress} mapped to nothing"
            assert (
                set(mapped) <= ids
            ), f"{symbol}{stress} names an id not in the vocabulary"


# ── The two traps m0 found, asserted as facts about this vocabulary ─────────


def test_g_is_the_script_g_and_ascii_g_is_absent(phone_map):
    """U+0261, not the keyboard letter — and the keyboard letter is not there at all.

    Both halves matter. If ASCII `g` were merely a different id, a wrong map would still
    score /g/ against *something*. It is absent entirely, so the import-time assertion
    catches it — which is only true as long as this stays true of the vocabulary.
    """
    assert "g" not in phone_map.VOCAB
    assert phone_map.VOCAB["ɡ"] == 35
    assert phone_map.ARPABET_TO_IPA["G"] == ["ɡ"]
    assert ord(phone_map.ARPABET_TO_IPA["G"][0]) == 0x0261


def test_r_maps_to_the_approximant_not_the_trill_that_also_exists(phone_map):
    """The dangerous one: `r` IS in the vocabulary, and it is the wrong sound.

    Mapping `R → "r"` raises nothing and breaks nothing visibly. It scores every English
    r against a trill no English speaker produces, and the learner is told their /r/ is
    weak. This test is the only thing standing between that and production.
    """
    assert phone_map.VOCAB["r"] == 31, "the trill is still in the vocabulary"
    assert phone_map.VOCAB["ɹ"] == 27
    assert phone_map.ARPABET_TO_IPA["R"] == ["ɹ"]
    assert 31 not in phone_map.map_phone("R1", phone_map.TABLE)


def test_unstressed_ah_is_schwa(phone_map):
    """AH0 → ə, not ʌ. Schwa is the most frequent vowel in English.

    Without the override, every "a", "the" and "about" in a passage would be scored
    against a stressed vowel the speaker correctly did not produce — a depressed GOP
    across ordinary function words that reads as a pronunciation problem.
    """
    assert phone_map.map_phone("AH0", phone_map.TABLE) == [
        phone_map.VOCAB["ə"],
        phone_map.VOCAB["əl"],
    ]
    assert phone_map.map_phone("AH1", phone_map.TABLE) == [phone_map.VOCAB["ʌ"]]


def test_the_flap_is_an_accepted_realisation_of_t(phone_map):
    """`butter` with an American flap is correct speech, not a substitution."""
    assert phone_map.VOCAB["ɾ"] in phone_map.map_phone("T", phone_map.TABLE)
    assert phone_map.VOCAB["t"] in phone_map.map_phone("T", phone_map.TABLE)


# ── The safety properties themselves ────────────────────────────────────────


def test_an_unmapped_phone_raises_rather_than_returning_a_default(phone_map):
    """The property that makes a gap loud.

    A `.get(phone, [])` here would turn "this phone has no acoustic target" into "this
    phone scored nothing", which is indistinguishable from correct speech in every
    aggregate downstream.
    """
    with pytest.raises(phone_map.PhoneMapError) as raised:
        phone_map.map_phone("QQ", phone_map.TABLE)
    assert "do not skip it" in str(raised.value)


def test_a_vocabulary_missing_a_token_fails_at_import(tmp_path):
    """Break the vocabulary; the module must refuse to load.

    This is the assertion the Dockerfile runs during the build. Removing `θ` stands in
    for the real scenario — an upstream model with a different phone inventory — and the
    required behaviour is a hard failure naming the offender, not a table with a hole in
    it.
    """
    real = json.load(open(os.path.join(PRON_SRC, "vocab.json"), encoding="utf-8"))
    del real["θ"]
    broken = tmp_path / "vocab.json"
    broken.write_text(json.dumps(real, ensure_ascii=False), encoding="utf-8")

    try:
        with pytest.raises(Exception) as raised:
            load_phone_map(str(broken))
        assert "TH" in str(raised.value)
        assert "do NOT drop the phone" in str(raised.value)
    finally:
        os.environ.pop("PRON_VOCAB_PATH", None)
        sys.modules.pop("phone_map", None)


def test_the_vocabulary_is_the_one_m0_measured_against(phone_map):
    """392 tokens. A different count means different ids mean different sounds.

    Every GOP this system has ever stored is a statement about these particular ids. If
    the vendored vocabulary changes, stored scores stop meaning what they meant, and that
    is a migration rather than a rebuild.
    """
    assert len(phone_map.VOCAB) == 392
