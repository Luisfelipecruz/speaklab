import pytest

import release_notes
from release_notes import CHANGELOG, CONFIG, NotesError

REPOSITORY = "owner/project"

SAMPLE = """# Changelog

Intro, not part of any entry.

---

## [1.2.0] — 2026-09-20 · the second

Links: [a record](decisions/0001-a.md), [the readme](../README.md#quick-start),
[a folder](decisions/), [here](#older), [outside](https://example.com/x),
[mail](mailto:someone@example.com).

### Added

- A thing.

## [1.1.0] — 2026-09-10

The first, with no name.
"""


def test_each_entry_is_found_with_its_heading():
    found = release_notes.entries(SAMPLE)

    assert [(e.version, e.date, e.name) for e in found] == [
        ("1.2.0", "2026-09-20", "the second"),
        ("1.1.0", "2026-09-10", None),
    ]
    assert found[0].body.endswith("- A thing.")
    assert "Intro" not in found[0].body
    assert "The first" not in found[0].body


def test_the_title_carries_the_name_when_there_is_one():
    assert release_notes.find(SAMPLE, "1.2.0").title == "SpeakLab 1.2.0 — the second"
    assert release_notes.find(SAMPLE, "1.1.0").title == "SpeakLab 1.1.0"


def test_relative_links_point_at_the_tag():
    body = release_notes.notes(release_notes.find(SAMPLE, "1.2.0"), REPOSITORY)
    base = "https://github.com/owner/project"

    assert f"({base}/blob/v1.2.0/docs/decisions/0001-a.md)" in body
    assert f"({base}/blob/v1.2.0/README.md#quick-start)" in body
    assert f"({base}/tree/v1.2.0/docs/decisions)" in body
    assert f"({base}/blob/v1.2.0/docs/changelog.md#older)" in body
    assert "(https://example.com/x)" in body
    assert "(mailto:someone@example.com)" in body
    assert body.rstrip().endswith(f"({base}/blob/v1.2.0/docs/changelog.md).")


def test_a_version_without_an_entry_is_an_error():
    with pytest.raises(NotesError, match="no entry for 9.9.9"):
        release_notes.find(SAMPLE, "9.9.9")


def test_a_malformed_heading_is_an_error_not_part_of_the_entry_above():
    broken = SAMPLE.replace("## [1.1.0] — 2026-09-10", "## [1.1.0] - 2026-09-10")

    with pytest.raises(NotesError, match="expected shape"):
        release_notes.entries(broken)


def test_every_heading_in_the_real_changelog_parses():
    text = CHANGELOG.read_text(encoding="utf-8")
    found = release_notes.entries(text)

    assert len(found) == text.count("\n## [")
    assert len({e.version for e in found}) == len(found)


def test_the_version_in_the_code_has_its_entry():
    # A version bumped without a changelog entry fails here, before a tag could be pushed.
    version = release_notes.code_version(CONFIG.read_text(encoding="utf-8"))

    entry = release_notes.find(CHANGELOG.read_text(encoding="utf-8"), version)

    assert entry.body


def test_the_command_fails_on_a_version_the_code_does_not_carry(capsys):
    in_code = release_notes.code_version(CONFIG.read_text(encoding="utf-8"))
    other = next(
        e.version
        for e in release_notes.entries(CHANGELOG.read_text(encoding="utf-8"))
        if e.version != in_code
    )

    assert release_notes.main([other, "--check-version"]) == 1
    assert f"says {in_code}, not {other}" in capsys.readouterr().err


def test_the_command_writes_the_notes_and_the_title(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", REPOSITORY)
    in_code = release_notes.code_version(CONFIG.read_text(encoding="utf-8"))
    notes_file, title_file = tmp_path / "notes.md", tmp_path / "title.txt"

    status = release_notes.main(
        [
            in_code,
            "--check-version",
            "--notes-file",
            str(notes_file),
            "--title-file",
            str(title_file),
        ]
    )

    assert status == 0
    assert title_file.read_text(encoding="utf-8").startswith(f"SpeakLab {in_code}")
    assert f"https://github.com/{REPOSITORY}/blob/v{in_code}/docs/changelog.md" in (
        notes_file.read_text(encoding="utf-8")
    )
