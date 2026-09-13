import re
from pathlib import Path

import pytest

import build
from build import FIXED, REPOSITORY_URL, ROOT

REVISION = "0123456789abcdef0123456789abcdef01234567"


# ── The repository as it is ───────────────────────────────────────────────────


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    out = tmp_path_factory.mktemp("site")
    return out, build.build(ROOT, out, REVISION)


def pages_in(out: Path) -> list[Path]:
    return sorted(p for p in out.rglob("*.html") if p.name != "404.html")


def test_the_repository_builds_with_no_problems(site):
    out, result = site

    assert result.problems == []
    assert result.pages == len(build.pages(ROOT))


def test_every_page_and_asset_is_written(site):
    out, _ = site

    for page in build.pages(ROOT):
        assert (out / page.output).is_file(), page.output
    for name in ("style.css", "site.js", "favicon.svg", "404.html", "sitemap.xml"):
        assert (out / name).is_file(), name
    assert (out / "docs" / "walkthrough.png").is_file()


def test_no_link_depends_on_the_address_the_site_is_served_from(site):
    # Pages serves the site under /speaklab/, a preview serves it at /. Only relative links
    # work at both, so nothing may start with a slash.
    out, _ = site

    for page in pages_in(out):
        text = page.read_text(encoding="utf-8")
        assert not re.search(r'(?:href|src)="/(?!/)', text), page


def test_every_page_has_exactly_one_title(site):
    out, _ = site

    for page in pages_in(out):
        assert page.read_text(encoding="utf-8").count("<h1") == 1, page


def test_the_home_page_leads_with_the_readme_and_leaves_githubs_badges_behind(site):
    out, _ = site
    home = (out / "index.html").read_text(encoding="utf-8")
    tagline = re.search(
        r"^\*\*(.+)\*\*$", (ROOT / "README.md").read_text(), re.MULTILINE
    )[1]

    assert f'<p class="tagline">{tagline}</p>' in home
    assert "img.shields.io" not in home
    assert '<pre class="mermaid">' in home
    assert 'id="quick-start"' in home


def test_a_file_that_is_not_a_page_is_linked_on_github_at_the_revision(site):
    out, _ = site
    home = (out / "index.html").read_text(encoding="utf-8")

    assert f'href="{REPOSITORY_URL}/blob/{REVISION}/LICENSE"' in home
    assert 'href="decisions/index.html"' in home
    assert 'href="how-it-works.html"' in home


def test_the_decisions_index_lists_every_record_and_each_links_to_its_neighbours(site):
    out, _ = site
    records = sorted((ROOT / "docs" / "decisions").glob("[0-9][0-9][0-9][0-9]-*.md"))
    index = (out / "decisions" / "index.html").read_text(encoding="utf-8")

    listed = re.findall(r'href="(\d{4}-[a-z0-9-]+\.html)"', index)
    assert listed == [f"{p.stem}.html" for p in records]

    second = (out / "decisions" / f"{records[1].stem}.html").read_text(encoding="utf-8")
    assert 'rel="prev"' in second and 'rel="next"' in second
    assert 'href="../how-it-works.html"' in second
    assert 'aria-current="page">Decisions<' in second


def test_the_sidebar_marks_the_page_it_is_on(site):
    out, _ = site
    page = (out / "measurements.html").read_text(encoding="utf-8")

    assert page.count('aria-current="page"') == 1
    assert 'href="measurements.html" aria-current="page"' in page


# ── A repository made for the test ────────────────────────────────────────────


def repository(tmp_path: Path, files: dict[str, str]) -> Path:
    root = tmp_path / "repo"
    for source, _, _, label in FIXED:
        if not source.endswith("/"):
            path = root / source
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"# {label}\n\n## Quick start\n\n## X\n", encoding="utf-8")
    (root / "docs" / "decisions").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "decisions" / "0001-first.md").write_text(
        "# 0001 — First\n\nStatus: accepted · 2026-01-02\n", encoding="utf-8"
    )
    (root / "docs" / "walkthrough.png").write_bytes(b"\x89PNG")
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def test_a_link_to_a_missing_file_fails_the_build_and_writes_nothing(tmp_path):
    root = repository(
        tmp_path, {"README.md": "# R\n\n## Quick start\n\nSee [gone](docs/gone.md).\n"}
    )
    out = tmp_path / "out"

    result = build.build(root, out, REVISION)

    assert result.problems == [
        "README.md:5: docs/gone.md: no such file in the repository"
    ]
    assert not out.exists()


def test_a_link_to_a_missing_heading_fails_the_build(tmp_path):
    root = repository(
        tmp_path,
        {
            "README.md": "# R\n\n## Quick start\n\n[there](docs/how-it-works.md#nowhere) [here](#nor-here)\n",
        },
    )

    result = build.build(root, tmp_path / "out", REVISION)

    assert result.problems == [
        "README.md:5: #nowhere: no such heading in docs/how-it-works.md",
        "README.md:5: #nor-here: no such heading in README.md",
    ]


def test_raw_html_github_would_not_show_fails_the_build(tmp_path):
    root = repository(
        tmp_path, {"docs/limitations.md": "# L\n\n<audio src=x></audio>\n"}
    )

    result = build.build(root, tmp_path / "out", REVISION)

    assert result.problems == [
        "docs/limitations.md:3: raw HTML <audio> is not allowed",
        "docs/limitations.md:3: raw HTML <audio> is not allowed",
    ]


def test_links_between_pages_are_relative_to_where_each_page_is(tmp_path):
    root = repository(
        tmp_path,
        {
            "docs/decisions/0002-second.md": (
                "# 0002 — Second\n\n[how](../how-it-works.md#x) [first](0001-first.md) "
                "[plan](../../eval/golden/) ![image](../walkthrough.png)\n"
            ),
            "eval/golden/manifest.json": "{}",
        },
    )
    out = tmp_path / "out"

    result = build.build(root, out, REVISION)

    assert result.problems == []
    page = (out / "decisions" / "0002-second.html").read_text(encoding="utf-8")
    assert 'href="../how-it-works.html#x"' in page
    assert 'href="0001-first.html"' in page
    assert f'href="{REPOSITORY_URL}/tree/{REVISION}/eval/golden"' in page
    assert 'src="../docs/walkthrough.png"' in page


def test_a_link_outside_the_repository_fails_the_build(tmp_path):
    root = repository(
        tmp_path, {"docs/data-model.md": "# D\n\n[up](../../elsewhere.md)\n"}
    )

    result = build.build(root, tmp_path / "out", REVISION)

    assert result.problems == [
        "docs/data-model.md:3: ../../elsewhere.md: outside the repository"
    ]


def test_a_directory_it_did_not_write_is_never_emptied(tmp_path):
    root = repository(tmp_path, {})
    out = tmp_path / "out"
    out.mkdir()
    (out / "precious.txt").write_text("keep me")

    with pytest.raises(SystemExit, match="not written by this builder"):
        build.build(root, out, REVISION)
    assert (out / "precious.txt").read_text() == "keep me"


def test_a_second_build_replaces_the_first(tmp_path):
    root = repository(tmp_path, {})
    out = tmp_path / "out"

    assert build.build(root, out, REVISION).problems == []
    (out / "stale.html").write_text("old")
    assert build.build(root, out, REVISION).problems == []

    assert not (out / "stale.html").exists()
    assert (out / "index.html").is_file()
