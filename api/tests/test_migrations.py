"""The migration is the schema. These tests are what make that claim checkable.

Three properties, on a scratch database of their own so nothing here can disturb the
suite's seeded one:

1. **`upgrade head` builds all twelve tables** and every enum type.
2. **`downgrade base` removes all of it**, types included. A downgrade that leaves an
   enum behind fails on the *next* upgrade, minutes later, as `type already exists` —
   so up, down and up again is run in one test.
3. **The ORM and the migration describe the same database.** Alembic's own
   `compare_metadata` against a migrated database must return an empty diff. This is
   the one that earns its keep: it is the check that catches a column added to a model
   and never migrated, which otherwise surfaces as an `UndefinedColumn` error in
   production code that was green in CI.
"""

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from db_models import Base
from tests.conftest import (
    downgrade,
    named_database,
    recreate_database,
    sync_url,
    upgrade,
)

# Spelled out rather than derived from Base.metadata — deriving it would make this
# assertion true by construction and it would stop being a test.
EXPECTED_TABLES = {
    "attempts",
    "audio_assets",
    "fluency_metrics",
    "grammar_usage",
    "language_errors",
    "passages",
    "phoneme_scores",
    "progress_snapshots",
    "scenarios",
    "sessions",
    "turns",
    "users",
}

EXPECTED_ENUMS = {
    "analysis_status",
    "attempt_status",
    "session_mode",
    "session_status",
}


@pytest.fixture
def scratch():
    """An empty database this test owns.

    Separate from `speaklab_test` because these tests downgrade to base, and the suite's
    other tests expect a schema with rows in it. Recreated per test, which costs about
    a second and removes any ordering dependence between them.
    """
    url = named_database("migrations")
    recreate_database(url)
    yield url


def _tables(url) -> set[str]:
    engine = create_engine(sync_url(url))
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def _enums(url) -> set[str]:
    engine = create_engine(sync_url(url))
    try:
        with engine.connect() as conn:
            return {
                row[0]
                for row in conn.exec_driver_sql(
                    "SELECT t.typname FROM pg_type t "
                    "JOIN pg_namespace n ON n.oid = t.typnamespace "
                    "WHERE n.nspname = 'public' AND t.typtype = 'e'"
                )
            }
    finally:
        engine.dispose()


def test_upgrade_head_creates_the_twelve_tables(scratch):
    upgrade(scratch)

    # alembic_version is Alembic's own bookkeeping, not part of the data model.
    assert _tables(scratch) - {"alembic_version"} == EXPECTED_TABLES
    assert _enums(scratch) == EXPECTED_ENUMS


def test_downgrade_removes_everything_including_the_enum_types(scratch):
    upgrade(scratch)
    downgrade(scratch)

    assert _tables(scratch) - {"alembic_version"} == set()
    assert _enums(scratch) == set(), (
        "a type survived the downgrade — the next upgrade will fail with "
        "'type already exists', long after the mistake was made"
    )


def test_the_migration_can_be_run_again_after_a_downgrade(scratch):
    upgrade(scratch)
    downgrade(scratch)
    upgrade(scratch)

    assert _tables(scratch) - {"alembic_version"} == EXPECTED_TABLES


def test_the_orm_and_the_migrated_schema_do_not_disagree(scratch):
    """An empty diff, or the diff itself in the failure message.

    `compare_type` and `compare_server_default` are on because without them a changed
    column type reads as no change at all, and the check would pass on a schema it
    could not actually detect drift in.
    """
    upgrade(scratch)

    engine = create_engine(sync_url(scratch))
    try:
        with engine.connect() as conn:
            context = MigrationContext.configure(
                conn,
                opts={"compare_type": True, "compare_server_default": True},
            )
            diff = compare_metadata(context, Base.metadata)
    finally:
        engine.dispose()

    assert (
        diff == []
    ), "db_models/ and alembic/versions/ describe different databases:\n" + "\n".join(
        f"  {entry}" for entry in diff
    )
