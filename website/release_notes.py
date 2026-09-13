"""Cut one version's entry out of the changelog, as the notes of its release.

    python website/release_notes.py 0.17.0
    python website/release_notes.py 0.18.0 --check-version --notes-file notes.md --title-file title.txt

The notes go to stdout unless `--notes-file` names a file. Exits 1 when the changelog has no
entry for the version, and, with `--check-version`, when `api/config.py` carries a different
one — a tag pushed on the wrong commit, or a version bumped without its entry.

Standard library only, so the release workflow runs it with no install step.
"""

from __future__ import annotations

import argparse
import os
import posixpath
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHANGELOG = ROOT / "docs" / "changelog.md"
CONFIG = ROOT / "api" / "config.py"
DEFAULT_REPOSITORY = "Luisfelipecruz/speaklab"

# `## [0.17.0] — 2026-09-13 · security and dependencies`; the name after the dot is optional.
HEADING = re.compile(
    r"^## \[(?P<version>\d+\.\d+\.\d+)\] — (?P<date>\d{4}-\d{2}-\d{2})(?: · (?P<name>.+))?$"
)
VERSION_LINE = re.compile(r'^VERSION = "(?P<version>[^"]+)"$', re.MULTILINE)
LINK_TARGET = re.compile(r"\]\((?P<target>[^)\s]+)\)")
SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*:", re.IGNORECASE)


class NotesError(Exception):
    """The changelog or the code cannot produce the notes asked for."""


@dataclass(frozen=True)
class Entry:
    version: str
    date: str
    name: str | None
    body: str

    @property
    def title(self) -> str:
        return (
            f"SpeakLab {self.version} — {self.name}"
            if self.name
            else f"SpeakLab {self.version}"
        )


def entries(text: str) -> list[Entry]:
    """Every entry in the changelog, newest first, as the file orders them.

    A line that starts `## [` and does not match the heading's shape is an error rather than
    a line of the entry above it, so a malformed heading cannot swallow a release.
    """
    found: list[Entry] = []
    current: re.Match[str] | None = None
    body: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if current is not None:
                found.append(_entry(current, body))
            match = HEADING.match(line)
            if match is None and line.startswith("## ["):
                raise NotesError(
                    f"changelog heading not in the expected shape: {line!r}"
                )
            current, body = match, []
        elif current is not None:
            body.append(line)
    if current is not None:
        found.append(_entry(current, body))
    return found


def _entry(match: re.Match[str], body: list[str]) -> Entry:
    return Entry(
        version=match["version"],
        date=match["date"],
        name=match["name"],
        body="\n".join(body).strip(),
    )


def find(text: str, version: str) -> Entry:
    for entry in entries(text):
        if entry.version == version:
            return entry
    raise NotesError(f"docs/changelog.md has no entry for {version}")


def absolute_links(body: str, version: str, repository: str) -> str:
    """Point every relative link at the file it names, as of the release's tag.

    The changelog's links are relative to `docs/`, which means nothing on a release page.
    """
    base = f"https://github.com/{repository}"

    def rewrite(match: re.Match[str]) -> str:
        target = match["target"]
        if SCHEME.match(target):
            return match.group(0)
        path, _, fragment = target.partition("#")
        suffix = f"#{fragment}" if fragment else ""
        if not path:
            return f"]({base}/blob/v{version}/docs/changelog.md{suffix})"
        resolved = posixpath.normpath(posixpath.join("docs", path))
        kind = "tree" if path.endswith("/") else "blob"
        return f"]({base}/{kind}/v{version}/{resolved}{suffix})"

    return LINK_TARGET.sub(rewrite, body)


def notes(entry: Entry, repository: str) -> str:
    body = absolute_links(entry.body, entry.version, repository)
    history = f"https://github.com/{repository}/blob/v{entry.version}/docs/changelog.md"
    return f"{body}\n\n---\n\nEvery release since the first is in [the changelog]({history}).\n"


def code_version(config_text: str) -> str:
    match = VERSION_LINE.search(config_text)
    if match is None:
        raise NotesError("api/config.py has no VERSION line")
    return match["version"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("version", help="the version to release, without the v: 0.18.0")
    parser.add_argument(
        "--check-version",
        action="store_true",
        help="fail unless api/config.py carries the same version",
    )
    parser.add_argument(
        "--notes-file", type=Path, help="write the notes here, not to stdout"
    )
    parser.add_argument(
        "--title-file", type=Path, help="write the release's title here"
    )
    args = parser.parse_args(argv)

    repository = os.environ.get("GITHUB_REPOSITORY", DEFAULT_REPOSITORY)
    try:
        entry = find(CHANGELOG.read_text(encoding="utf-8"), args.version)
        if args.check_version:
            in_code = code_version(CONFIG.read_text(encoding="utf-8"))
            if in_code != args.version:
                raise NotesError(f"api/config.py says {in_code}, not {args.version}")
    except NotesError as error:
        print(f"release_notes: {error}", file=sys.stderr)
        return 1

    text = notes(entry, repository)
    if args.notes_file:
        args.notes_file.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    if args.title_file:
        args.title_file.write_text(entry.title + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
