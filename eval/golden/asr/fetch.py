"""Rebuild the ASR golden set from LibriSpeech test-clean.

The audio is committed, so this script is not needed to run the evaluation — it is
needed to *audit* it. Anyone can re-run it and get byte-identical files, because the
row indices below are pinned and `manifest.json` records the sha256 of every file it
produced. That is the difference between a fixture you trust and a fixture you found.

Why LibriSpeech and not the recordings in `spike/audio/`: those are macOS `say` output,
and m0 established that instrument is degenerate (`spike/gop-feasibility.md` §3 — two
takes saying different words decoded to an identical phone string). A WER measured on
synthetic speech would be a flattering number about nothing. LibriSpeech test-clean is
read speech from real people, with references verified by the corpus authors.

What this set is NOT: representative of the users of this product. It is native,
adult, fluent, read-aloud English recorded in good conditions. It measures the
recogniser's *floor* — the error rate below which nothing that follows can be blamed
on the model. Learner speech will be worse, and the honest number for that needs
learner recordings; `spike/RECORD.md` is the first five minutes of that work and m11 is
where it becomes a suite.

    python3 eval/golden/asr/fetch.py [--force]

No third-party imports on purpose: this runs on a bare host with whatever Python is
installed, not inside the API image.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent

DATASET = "openslr/librispeech_asr"
CONFIG = "clean"
SPLIT = "test"
ROWS_ENDPOINT = "https://datasets-server.huggingface.co/rows"

# Ten utterances, ten different speakers, 13-31 words each so the set spans the range of
# turn lengths this product will see. Pinned by row index rather than by a filter, so
# the set cannot silently change when the dataset viewer re-shuffles or the corpus is
# re-uploaded; `manifest.json` carries the sha256 that proves it did not.
ROW_INDICES = [4, 300, 601, 905, 1200, 1503, 1803, 2105, 2404, 2551]

LICENCE = "CC BY 4.0"
ATTRIBUTION = (
    "LibriSpeech ASR corpus (Panayotov, Chen, Povey, Khudanpur, ICASSP 2015), "
    "test-clean split, http://www.openslr.org/12"
)


def flac_duration_s(data: bytes) -> float:
    """Read total samples and sample rate out of a FLAC STREAMINFO block.

    Hand-parsed rather than pulled from soundfile: this script has to run on a host
    with no virtualenv, and STREAMINFO is a fixed 34-byte layout that has not changed
    since 2004. The fields wanted are packed across byte boundaries — 20 bits of sample
    rate, 3 of channels, 5 of bit depth, 36 of total samples — so the whole run is read
    as one integer and sliced with shifts.
    """
    if data[:4] != b"fLaC":
        raise ValueError("not a FLAC file")
    # 4-byte metadata block header, then the 34-byte STREAMINFO payload.
    block = data[8 : 8 + 34]
    packed = int.from_bytes(block[10:18], "big")  # 64 bits covering the four fields
    sample_rate = packed >> 44
    total_samples = packed & ((1 << 36) - 1)
    if not sample_rate:
        raise ValueError("FLAC header declares a zero sample rate")
    return total_samples / sample_rate


def fetch_row(index: int) -> dict:
    query = urllib.parse.urlencode(
        {
            "dataset": DATASET,
            "config": CONFIG,
            "split": SPLIT,
            "offset": index,
            "length": 1,
        }
    )
    with urllib.request.urlopen(f"{ROWS_ENDPOINT}?{query}", timeout=60) as response:
        payload = json.load(response)
    rows = payload.get("rows") or []
    if not rows:
        raise RuntimeError(f"row {index} came back empty")
    return rows[0]["row"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="re-download even when the local file already matches the manifest",
    )
    args = parser.parse_args()

    existing = {}
    manifest_path = HERE / "manifest.json"
    if manifest_path.exists():
        existing = {
            item["id"]: item for item in json.loads(manifest_path.read_text())["items"]
        }

    items = []
    for index in ROW_INDICES:
        row = fetch_row(index)
        utterance_id = row["id"]
        target = HERE / f"{utterance_id}.flac"
        known = existing.get(utterance_id)

        if target.exists() and known and not args.force:
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            if digest == known["sha256"]:
                print(f"  ok    {utterance_id}  (unchanged)")
                items.append(known)
                continue
            print(
                f"  STALE {utterance_id}  sha256 differs from the manifest",
                file=sys.stderr,
            )

        # The dataset viewer serves audio from a signed, expiring URL, which is why the
        # metadata is re-fetched on every run rather than cached alongside the manifest.
        source_url = row["audio"][0]["src"]
        with urllib.request.urlopen(source_url, timeout=120) as response:
            audio = response.read()
        target.write_bytes(audio)

        item = {
            "id": utterance_id,
            "file": target.name,
            "row_index": index,
            "speaker_id": row["speaker_id"],
            # LibriSpeech transcripts are upper-case and unpunctuated. They are stored
            # exactly as the corpus has them; normalisation for scoring belongs to the
            # scorer, where it is visible, not to the fixture, where it would be baked in.
            "text": row["text"],
            "duration_s": round(flac_duration_s(audio), 3),
            "sha256": hashlib.sha256(audio).hexdigest(),
        }
        items.append(item)
        print(
            f"  saved {utterance_id}  {item['duration_s']:>6.2f}s  {len(audio):>7,} bytes"
        )

    manifest = {
        "dataset": DATASET,
        "config": CONFIG,
        "split": SPLIT,
        "licence": LICENCE,
        "attribution": ATTRIBUTION,
        "generated_by": "eval/golden/asr/fetch.py",
        "items": items,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    total = sum(item["duration_s"] for item in items)
    speakers = len({item["speaker_id"] for item in items})
    print(f"\n{len(items)} utterances, {speakers} speakers, {total:.1f}s of audio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
