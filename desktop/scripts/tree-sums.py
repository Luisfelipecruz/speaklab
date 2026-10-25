"""A line per file and per link under a folder, sorted by path: the file's SHA-256, or the
link's target, then the path from the folder. Two trees with the same lines hold the same
bytes and the same links.

    tree-sums.py <folder> [top-level name...]

With names, only those top-level entries are listed.
"""

import hashlib
import os
import sys


def sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    root, tops = sys.argv[1], set(sys.argv[2:])
    lines = []
    for folder, dirs, files in os.walk(root):
        here = os.path.relpath(folder, root)
        if here == "." and tops:
            dirs[:] = [d for d in dirs if d in tops]
            files = [f for f in files if f in tops]
        for name in dirs + files:
            path = os.path.join(folder, name)
            rel = os.path.normpath(os.path.join(here, name))
            if os.path.islink(path):
                lines.append(f"link:{os.readlink(path)}  {rel}")
            elif name in files:
                lines.append(f"{sha256(path)}  {rel}")
    for line in sorted(lines, key=lambda entry: entry.split("  ", 1)[1]):
        print(line)


if __name__ == "__main__":
    main()
