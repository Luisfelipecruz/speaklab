"""Every piece of native English the repository carries, for the rule layer to be held to.

The reading passages and the persona briefs were written for this project; the LibriSpeech
references are read speech; the persona calibration replies are what the conversation model
says in character. None of it is a learner's, so a rule that proposes an error anywhere in
it has proposed a false one — or has found a typo, which is worth knowing too.

Shared by `test_rules.py`, which asserts the layer finds nothing here, and by
`test_error_precision.py`, which plants errors in it and counts what comes back.
"""

from __future__ import annotations

import json
from pathlib import Path

from tests.eval_out import harness_root

SEEDS = Path(__file__).resolve().parents[1] / "seeds"


def native_texts() -> list[tuple[str, str]]:
    """(where it came from, the text), in a fixed order."""
    texts: list[tuple[str, str]] = []
    for passage in json.loads((SEEDS / "passages.json").read_text()):
        texts.append((f"passage {passage['slug']}", passage["body"]))
    for scenario in json.loads((SEEDS / "scenarios.json").read_text()):
        for field in ("description", "persona_prompt", "goal"):
            texts.append((f"scenario {scenario['slug']} {field}", scenario[field]))

    root = harness_root()
    if root is not None:
        asr = root / "golden" / "asr" / "manifest.json"
        if asr.is_file():
            for item in json.loads(asr.read_text())["items"]:
                # The references are upper case. Lowered, they have the shape of
                # recogniser output: no capitals the speaker did not produce.
                texts.append((f"librispeech {item['id']}", item["text"].lower()))
        personas = root / "golden" / "personas" / "manifest.json"
        if personas.is_file():
            for item in json.loads(personas.read_text())["calibration"]:
                texts.append((f"persona reply {item['id']}", item["reply"]))
    return texts
