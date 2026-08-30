"""Load `seeds/*.json` into the database. Idempotent, by slug.

Scenarios and passages are **seeded data, not fixtures**: real rows a user browses and
starts sessions against, versioned as JSON so a content edit is a reviewable diff rather
than an UPDATE somebody ran once. The slug is the key, so the second run of this script
inserts nothing — which is what makes it safe to put in front of `make up` in a README
and safe to run in CI.

Three outcomes per record, reported separately, because they are three different facts:

    inserted   the slug was not there
    updated    the slug was there and something about the content changed
    unchanged  the slug was there and every field already matched

Only the third makes a second run a no-op, and only reporting them apart makes that
visible. A script that printed "8 scenarios loaded" both times would be telling the
truth in a way that hides the thing worth knowing.

Every record is validated through the same Pydantic models the API serves before
anything touches the database, so a typo in a seed file fails here, naming the field,
rather than at request time as a 500.
"""

import asyncio
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db_models import Passage, Scenario
from models.passage import PassageSeed, word_count
from models.scenario import ScenarioSeed

# api/seeds/, resolved from this file rather than from the working directory.
#
# The seeds live under api/ rather than at the repository root so that this one path
# resolves identically in all three places the loader runs: the container, where api/ is
# /app; CI, which runs from the api/ directory; and a host shell. A root-level seeds/
# would need a bind mount in one of them and a different relative path in another, and
# the day those disagree the seed loads an empty directory and reports success. D20.
SEEDS_DIR = Path(__file__).resolve().parent.parent / "seeds"


@dataclass
class TableReport:
    table: str
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0

    @property
    def total(self) -> int:
        return self.inserted + self.updated + self.unchanged

    def __str__(self) -> str:
        return (
            f"{self.table:<10} {self.total:>3} records  "
            f"{self.inserted:>3} inserted  {self.updated:>3} updated  "
            f"{self.unchanged:>3} unchanged"
        )


@dataclass
class SeedReport:
    tables: list[TableReport] = field(default_factory=list)

    @property
    def inserted(self) -> int:
        return sum(t.inserted for t in self.tables)

    @property
    def updated(self) -> int:
        return sum(t.updated for t in self.tables)

    def __str__(self) -> str:
        return "\n".join(str(t) for t in self.tables)


def _load(filename: str, model: type) -> list[Any]:
    """Read one seed file and validate every record in it.

    The error message carries the index and the slug, because "1 validation error for
    ScenarioSeed" on its own is useless against a file with eight records in it.
    """
    path = SEEDS_DIR / filename
    records = json.loads(path.read_text())
    validated = []
    for index, raw in enumerate(records):
        try:
            validated.append(model(**raw))
        except ValidationError as exc:
            slug = raw.get("slug", "<no slug>")
            raise SystemExit(
                f"{path}: record {index} ({slug}) is invalid:\n{exc}"
            ) from exc

    slugs = [record.slug for record in validated]
    duplicates = {slug for slug in slugs if slugs.count(slug) > 1}
    if duplicates:
        # Without this the load would "succeed": the second record with a given slug
        # would be an update of the first, and the file would silently hold one fewer
        # scenario than it appears to.
        raise SystemExit(f"{path}: duplicate slugs {sorted(duplicates)}")

    return validated


async def _upsert(
    session: AsyncSession, model: type, rows: list[dict[str, Any]], report: TableReport
) -> None:
    """Insert or update by slug, counting which of the three things happened.

    Field-by-field comparison rather than a blind UPDATE, because "updated: 0" is the
    claim this script exists to be able to make, and an unconditional write would make
    every run report eight updates and prove nothing.
    """
    existing = {row.slug: row for row in (await session.scalars(select(model))).all()}

    for values in rows:
        row = existing.get(values["slug"])

        if row is None:
            session.add(model(**values))
            report.inserted += 1
            continue

        changed = [k for k, v in values.items() if getattr(row, k) != v]
        if not changed:
            report.unchanged += 1
            continue

        for key in changed:
            setattr(row, key, values[key])
        report.updated += 1


async def seed(session: AsyncSession) -> SeedReport:
    """Load both files into `session`. The caller owns the transaction.

    Taking a session rather than opening one is what lets the test suite run this
    against its own scratch database, and what lets a future `seed --dry-run` roll back
    instead of needing a second code path.
    """
    scenario_rows = [
        r.model_dump(mode="json") for r in _load("scenarios.json", ScenarioSeed)
    ]

    # word_count is derived here rather than stated in the JSON, so the file cannot
    # disagree with itself. models/passage.py explains what a word is taken to be.
    passage_rows = []
    for record in _load("passages.json", PassageSeed):
        values = record.model_dump(mode="json")
        values["word_count"] = word_count(record.body)
        passage_rows.append(values)

    scenario_report = TableReport("scenarios")
    passage_report = TableReport("passages")

    await _upsert(session, Scenario, scenario_rows, scenario_report)
    await _upsert(session, Passage, passage_rows, passage_report)
    await session.flush()

    return SeedReport([scenario_report, passage_report])


async def main() -> int:
    from database import async_session, engine

    async with async_session() as session:
        report = await seed(session)
        await session.commit()
    await engine.dispose()

    print(report)
    if report.inserted == 0 and report.updated == 0:
        print("nothing to do — the database already matches seeds/")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
