"""The seed loader.

Idempotency is the property. Seeds are real rows in a real database, loaded by a command
a human runs — after a `make clean`, after pulling a content change, sometimes twice by
accident. The second run has to be a no-op, and "no-op" has to be something the script
can *report* rather than something we assert about it from outside: `0 inserted,
0 updated` is the claim, and `_upsert` compares field by field so the claim is earned
rather than produced by an unconditional write.
"""

import json

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from db_models import Passage, Scenario
from models.passage import PassageSeed
from models.scenario import ScenarioSeed
from scripts.seed import SEEDS_DIR, _load, seed
from tests.conftest import named_database, recreate_database, upgrade


@pytest_asyncio.fixture
async def empty_session():
    """A migrated database with nothing in it.

    The suite's `speaklab_test` is seeded by whichever test ran first, so it cannot
    answer the question this file exists to ask — what the *first* run reports. A
    scratch database costs about a second and makes the answer independent of test
    order.
    """
    url = named_database("seed")
    recreate_database(url)
    upgrade(url)

    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def test_the_first_run_loads_eight_scenarios_and_twelve_passages(empty_session):
    report = await seed(empty_session)
    await empty_session.commit()

    scenarios, passages = report.tables
    assert (scenarios.inserted, scenarios.updated) == (8, 0)
    assert (passages.inserted, passages.updated) == (12, 0)

    assert await empty_session.scalar(select(func.count()).select_from(Scenario)) == 8
    assert await empty_session.scalar(select(func.count()).select_from(Passage)) == 12


async def test_the_second_run_inserts_nothing(seeded):
    """Seeding is idempotent: a second run inserts nothing."""
    report = await seed(seeded)
    await seeded.commit()

    assert report.inserted == 0
    assert report.updated == 0
    assert [t.unchanged for t in report.tables] == [8, 12]


async def test_an_edited_seed_updates_in_place_and_says_so(seeded):
    """A content edit is a diff in `seeds/`, then one `make seed`.

    Reported as an update rather than an insert, and the row keeps its id — sessions
    started against that scenario still point at it.
    """
    scenario = await seeded.scalar(
        select(Scenario).where(Scenario.slug == "daily-standup")
    )
    original_id, original_title = scenario.id, scenario.title
    scenario.title = "Something a content edit replaced"
    await seeded.commit()

    report = await seed(seeded)
    await seeded.commit()

    assert report.inserted == 0
    assert report.updated == 1

    await seeded.refresh(scenario)
    assert scenario.title == original_title
    assert scenario.id == original_id


async def test_word_count_is_derived_not_declared(seeded):
    """The seed file does not state it, so it cannot disagree with the body."""
    raw = json.loads((SEEDS_DIR / "passages.json").read_text())
    assert all("word_count" not in record for record in raw)

    passage = await seeded.scalar(
        select(Passage).where(Passage.slug == "the-rural-library")
    )
    assert passage.word_count == len(passage.body.split())


# ── The seed files as content ───────────────────────────────────────────────


def test_the_seed_files_validate_against_the_models_that_serve_them():
    """`_load` raises SystemExit with the record index and slug on a bad file. Running
    it here means a malformed seed is caught by the suite, not by the person who next
    runs `make seed`."""
    assert len(_load("scenarios.json", ScenarioSeed)) == 8
    assert len(_load("passages.json", PassageSeed)) == 12


@pytest.mark.parametrize(
    "filename,model", [("scenarios.json", ScenarioSeed), ("passages.json", PassageSeed)]
)
def test_slugs_are_unique_within_a_seed_file(filename, model):
    """A duplicate slug would load as an update of the earlier record, and the file
    would silently hold one fewer item than it appears to."""
    slugs = [record.slug for record in _load(filename, model)]

    assert len(slugs) == len(set(slugs))


def test_an_unknown_field_in_a_seed_record_is_rejected(tmp_path, monkeypatch):
    """`extra="forbid"`, which is what turns `target_gramar` from a silently dropped
    typo into a failed load."""
    bad = [
        {
            "slug": "typo",
            "title": "t",
            "description": "d",
            "category": "c",
            "cefr_band": "B1",
            "persona_prompt": "p",
            "goal": "g",
            "target_gramar": ["past_simple"],
            "target_functions": ["f"],
            "rubric": {"criteria": [{"name": "n", "descriptor": "d"}], "min_turns": 1},
        }
    ]
    (tmp_path / "scenarios.json").write_text(json.dumps(bad))
    monkeypatch.setattr("scripts.seed.SEEDS_DIR", tmp_path)

    with pytest.raises(SystemExit) as excinfo:
        _load("scenarios.json", ScenarioSeed)

    assert "typo" in str(excinfo.value)


def test_a_phoneme_focus_that_is_not_arpabet_is_rejected(tmp_path, monkeypatch):
    bad = [
        {
            "slug": "lowercase-phone",
            "title": "t",
            "body": "b",
            "cefr_band": "B1",
            "phoneme_focus": ["th"],
        }
    ]
    (tmp_path / "passages.json").write_text(json.dumps(bad))
    monkeypatch.setattr("scripts.seed.SEEDS_DIR", tmp_path)

    with pytest.raises(SystemExit) as excinfo:
        _load("passages.json", PassageSeed)

    assert "not ARPAbet" in str(excinfo.value)
