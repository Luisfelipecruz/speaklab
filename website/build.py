"""Build the project site from the repository's own Markdown.

    python website/build.py --out _site --revision "$(git rev-parse HEAD)"

The README is the home page, and every document under docs/ a page of its own, each
decision record included. Every link is checked as it is written: a link to another
document becomes a relative link to its page, so the site works at any address; a link to a
file that is not a page becomes a link to that file on GitHub, at the revision the site was
built from; and a link to a file or a heading that does not exist fails the build, as does
raw HTML that GitHub would not show. Exits 1 and names each problem.
"""

from __future__ import annotations

import argparse
import html
import os
import posixpath
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from string import Template

import markup

ROOT = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent
REPOSITORY = "Luisfelipecruz/speaklab"
REPOSITORY_URL = f"https://github.com/{REPOSITORY}"
SITE_URL = "https://luisfelipecruz.github.io/speaklab/"
SOCIAL_IMAGE = "docs/walkthrough.png"
MARKER = ".speaklab-site"
SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*:", re.IGNORECASE)
ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")

# The sidebar, in order. The decision records sit under "Decisions" and are not listed one
# by one; their index is.
FIXED = [
    ("README.md", "index.html", "Overview", "Home"),
    ("docs/how-it-works.md", "how-it-works.html", "The system", "How it works"),
    ("docs/architecture.md", "architecture.html", "The system", "Architecture"),
    ("docs/data-model.md", "data-model.html", "The system", "Data model"),
    ("docs/measurements.md", "measurements.html", "Measured", "Every measured figure"),
    ("docs/evaluation.md", "evaluation.html", "Measured", "The evaluation report"),
    ("docs/limitations.md", "limitations.html", "Measured", "What does not exist yet"),
    ("docs/decisions/", "decisions/index.html", "Project", "Decisions"),
    ("docs/changelog.md", "changelog.html", "Project", "Changelog"),
    ("CONTRIBUTING.md", "contributing.html", "Project", "Contributing"),
    ("SECURITY.md", "security.html", "Project", "Security"),
    ("CODE_OF_CONDUCT.md", "code-of-conduct.html", "Project", "Code of conduct"),
]
DECISIONS = "docs/decisions/"


@dataclass
class Page:
    source: str  # the repository path; a directory's ends in "/"
    output: str  # the path inside the site
    section: str
    label: str | None
    text: str = ""
    links_from: str = ""  # the file the text's relative links are relative to
    document: markup.Document | None = None
    hero: tuple[str, str] | None = None  # the home page's title and tagline

    @property
    def root(self) -> str:
        depth = self.output.count("/")
        return "../" * depth


@dataclass
class Result:
    pages: int = 0
    to_pages: int = 0
    to_anchors: int = 0
    to_repository: int = 0
    external: int = 0
    problems: list[str] = field(default_factory=list)


class Broken(Exception):
    pass


# ── What is in the repository ─────────────────────────────────────────────────


class Repository:
    """The files a link may name: those git tracks, or on disk where there is no git."""

    def __init__(self, root: Path):
        self.root = root
        self.files = _tracked(root)
        self.directories = (
            {folder for name in self.files for folder in _folders(name)}
            if self.files is not None
            else None
        )

    def is_file(self, path: str) -> bool:
        if self.files is not None:
            return path in self.files
        return (self.root / path).is_file()

    def is_dir(self, path: str) -> bool:
        if self.directories is not None:
            return path.rstrip("/") in self.directories
        return (self.root / path).is_dir()


def _tracked(root: Path) -> set[str] | None:
    try:
        listed = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z"],
            capture_output=True,
            check=True,
        ).stdout
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    return {name for name in listed.decode("utf-8").split("\0") if name}


def _folders(path: str) -> list[str]:
    """Every directory above a file: `a/b/c.md` gives `a` and `a/b`."""
    parts = path.split("/")[:-1]
    return ["/".join(parts[: i + 1]) for i in range(len(parts))]


# ── The pages ─────────────────────────────────────────────────────────────────


def pages(root: Path) -> list[Page]:
    found = [
        Page(source, output, section, label) for source, output, section, label in FIXED
    ]
    records = sorted((root / DECISIONS).glob("[0-9][0-9][0-9][0-9]-*.md"))
    found += [
        Page(
            f"{DECISIONS}{path.name}", f"decisions/{path.stem}.html", "Decisions", None
        )
        for path in records
    ]
    return found


def load(root: Path, page: Page, records: list[Page]) -> None:
    if page.source == DECISIONS:
        page.text = decisions_index(root, records)
        page.links_from = f"{DECISIONS}index.md"
        return
    page.text = (root / page.source).read_text(encoding="utf-8")
    page.links_from = page.source
    if page.source == "README.md":
        page.text, page.hero = split_hero(page.text)


def split_hero(readme: str) -> tuple[str, tuple[str, str] | None]:
    """Take the README's centred header off, and keep its title and tagline for the hero.

    The badges and the link row in it are GitHub's way into the page; the site has its own.
    """
    match = re.match(
        r'\s*<div align="center">\n(?P<inner>.*?)\n</div>\n', readme, re.DOTALL
    )
    if match is None:
        return readme, None
    inner = match["inner"]
    title = re.search(r"^# (.+)$", inner, re.MULTILINE)
    tagline = re.search(r"^\*\*(.+)\*\*$", inner, re.MULTILINE)
    if title is None or tagline is None:
        return readme, None
    return readme[match.end() :], (title[1].strip(), tagline[1].strip())


def decisions_index(root: Path, records: list[Page]) -> str:
    rows = []
    for record in records:
        text = (root / record.source).read_text(encoding="utf-8")
        heading = re.search(r"^# (.+)$", text, re.MULTILINE)
        number, _, title = (heading[1] if heading else record.source).partition(" — ")
        status = next(
            (p for p in text.split("\n\n") if re.match(r"\s*(\*\*)?Status:", p)),
            "",
        )
        date = ISO_DATE.search(status)
        name = posixpath.basename(record.source)
        rows.append(
            f"| {number} | [{title or number}]({name}) | {date[0] if date else ''} |"
        )
    return "\n".join(
        [
            "# Decisions",
            "",
            "Why each choice was made. A record is dated and kept as it was written: a",
            "decision that changed has a newer record that supersedes it, and says so.",
            "",
            "| | Decision | Date |",
            "|---|---|---|",
            *rows,
            "",
        ]
    )


# ── Links ─────────────────────────────────────────────────────────────────────


class Site:
    def __init__(self, repository: Repository, all_pages: list[Page], revision: str):
        self.repository = repository
        self.by_source = {page.source: page for page in all_pages}
        self.revision = revision
        self.assets: set[str] = set()

    def resolve(self, url: str, page: Page, image: bool, result: Result) -> str:
        if SCHEME.match(url) or url.startswith("//"):
            result.external += 1
            return url
        path, _, fragment = url.partition("#")
        suffix = f"#{fragment}" if fragment else ""
        if not path:
            self._require_anchor(page, fragment)
            result.to_anchors += 1
            return url

        base = posixpath.dirname(page.links_from)
        target = posixpath.normpath(posixpath.join(base, path))
        if target.startswith("../") or target == "..":
            raise Broken(f"{url}: outside the repository")
        directory = path.endswith("/") or self.repository.is_dir(target)
        key = f"{target}/" if directory else target

        destination = self.by_source.get(key)
        if destination is not None:
            if fragment:
                self._require_anchor(destination, fragment)
            result.to_pages += 1
            return relative(destination.output, page.output) + suffix

        if directory and self.repository.is_dir(target):
            result.to_repository += 1
            return f"{REPOSITORY_URL}/tree/{self.revision}/{target}{suffix}"
        if self.repository.is_file(target):
            if image:
                self.assets.add(target)
                return relative(target, page.output)
            result.to_repository += 1
            return f"{REPOSITORY_URL}/blob/{self.revision}/{target}{suffix}"
        raise Broken(f"{url}: no such file in the repository")

    @staticmethod
    def _require_anchor(page: Page, fragment: str) -> None:
        if (
            fragment
            and page.document is not None
            and fragment not in page.document.anchors
        ):
            raise Broken(f"#{fragment}: no such heading in {page.source}")


def relative(target: str, from_page: str) -> str:
    return posixpath.relpath(target, posixpath.dirname(from_page) or ".")


# ── Writing ───────────────────────────────────────────────────────────────────


def navigation(all_pages: list[Page], current: Page) -> str:
    lines = []
    section = None
    for page in all_pages:
        if page.label is None:
            continue
        if page.section != section:
            if section is not None:
                lines.append("    </ul>")
            section = page.section
            lines.append(f"    <h2>{html.escape(section)}</h2>")
            lines.append("    <ul>")
        here = page is current or (
            page.source == DECISIONS and current.section == "Decisions"
        )
        state = ' aria-current="page"' if here else ""
        href = relative(page.output, current.output)
        lines.append(
            f'      <li><a href="{href}"{state}>{html.escape(page.label)}</a></li>'
        )
    lines.append("    </ul>")
    return "\n".join(lines)


def contents(page: Page) -> str:
    assert page.document is not None
    sections = [h for h in page.document.headings if h.level == 2]
    if len(sections) < 3:
        return ""
    items = "\n".join(
        f'      <li><a href="#{html.escape(h.id)}">{html.escape(h.text)}</a></li>'
        for h in sections
    )
    return (
        '  <aside class="toc" aria-label="On this page">\n'
        "    <p>On this page</p>\n"
        f"    <ul>\n{items}\n    </ul>\n  </aside>"
    )


def pager(records: list[Page], page: Page) -> str:
    if page not in records:
        return ""
    index = records.index(page)
    parts = []
    for rel, neighbour in (("prev", index - 1), ("next", index + 1)):
        if 0 <= neighbour < len(records):
            other = records[neighbour]
            assert other.document is not None
            arrow = "←" if rel == "prev" else "→"
            text = (
                f"{arrow} {other.document.title}"
                if rel == "prev"
                else f"{other.document.title} {arrow}"
            )
            href = relative(other.output, page.output)
            parts.append(f'<a rel="{rel}" href="{href}">{html.escape(text)}</a>')
    return (
        f'    <nav class="pager" aria-label="Decision records">{"".join(parts)}</nav>'
    )


def hero(page: Page) -> str:
    if page.hero is None:
        return ""
    title, tagline = page.hero
    return f"""    <section class="hero">
      <h1>{html.escape(title)}</h1>
      <p class="tagline">{html.escape(tagline)}</p>
      <p class="actions">
        <a class="button primary" href="#quick-start">Quick start</a>
        <a class="button" href="how-it-works.html">How it works</a>
        <a class="button" href="{REPOSITORY_URL}">Source on GitHub</a>
        <a class="button" href="{REPOSITORY_URL}/releases/latest">Latest release</a>
      </p>
    </section>"""


def footer(revision: str) -> str:
    built = (
        f'Built from <a href="{REPOSITORY_URL}/commit/{revision}"><code>{revision[:7]}</code></a>'
        if re.fullmatch(r"[0-9a-f]{7,40}", revision)
        else f"Built from <code>{html.escape(revision)}</code>"
    )
    return (
        f'{built} · <a href="{REPOSITORY_URL}">Source on GitHub</a> · '
        f'<a href="{REPOSITORY_URL}/blob/main/LICENSE">MIT licence</a>'
    )


def fill(
    template: Template,
    page: Page,
    all_pages: list[Page],
    records: list[Page],
    body: str,
    revision: str,
    head_extra: str = "",
) -> str:
    assert page.document is not None
    if page.hero is not None:
        title = f"{page.hero[0]} — {page.hero[1]}"
        description = page.hero[1]
    else:
        title = f"{page.document.title or page.label} · SpeakLab"
        description = page.document.summary()
    canonical = SITE_URL if page.output == "index.html" else SITE_URL + page.output
    return template.substitute(
        title=html.escape(title),
        description=html.escape(description),
        canonical=canonical,
        og_image=SITE_URL + SOCIAL_IMAGE,
        head_extra=head_extra,
        root=page.root,
        body_class="home" if page.hero else "doc",
        releases_url=f"{REPOSITORY_URL}/releases",
        repository_url=REPOSITORY_URL,
        nav=navigation(all_pages, page),
        hero=hero(page),
        content=body,
        pager=pager(records, page),
        toc=contents(page),
        footer=footer(revision),
    )


def prepare(out: Path) -> None:
    """Empty the output directory, but only one this builder made, or an empty one."""
    if out.exists() and any(out.iterdir()):
        if not (out / MARKER).exists():
            raise SystemExit(
                f"{out} is not empty and was not written by this builder; not touching it"
            )
        # What is inside, not the directory itself, which may be a mount point.
        for child in out.iterdir():
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink()
    out.mkdir(parents=True, exist_ok=True)
    (out / MARKER).write_text("Written by website/build.py; emptied on every build.\n")


def not_found(template: Template, all_pages: list[Page], revision: str) -> str:
    md = markup.parser()
    page = Page("404", "404.html", "", None, text="# There is no page here\n")
    page.document = markup.parse(
        md, page.text + "\nThe [home page](index.html) lists every page.\n", "404"
    )
    # Served for any missing address at any depth, so its links resolve from the site root.
    return fill(
        template,
        page,
        all_pages,
        [],
        markup.render(md, page.document),
        revision,
        head_extra=f'<base href="{SITE_URL}">',
    )


def sitemap(all_pages: list[Page]) -> str:
    urls = "\n".join(
        f"  <url><loc>{SITE_URL if p.output == 'index.html' else SITE_URL + p.output}</loc></url>"
        for p in all_pages
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{urls}\n</urlset>\n"
    )


def build(root: Path, out: Path, revision: str) -> Result:
    result = Result()
    md = markup.parser()
    all_pages = pages(root)
    records = [p for p in all_pages if p.section == "Decisions"]

    for page in all_pages:
        path = root / page.source
        if page.source != DECISIONS and not path.is_file():
            result.problems.append(f"{page.source}: listed as a page, and missing")
            continue
        load(root, page, records)
        page.document = markup.parse(md, page.text, page.source)
        result.problems += page.document.problems
    all_pages = [p for p in all_pages if p.document is not None]
    records = [p for p in records if p.document is not None]

    site = Site(Repository(root), all_pages, revision)
    for page in all_pages:
        assert page.document is not None
        for link in markup.links(page.document):
            # The heading's own permalink, which the renderer wrote and nobody authored.
            if link.token.attrGet("class") == "header-anchor":
                continue
            try:
                link.point_at(site.resolve(link.url, page, link.image, result))
            except Broken as broken:
                result.problems.append(f"{page.source}:{link.line}: {broken}")
        if page.hero is not None and "quick-start" not in page.document.anchors:
            result.problems.append(
                f"{page.source}: the hero links to #quick-start, which is gone"
            )

    if result.problems:
        return result

    prepare(out)
    template = Template((HERE / "templates" / "page.html").read_text(encoding="utf-8"))
    for page in all_pages:
        assert page.document is not None
        target = out / page.output
        target.parent.mkdir(parents=True, exist_ok=True)
        body = markup.render(md, page.document)
        target.write_text(
            fill(template, page, all_pages, records, body, revision), encoding="utf-8"
        )
    (out / "404.html").write_text(
        not_found(template, all_pages, revision), encoding="utf-8"
    )
    (out / "sitemap.xml").write_text(sitemap(all_pages), encoding="utf-8")
    for name in ("style.css", "site.js", "favicon.svg"):
        shutil.copyfile(HERE / "static" / name, out / name)
    for asset in sorted(site.assets | {SOCIAL_IMAGE}):
        (out / asset).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / asset, out / asset)
    result.pages = len(all_pages)
    return result


def default_revision(root: Path) -> str:
    if os.environ.get("GITHUB_SHA"):
        return os.environ["GITHUB_SHA"]
    try:
        return subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            check=True,
            text=True,
        ).stdout.strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        return "main"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--out", type=Path, default=ROOT / "_site", help="where to write the site"
    )
    parser.add_argument(
        "--revision",
        help="the commit links to the repository point at (default: $GITHUB_SHA, then HEAD)",
    )
    args = parser.parse_args(argv)

    started = time.perf_counter()
    revision = args.revision or default_revision(ROOT)
    result = build(ROOT, args.out, revision)
    if result.problems:
        for problem in result.problems:
            print(f"build: {problem}", file=sys.stderr)
        print(
            f"build: {len(result.problems)} problem(s); nothing written",
            file=sys.stderr,
        )
        return 1
    print(
        f"{result.pages} pages · links: {result.to_pages} to pages, {result.to_anchors} to"
        f" headings on the same page, {result.to_repository} to the repository at"
        f" {revision[:12]}, {result.external} elsewhere · 0 problems ·"
        f" {time.perf_counter() - started:.2f} s → {args.out}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
