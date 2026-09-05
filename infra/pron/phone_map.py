"""ARPAbet (g2p_en) → eSpeak-IPA token ids (facebook/wav2vec2-lv-60-espeak-cv-ft).

**This is the most dangerous file in the pronunciation path**, and it is dangerous in a
specific way: a wrong entry here does not raise. It produces a confident GOP number that
measures nothing, for every recording, forever. Handoff §9 trap 1 exists because of this
file, and the m0 spike existed largely to prove the table is right.

Two live traps in this particular vocabulary, both confirmed present:

  * ``ɡ`` is U+0261 LATIN SMALL LETTER SCRIPT G, **not** ASCII ``g``. ASCII ``g`` is not
    in the 392-token vocabulary at all. A map typed on a keyboard loses every /g/.
  * ``r`` (id 31) *is* in the vocabulary — it is the trill other languages use. English
    /r/ is ``ɹ`` (id 27). Mapping ``R → "r"`` raises nothing; it just scores every
    English r against an acoustic target no English speaker produces.

Neither is caught by any test that only checks "did we get a number". So this module
holds two safety properties, and both are load-bearing:

1. **It asserts its whole table against the model's real ``vocab.json`` at import.** Not
   at first request, not in a test — at import, so that nothing in this process can score
   anything before the check has run. The Dockerfile imports it during the build, which
   turns a bad edit into a failed build.
2. **``map_phone`` raises on an unmapped phone.** It never returns a default and never
   skips. A skipped phone is a pronunciation error that silently never gets scored, which
   is worse than a crash because it looks like success.

Carried over from ``spike/phone_map.py`` nearly as written (plan §7 m8). The differences
are that the vocabulary is the file vendored into the image rather than the spike's dump,
and that the reverse id→token index is built here rather than assigned by the caller —
in the spike ``gop.py`` set ``pm.ID_TO_TOK`` from outside, and a module whose correctness
depends on a caller remembering to initialise it is one import away from silence.
"""

from __future__ import annotations

import json
import os

VOCAB_PATH = os.environ.get("PRON_VOCAB_PATH", os.path.join(os.path.dirname(__file__), "vocab.json"))

# ARPAbet phone → acceptable model tokens, best first.
#
# A list rather than a single token because one canonical phone can have more than one
# legitimate surface realisation, and scoring against only the first would mark correct
# speech wrong. GOP takes the best-scoring member (gop.py) — which is the definition of
# "was this phone produced acceptably", not "was it produced the way I first wrote down".
ARPABET_TO_IPA: dict[str, list[str]] = {
    # ── monophthongs ────────────────────────────────────────────────────────
    "AA": ["ɑː", "ɑ"],
    "AE": ["æ"],
    "AH": ["ʌ"],  # stressed only; AH0 is remapped to schwa below
    "AO": ["ɔː", "ɔ"],
    "EH": ["ɛ"],
    "ER": ["ɚ", "ɜː"],
    "IH": ["ɪ"],
    "IY": ["iː"],
    "UH": ["ʊ"],
    "UW": ["uː", "u"],
    # ── diphthongs ──────────────────────────────────────────────────────────
    "AW": ["aʊ"],
    "AY": ["aɪ"],
    "EY": ["eɪ"],
    "OW": ["oʊ"],
    "OY": ["ɔɪ"],
    # ── consonants ──────────────────────────────────────────────────────────
    "B": ["b"],
    "CH": ["tʃ"],
    "D": ["d"],
    "DH": ["ð"],
    "F": ["f"],
    "G": ["ɡ"],  # U+0261. NOT ASCII "g" — see the module docstring.
    "HH": ["h"],
    "JH": ["dʒ"],
    "K": ["k"],
    "L": ["l", "ɫ"],
    "M": ["m"],
    "N": ["n"],
    "NG": ["ŋ"],
    "P": ["p"],
    "R": ["ɹ"],  # NOT "r" (id 31, the trill) — see the module docstring.
    "S": ["s"],
    "SH": ["ʃ"],
    "T": ["t", "ɾ"],  # ɾ is the American intervocalic flap: a *correct* realisation
    "TH": ["θ"],
    "V": ["v"],
    "W": ["w"],
    "Y": ["j"],
    "Z": ["z"],
    "ZH": ["ʒ"],
}

# Unstressed AH is schwa in eSpeak, and schwa is by far the most frequent vowel in
# English. Scoring every unstressed AH against /ʌ/ would depress GOP across ordinary
# function words — "a", "the", "of", "about" — and present as a pronunciation problem
# the speaker does not have. This is a correctness fix, not a refinement.
STRESS_OVERRIDES: dict[str, list[str]] = {
    "AH0": ["ə", "əl"],
    "ER0": ["ɚ"],
    "ER1": ["ɜː", "ɚ"],
    "ER2": ["ɜː", "ɚ"],
}

# eSpeak emits these r-coloured composites as SINGLE tokens where g2p_en emits two
# ARPAbet phones. Every *symbol* maps; *segmentation* can differ around rhotics. m0 saw
# no harm from it and deferred the question here — gop.py reports the affected rows so
# the decision can be made on measurement rather than on this comment. See
# docs/decisions/0005 §5.
R_COMPOSITES: list[str] = ["ɑːɹ", "ɔːɹ", "oːɹ", "ɛɹ", "ɪɹ", "ʊɹ", "aɪɚ", "aɪə"]


class PhoneMapError(KeyError):
    """The map and the model's vocabulary disagree, or a phone has no entry.

    A KeyError subclass so that `except KeyError` around a lookup still catches it, and a
    named type so that the service can tell this apart from an ordinary missing key and
    report it as a configuration fault rather than a bad recording.
    """


def strip_stress(phone: str) -> str:
    """``"AH0"`` → ``"AH"``. Stress digits are g2p_en's, not the vocabulary's."""
    return phone[:-1] if phone and phone[-1].isdigit() else phone


def load_vocab(path: str = VOCAB_PATH) -> dict[str, int]:
    """The model's own token→id map, as shipped on the hub.

    Read as plain JSON rather than through ``Wav2Vec2PhonemeCTCTokenizer``, which would
    pull in `phonemizer` and the espeak-ng binary to do a job this file does itself.
    """
    with open(path, encoding="utf-8") as handle:
        vocab = json.load(handle)
    # The spike wrapped the vocabulary in an envelope; the hub file is the bare mapping.
    # Accept the envelope so a dump from spike/out/ can still be pointed at in a test.
    if "vocab" in vocab and isinstance(vocab["vocab"], dict):
        vocab = vocab["vocab"]
    if not isinstance(vocab, dict) or not vocab:
        raise PhoneMapError(f"{path} is not a token→id mapping")
    return vocab


def build(vocab: dict[str, int]) -> dict[str, list[int]]:
    """ARPAbet-with-stress → [token ids]. Raises on anything that does not map.

    Every token named anywhere in this module is checked against the real vocabulary
    *before* a single entry is emitted, so a partial table can never be returned. The
    error names every offender at once rather than the first, because fixing these one
    failed import at a time is how a tired person starts deleting entries.
    """
    missing: list[tuple[str, str]] = []
    for symbol in list(ARPABET_TO_IPA) + list(STRESS_OVERRIDES):
        for token in STRESS_OVERRIDES.get(symbol) or ARPABET_TO_IPA[symbol]:
            if token not in vocab:
                missing.append((symbol, token))
    if missing:
        raise PhoneMapError(
            "phone map references tokens absent from the model vocabulary: "
            + ", ".join(f"{s}->{t!r}" for s, t in missing)
            + " — fix the map, do NOT drop the phone"
        )

    table: dict[str, list[int]] = {}
    for symbol, tokens in ARPABET_TO_IPA.items():
        for stress in ("", "0", "1", "2"):
            key = symbol + stress
            table[key] = [vocab[t] for t in STRESS_OVERRIDES.get(key, tokens)]
    for key, tokens in STRESS_OVERRIDES.items():
        table[key] = [vocab[t] for t in tokens]
    return table


def map_phone(phone: str, table: dict[str, list[int]]) -> list[int]:
    """Look up one g2p_en phone. Fails loudly — never returns a silent default."""
    if phone in table:
        return table[phone]
    base = strip_stress(phone)
    if base in table:
        return table[base]
    raise PhoneMapError(
        f"unmapped phone {phone!r} (base {base!r}). g2p_en produced a symbol this map "
        f"does not cover. Add it to ARPABET_TO_IPA — do not skip it. A skipped phone is "
        f"a pronunciation error that silently never gets scored."
    )


# ── The import-time assertion ────────────────────────────────────────────────
#
# Safety property 1. Everything above is a definition; this is the check. It runs on
# import, so no code path in this process can reach `score()` without it having passed,
# and the Dockerfile runs it during the build so a bad edit never becomes an image.

VOCAB: dict[str, int] = load_vocab()
TABLE: dict[str, list[int]] = build(VOCAB)
ID_TO_TOKEN: dict[int, str] = {i: t for t, i in VOCAB.items()}


def summary() -> str:
    """One line, printed by the Docker build, so the check is visible rather than implied."""
    return (
        f"phone map OK: {len(ARPABET_TO_IPA)} ARPAbet phones, "
        f"{len(TABLE)} phone×stress keys, against {len(VOCAB)} vocabulary tokens "
        f"(ɡ={VOCAB['ɡ']} U+0261, ɹ={VOCAB['ɹ']}, r={VOCAB.get('r')} left unused)"
    )


if __name__ == "__main__":
    print(summary())
    print()
    print(f"{'ARPA':<6}{'IPA':<12}{'ids':<14}note")
    print("-" * 62)
    notes = {
        "G": "U+0261 script g, not ASCII",
        "R": "not 'r' (id 31 = trill)",
        "AH": "AH0 → schwa, below",
        "T": "flap is a correct realisation",
        "ER": "stress-conditioned",
    }
    for symbol, tokens in ARPABET_TO_IPA.items():
        ids = str([VOCAB[t] for t in tokens])
        print(f"{symbol:<6}{' '.join(tokens):<12}{ids:<14}{notes.get(symbol, '')}")
    print("-" * 62)
    for key, tokens in STRESS_OVERRIDES.items():
        ids = str([VOCAB[t] for t in tokens])
        print(f"{key:<6}{' '.join(tokens):<12}{ids:<14}stress override")
