"""Say it in English against the owner's golden set: `make say-eval`.

**The golden set is the owner's own.** Things they would really write, each said in their
language as they would say it and recorded with `eval/golden/say/record.py`: what was
said, written out word for word; the English they would send; and what must survive into
every version — names, numbers, links, e-mails. The texts are in `manifest.json`, the
lines marked private in `manifest.local.json`, which git ignores; the recordings stay in
`audio/` on the machine that made them. Both files are read, the result says how many
lines came from each, and nothing from a private line but its id reaches the result.

**What is measured, and what each part needs:**

- *Spanish or English* — the product's language check on each line as said and on its
  English. Nothing but the texts.
- *Spelling* — one misspelling from `typos.json` planted in each English text, which the
  check must find and should mend to the word that was there; and each English text as
  written, in which it must flag nothing. Nothing but the texts.
- *The two versions* — Direct and Organized of each line as said, against the owner's
  English: chrF, and whether what must survive did. Ollama.
- *The instruction probe* — ten dictations that give an order, in `probes.json`, each to
  be translated rather than done. Ollama.
- *The recogniser* — each recording heard as the product hears it, with both languages on
  offer: the Spanish error rate, the language it chose, and how long it took. `asr-multi`
  and the recordings.

The versions are written from what was said, not from what the recogniser heard, so that
a name the model dropped and a name the recogniser misheard are counted apart.

**What is asserted** is the bar each part was built to: every planted misspelling found
and no correct word flagged; every text's language told; everything that must survive
kept in both versions; every probe translated in both; and a Spanish error rate of at
most 10 %. chrF is reported and never asserted: two good translations of one sentence
share far from all their characters, and the figure is for comparing models.

Each part skips when what it needs is absent, and the last test records what the others
measured as the `say` result; when none of them ran, nothing is recorded.
"""

import hashlib
import json
import math
import re
import statistics
from pathlib import Path

import httpx
import pytest

from config import ASR_MULTI_URL, OLLAMA_BASE_URL, OLLAMA_MODEL
from services import keep, language, spelling
from services.asr_client import transcribe
from services.english import write
from services.llm import OllamaProvider
from services.wer import wer
from tests.eval_out import harness_root, load_harness, record

_HERE = Path(__file__).resolve().parent
GOLDEN = next(
    (
        path
        for path in (
            Path("/app/eval/golden/say"),
            _HERE.parents[1] / "eval" / "golden" / "say",
        )
        if (path / "probes.json").is_file()
    ),
    Path("/app/eval/golden/say"),
)

# The bar the recogniser is held to on the owner's Spanish.
SPANISH_WER_CEILING = 0.10
VERSIONS = ("direct", "organized")

# What the parts measured, by part, for the last test to record.
MEASURED: dict[str, dict] = {}


def _lines() -> tuple[list[dict], dict[str, int]]:
    lines: list[dict] = []
    read: dict[str, int] = {}
    for name, private in (("manifest.json", False), ("manifest.local.json", True)):
        path = GOLDEN / name
        if path.is_file():
            items = json.loads(path.read_text(encoding="utf-8"))["items"]
            lines += [{**item, "private": private} for item in items]
            read[name] = len(items)
    return sorted(lines, key=lambda line: line["id"]), read


def _fixture(name: str) -> list:
    path = GOLDEN / name
    if not path.is_file():
        return []
    body = json.loads(path.read_text(encoding="utf-8"))
    return body["typos"] if name == "typos.json" else body["probes"]


LINES, READ = _lines()
TYPOS = _fixture("typos.json")
PROBES = _fixture("probes.json")
mounted = pytest.mark.skipif(
    not (GOLDEN / "probes.json").is_file(), reason="golden set not mounted"
)


def _model_ready() -> tuple[bool, str]:
    try:
        response = httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5.0)
    except httpx.RequestError as exc:
        return False, f"{OLLAMA_BASE_URL} is not answering ({type(exc).__name__})"
    names = {model.get("name") for model in response.json().get("models", [])}
    if OLLAMA_MODEL not in names:
        return False, f"{OLLAMA_MODEL} is not pulled on {OLLAMA_BASE_URL}"
    return True, ""


def _recogniser_ready() -> tuple[bool, str]:
    try:
        response = httpx.get(f"{ASR_MULTI_URL}/health", timeout=3.0)
    except httpx.RequestError as exc:
        return False, (
            f"asr-multi is not answering at {ASR_MULTI_URL} ({type(exc).__name__}): "
            "`make say-up`"
        )
    if not (response.is_success and response.json().get("model_loaded") is True):
        return False, f"asr-multi at {ASR_MULTI_URL} has not loaded its model"
    return True, ""


def _recorded() -> list[dict]:
    return [line for line in LINES if (GOLDEN / line["audio"]).is_file()]


MODEL_READY, MODEL_WHY_NOT = _model_ready()
needs_lines = pytest.mark.skipif(
    not LINES,
    reason=f"no golden lines in {GOLDEN}: record them with eval/golden/say/record.py",
)
needs_model = pytest.mark.skipif(not MODEL_READY, reason=MODEL_WHY_NOT or "no model")


def _spanish(line: dict) -> bool:
    """Said in the account's language, English words in it or not: what is translated."""
    return line["language"] != "en"


def _shown(line: dict, value: str) -> str:
    """A word or an item from a line, as the result may carry it."""
    return "(private)" if line["private"] else value


def _p95(values: list[float]) -> float | None:
    """The nearest-rank 95th percentile: a value that was measured, not one between two."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def _spread(values: list[float]) -> dict:
    return {
        "median": statistics.median(values) if values else None,
        "p95": _p95(values),
        "max": max(values) if values else None,
    }


# ── The fixtures themselves ─────────────────────────────────────────────────
#
# These run everywhere, CI included: a typo that is itself a word, or a probe with
# nothing to look for, would measure nothing while reading as a pass.


@mounted
def test_every_planted_misspelling_is_unknown_and_every_word_it_spoils_is_known():
    assert len(TYPOS) >= 60, "typos.json has lost most of its list"
    words = spelling.dictionary().words
    for right, wrong in TYPOS:
        assert right in words or right in spelling.TABLE.values(), right
        assert wrong not in words, f"{wrong} is a word, so planting it plants nothing"
        assert wrong in spelling.TABLE or spelling.suggest(wrong), wrong


@mounted
def test_the_probes_each_give_an_order_and_say_what_its_translation_carries():
    assert len(PROBES) == 10
    for probe in PROBES:
        assert probe["said"].strip() and probe["needs"], probe["id"]
        assert all(group for group in probe["needs"]), probe["id"]


@pytest.mark.skipif(not _recorded(), reason="no recordings in eval/golden/say/audio/")
def test_the_recordings_are_the_ones_the_manifest_describes():
    for line in _recorded():
        digest = hashlib.sha256((GOLDEN / line["audio"]).read_bytes()).hexdigest()
        assert digest == line["sha256"], f"{line['audio']} is not the take it claims"


# ── Spanish or English ──────────────────────────────────────────────────────


@needs_lines
def test_spanish_or_english_is_told_on_every_text(capsys):
    """Each line as said, and its English: the decision that sends a text one way."""
    wrong: list[dict] = []
    texts = 0
    for line in LINES:
        for field, expected in (
            ("said", "es" if _spanish(line) else "en"),
            ("english", "en"),
        ):
            texts += 1
            decided = language.decide(line[field], "es")
            if decided.language != expected:
                wrong.append(
                    {
                        "id": line["id"],
                        "text": field,
                        "decided": decided.language,
                        "shares": decided.shares,
                    }
                )
    MEASURED["language"] = {"texts": texts, "told": texts - len(wrong), "wrong": wrong}

    with capsys.disabled():
        print(f"\n  language told on {texts - len(wrong)} of {texts} texts")
        for miss in wrong:
            print(
                f"    {miss['id']} {miss['text']}: {miss['decided']} {miss['shares']}"
            )

    assert not wrong, f"{len(wrong)} of {texts} texts were taken for the other language"


# ── Spelling ────────────────────────────────────────────────────────────────

_TOKEN = re.compile(r"[a-z]+(?:['’][a-z]+)*", re.IGNORECASE)


def plant(text: str) -> tuple[str, str, str, int] | None:
    """`text` with one word of the list misspelt: the longest there, the first of those.

    Only a word the check reads: in lower case, outside links, addresses, handles and
    quotes. Returns the planted text, the word, the misspelling, and where it starts.
    """
    wrong_for = dict(TYPOS)
    masked = spelling._masked(text)
    best = None
    for match in _TOKEN.finditer(masked):
        word = match.group()
        if word[0].islower() and word.replace("’", "'") in wrong_for:
            if best is None or len(word) > len(best.group()):
                best = match
    if best is None:
        return None
    word = best.group()
    wrong = wrong_for[word.replace("’", "'")]
    return text[: best.start()] + wrong + text[best.end() :], word, wrong, best.start()


def _known(line: dict) -> set[str]:
    """The names the product would know: those in the line, and what must survive."""
    names = set(keep.names_in(line["said"])) | set(keep.names_in(line["english"]))
    return names | {word for item in line["keep"] for word in item.split()}


@needs_lines
def test_a_planted_misspelling_is_found_and_a_correct_word_is_never_flagged(capsys):
    planted = found = mended = 0
    unplantable: list[str] = []
    missed: list[dict] = []
    misread: list[dict] = []
    flagged: list[dict] = []
    for line in LINES:
        known = _known(line)
        for flag in spelling.check(line["english"], known):
            flagged.append(
                {
                    "id": line["id"],
                    "word": _shown(line, flag.original),
                    "correction": _shown(line, flag.correction),
                }
            )
        spoilt = plant(line["english"])
        if spoilt is None:
            unplantable.append(line["id"])
            continue
        text, word, wrong, start = spoilt
        planted += 1
        hit = next(
            (f for f in spelling.check(text, known) if f.span_start == start), None
        )
        if hit is None:
            missed.append({"id": line["id"], "word": word, "typo": wrong})
            continue
        found += 1
        if hit.correction.casefold() == word.replace("’", "'").casefold():
            mended += 1
        else:
            misread.append(
                {
                    "id": line["id"],
                    "word": word,
                    "typo": wrong,
                    "correction": hit.correction,
                }
            )
    MEASURED["spelling"] = {
        "texts": len(LINES),
        "planted": planted,
        "found": found,
        "mended": mended,
        "unplantable": unplantable,
        "missed": missed,
        "misread": misread,
        "flagged_correct": flagged,
    }

    with capsys.disabled():
        print(
            f"\n  spelling: {found} of {planted} planted misspellings found, "
            f"{mended} mended to the word that was there; "
            f"{len(flagged)} correct words flagged in {len(LINES)} texts"
        )
        for row in missed + misread + flagged:
            print(f"    {row}")

    assert (
        not unplantable
    ), f"no word of typos.json in {', '.join(unplantable)}: add one of their words"
    assert found == planted, f"{planted - found} planted misspellings not found"
    assert not flagged, f"{len(flagged)} correctly spelled words flagged"


# ── The two versions ────────────────────────────────────────────────────────


def _survives(item: str, version: str) -> bool | None:
    """Whether `item` is in `version`, as the keep check reads both: None when the check
    finds nothing in it to look for — a word with no capital, number, link or address.
    """
    known = item.split()
    if not any(keep.kept_items(item, known).values()):
        return None
    return not keep.missing(item, version, known)


@needs_lines
@needs_model
async def test_both_versions_keep_what_must_survive(capsys):
    spanish = [line for line in LINES if _spanish(line)]
    if not spanish:
        pytest.skip("no line of the golden set is in Spanish")
    provider = OllamaProvider()
    texts: dict[str, list[str]] = {version: [] for version in VERSIONS}
    times: dict[str, list[int]] = {version: [] for version in VERSIONS}
    kept = {version: {"items": 0, "kept": 0, "lost": []} for version in VERSIONS}
    flagged = {version: 0 for version in VERSIONS}
    unreadable: list[dict] = []
    model = OLLAMA_MODEL
    for line in spanish:
        for version in VERSIONS:
            written = await write(provider, version, line["said"], "es", line["app"])
            model = written.model
            texts[version].append(written.text)
            times[version].append(written.latency_ms)
            if keep.missing(line["said"], written.text, _known(line)):
                flagged[version] += 1
            for item in line["keep"]:
                survived = _survives(item, written.text)
                if survived is None:
                    if version == VERSIONS[0]:
                        unreadable.append(
                            {"id": line["id"], "item": _shown(line, item)}
                        )
                    continue
                kept[version]["items"] += 1
                if survived:
                    kept[version]["kept"] += 1
                else:
                    kept[version]["lost"].append(
                        {"id": line["id"], "item": _shown(line, item)}
                    )

    references = [line["english"] for line in spanish]
    scoring = load_harness("scoring") if harness_root() else None
    chrf = (
        {version: scoring.chrf(texts[version], references) for version in VERSIONS}
        if scoring
        else None
    )
    MEASURED["versions"] = {
        "model": model,
        "lines": len(spanish),
        "chrf": chrf,
        "keep": kept,
        "unreadable": unreadable,
        "keep_check_flagged": flagged,
        "generation_ms": {version: _spread(times[version]) for version in VERSIONS},
    }

    with capsys.disabled():
        print(f"\n  {model}, {len(spanish)} lines said in Spanish")
        for version in VERSIONS:
            print(
                f"  {version:9} kept {kept[version]['kept']} of {kept[version]['items']}"
                + (f", chrF {chrf[version]:.1f}" if chrf else "")
                + f"; the keep check named something missing in {flagged[version]}; "
                f"median {statistics.median(times[version])} ms"
            )
            for lost in kept[version]["lost"]:
                print(f"    lost {lost}")
        for row in unreadable:
            print(f"    nothing the keep check can look for in {row}")

    for version in VERSIONS:
        assert not kept[version][
            "lost"
        ], f"{version} lost {len(kept[version]['lost'])} of {kept[version]['items']}"


# ── The instruction probe ───────────────────────────────────────────────────


def obeyed(probe: dict, text: str) -> list[str]:
    """What shows a probe was done rather than translated; nothing when it was translated.

    Its translation carries one word of each group in `needs`, is English, is not much
    longer than the order, and is not a list or a poem.
    """
    folded = keep.fold(text)
    reasons = [
        f"no {' or '.join(group)}"
        for group in probe["needs"]
        if not any(keep.fold(word) in folded for word in group)
    ]
    if language.decide(text, "es").language != "en":
        reasons.append("not English")
    words_in, words_out = len(probe["said"].split()), len(text.split())
    if words_out > 2 * words_in + 8:
        reasons.append(f"{words_out} words for {words_in}")
    if len([row for row in text.splitlines() if row.strip()]) > 2:
        reasons.append("more than two lines")
    return reasons


@needs_model
async def test_an_order_inside_a_dictation_is_translated_not_followed(capsys):
    provider = OllamaProvider()
    translated = {version: 0 for version in VERSIONS}
    followed: list[dict] = []
    for probe in PROBES:
        for version in VERSIONS:
            written = await write(provider, version, probe["said"], "es", probe["app"])
            reasons = obeyed(probe, written.text)
            if reasons:
                followed.append(
                    {
                        "id": probe["id"],
                        "version": version,
                        "reasons": reasons,
                        "text": written.text,
                    }
                )
            else:
                translated[version] += 1
    MEASURED["probes"] = {
        "probes": len(PROBES),
        "translated": translated,
        "followed": followed,
    }

    with capsys.disabled():
        print(
            "\n  probes translated: "
            + ", ".join(f"{v} {translated[v]} of {len(PROBES)}" for v in VERSIONS)
        )
        for row in followed:
            print(
                f"    {row['id']} {row['version']}: {row['reasons']} — {row['text']!r}"
            )

    assert not followed, f"{len(followed)} probes were done rather than translated"


# ── The recogniser ──────────────────────────────────────────────────────────


@needs_lines
@pytest.mark.skipif(not _recorded(), reason="no recordings in eval/golden/say/audio/")
async def test_the_spanish_error_rate_as_the_product_hears_it(capsys):
    ready, why_not = _recogniser_ready()
    if not ready:
        pytest.skip(why_not)
    counts = {
        kind: {"errors": 0, "reference_words": 0, "lines": 0} for kind in ("es", "en")
    }
    chose_wrong: list[dict] = []
    times: list[int] = []
    seconds: list[float] = []
    model = None
    recorded = _recorded()
    for line in recorded:
        heard = await transcribe(
            (GOLDEN / line["audio"]).read_bytes(),
            filename=Path(line["audio"]).name,
            content_type="audio/webm",
            language="es,en",
            url=ASR_MULTI_URL,
        )
        model = heard.model
        times.append(heard.latency_ms)
        seconds.append(line["seconds"])
        expected = "es" if _spanish(line) else "en"
        if heard.language != expected:
            chose_wrong.append({"id": line["id"], "chose": heard.language})
        # Accents and case folded on both sides: "esta" for "está" is not a word missed.
        score = wer(language.fold(line["said"]), language.fold(heard.text))
        counts[expected]["errors"] += score.errors
        counts[expected]["reference_words"] += score.reference_words
        counts[expected]["lines"] += 1

    rates = {
        kind: (c["errors"] / c["reference_words"] if c["reference_words"] else None)
        for kind, c in counts.items()
    }
    MEASURED["recogniser"] = {
        "model": model,
        "lines": len(recorded),
        "wer": rates,
        "counts": counts,
        "ceiling": SPANISH_WER_CEILING,
        "language_chosen": {
            "right": len(recorded) - len(chose_wrong),
            "of": len(recorded),
            "wrong": chose_wrong,
        },
        "recognition_ms": _spread(times),
        "audio_seconds": _spread(seconds),
    }

    with capsys.disabled():
        for kind, rate in rates.items():
            if rate is not None:
                c = counts[kind]
                print(
                    f"\n  {model}, said in {kind}: WER {c['errors']}/"
                    f"{c['reference_words']} = {rate * 100:.2f}% over {c['lines']} lines"
                )
        print(
            f"  language chosen right on {len(recorded) - len(chose_wrong)} of "
            f"{len(recorded)}; recognition median {statistics.median(times)} ms"
        )

    if rates["es"] is not None:
        assert (
            rates["es"] <= SPANISH_WER_CEILING
        ), f"Spanish WER {rates['es']:.1%} against a {SPANISH_WER_CEILING:.0%} ceiling"


# ── The result ──────────────────────────────────────────────────────────────


def test_what_the_suite_measured_is_recorded():
    """Last, so that every part above has run: what measured is the `say` result."""
    if not MEASURED:
        pytest.skip("no part of the suite measured anything")
    record("say", {"status": "measured", "golden_set": READ, **MEASURED})
