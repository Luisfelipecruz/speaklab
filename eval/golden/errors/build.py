"""Resolve the hand-written labels into a manifest with spans, from the stored turns.

`labels.json` is written by a person reading transcripts, and it quotes text rather than
counting characters — quoting is what a reader can check, and an offset is not. This
script turns those quotes into offsets against the transcript the database actually holds,
and **fails loudly** if a quote is missing from its turn or appears in it twice. A gold
label that silently attached itself to the wrong occurrence would make every precision
figure measured against it meaningless.

A manifest is self-contained — transcript, word timings and resolved spans — so the
evaluation runs from a clone without a database.

**Two manifests, because a golden set made of real speech is somebody's real speech.**
`labels.json` covers the turns that can be published: a role-play about viewing a flat,
and one closing line. `labels.local.json` covers the rest, which is a person talking about
their actual job, and it is not in this repository. When it is present this writes
`manifest.local.json` as well — the union, the larger set, and the one the measurement
suite prefers. When it is absent the public manifest is the whole set and everything still
runs, on fewer turns.

    python3 eval/golden/errors/build.py                     # from the running database
    python3 eval/golden/errors/build.py --turns dump.json   # from an export

The second form takes the rows of `select id, transcript, words, ... from turns` as JSON,
and exists so the resolver can be exercised without the stack up.
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "api"))

from services.taxonomy import AMBIGUOUS, TAXONOMY, locate  # noqa: E402


def load_turns(source: str | None) -> dict[int, dict]:
    if source:
        rows = json.loads(pathlib.Path(source).read_text())
    else:
        rows = _from_database()
    return {int(row["id"]): row for row in rows}


def _from_database() -> list[dict]:
    from sqlalchemy import create_engine, text

    from config import SYNC_DATABASE_URL

    engine = create_engine(SYNC_DATABASE_URL)
    query = text(
        """
        select t.id, t.session_id, t.idx, t.transcript, t.words, t.asr_confidence,
               sc.slug as scenario
        from turns t
        join sessions s on s.id = t.session_id
        left join scenarios sc on sc.id = s.scenario_id
        where t.role = 'user'
        order by t.id
        """
    )
    with engine.connect() as conn:
        return [dict(row._mapping) for row in conn.execute(query)]


def build(labels: dict, turns: dict[int, dict]) -> dict:
    items = []
    problems = []

    for turn_id_text, entries in labels["turns"].items():
        turn_id = int(turn_id_text)
        turn = turns.get(turn_id)
        if turn is None:
            problems.append(f"turn {turn_id} is labelled but not in the corpus")
            continue

        transcript = turn["transcript"]
        resolved = []
        for entry in entries:
            category = entry["category"]
            subcategory = entry.get("subcategory")
            if category not in TAXONOMY:
                problems.append(f"turn {turn_id}: {category} is not in the taxonomy")
            elif subcategory is not None and subcategory not in TAXONOMY[category]:
                problems.append(
                    f"turn {turn_id}: {category}/{subcategory} is not in the taxonomy"
                )

            span = locate(entry["quote"], transcript)
            if span is None:
                problems.append(f"turn {turn_id}: quote not found: {entry['quote']!r}")
                continue
            if span == AMBIGUOUS:
                problems.append(
                    f"turn {turn_id}: quote appears more than once: {entry['quote']!r}"
                )
                continue

            start, end = span
            resolved.append(
                {
                    "kind": entry["kind"],
                    "category": category,
                    "subcategory": subcategory,
                    "span_start": start,
                    "span_end": end,
                    "original": transcript[start:end],
                    "correction": entry["correction"],
                    "note": entry.get("note"),
                }
            )

        items.append(
            {
                "turn_id": turn_id,
                "session_id": turn["session_id"],
                "idx": turn["idx"],
                "scenario": turn["scenario"],
                "asr_confidence": round(float(turn["asr_confidence"]), 4),
                "transcript": transcript,
                "words": turn["words"],
                "labels": resolved,
            }
        )

    if problems:
        raise SystemExit("labels do not resolve:\n  " + "\n  ".join(problems))

    counts: dict[str, int] = {}
    for item in items:
        for label in item["labels"]:
            counts[label["kind"]] = counts.get(label["kind"], 0) + 1

    return {
        "written": labels["written"],
        "labelled_by": labels["labelled_by"],
        "kinds": labels["kinds"],
        "turn_count": len(items),
        "word_count": sum(len(item["words"]) for item in items),
        "label_counts": counts,
        "items": sorted(items, key=lambda item: item["turn_id"]),
    }


def write(labels: dict, turns: dict, name: str) -> dict:
    manifest = build(labels, turns)
    (HERE / name).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    )
    low = sum(
        1
        for item in manifest["items"]
        for word in item["words"]
        if math.exp(word["logprob"]) < 0.60
    )
    print(
        f"{name}: {manifest['turn_count']} turns, {manifest['word_count']} words, "
        f"{manifest['label_counts']}, {low} words under the 0.60 gate"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--turns", help="a JSON export of the user turns")
    args = parser.parse_args()

    turns = load_turns(args.turns)
    public = json.loads((HERE / "labels.json").read_text())
    write(public, turns, "manifest.json")

    private = HERE / "labels.local.json"
    if not private.is_file():
        print("no labels.local.json; the public set is the whole set here")
        return

    held_back = json.loads(private.read_text())
    merged = dict(public)
    merged["turns"] = {**public["turns"], **held_back["turns"]}
    write(merged, turns, "manifest.local.json")


if __name__ == "__main__":
    main()
