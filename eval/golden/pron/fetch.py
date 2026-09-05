"""Fetch the pronunciation probe recording.

**Unlike `eval/golden/asr/fetch.py`, this script is not optional.** The ASR golden set
commits its ten `.flac` files and that script exists to *audit* them. Here `.gitignore`
covers `*.wav` — trap 4, recordings of a human voice must never be able to appear in
`git status` — so nothing in this directory is versioned except the manifest and this
file. Running it is how the audio gets onto a machine at all.

    python3 eval/golden/pron/fetch.py [--force]

No third-party imports on purpose: this runs on a bare host with whatever Python is
installed, not inside a container.

The recorded sha256 is what makes an unversioned fixture trustworthy. If the upstream
mirror ever serves different bytes, this refuses them rather than quietly measuring
something else.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(HERE, "manifest.json")


def digest(path: str) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force", action="store_true", help="re-download even if the file verifies"
    )
    args = parser.parse_args()

    with open(MANIFEST, encoding="utf-8") as handle:
        manifest = json.load(handle)

    probe = manifest["probe"]
    target = os.path.join(HERE, probe["file"])
    expected = probe["sha256"]

    if os.path.exists(target) and not args.force:
        actual = digest(target)
        if actual == expected:
            print(f"ok       {probe['file']} ({os.path.getsize(target)} bytes)")
            return 0
        print(f"MISMATCH {probe['file']}: {actual[:12]} != {expected[:12]}, re-fetching")

    print(f"fetching {probe['source_url']}")
    try:
        with urllib.request.urlopen(probe["source_url"], timeout=60) as response:
            data = response.read()
    except Exception as exc:  # noqa: BLE001 — a fetch script says what went wrong
        print(f"FAILED   {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        # Refused rather than written. A golden set whose contents can change without
        # anybody noticing is not a golden set — every number this file supports would
        # silently start describing different audio.
        print(
            f"FAILED   sha256 mismatch: got {actual}, manifest says {expected}.\n"
            f"         The upstream mirror is serving different bytes. Do NOT update the\n"
            f"         manifest to match — work out which recording is the right one.",
            file=sys.stderr,
        )
        return 1

    with open(target, "wb") as handle:
        handle.write(data)
    print(f"wrote    {probe['file']} ({len(data)} bytes, sha256 verified)")

    if not manifest["pairs"]:
        print()
        print("The clean/broken PAIRS are still empty, so criterion S4 has nothing to")
        print("measure. They need a person: see spike/RECORD.md, about five minutes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
