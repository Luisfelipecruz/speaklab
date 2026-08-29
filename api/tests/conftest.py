"""Shared fixtures.

The client is an in-process ASGI transport, not a network call to a running container.
That is what makes `make test` a test of *this* code rather than of whatever happens to
be listening on port 8002.

From m2 the suite also needs a schema, and it builds it **with Alembic** — not with
`Base.metadata.create_all`. Those are two different things: `create_all` builds what the
ORM currently says, and the migration builds what will actually be applied to the
database people run. A suite that tests the first is green while the second is broken,
which is the failure mode most worth not having. It costs one `alembic upgrade head` per
session, about a second.

The database is dropped and recreated at the start of every run, so a test never sees a
row left behind by the last one. It is a separate database — `speaklab_test` beside
`speaklab` — because a suite that truncates tables in the development database is a
suite nobody runs twice.
"""

import os
import sys
from collections.abc import AsyncGenerator, Iterator

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# The api/ directory itself is the import root — `from config import ...`, not
# `from api.config import ...` — because that is what it is inside the container, where
# api/ is mounted at /app. Keeping the two identical means a test that passes here
# passes there.
API_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, API_ROOT)

from config import DATABASE_URL  # noqa: E402
from database import engine, get_db  # noqa: E402
from main import app  # noqa: E402
from scripts.seed import seed  # noqa: E402

ALEMBIC_INI = os.path.join(API_ROOT, "alembic.ini")


# ── Database plumbing ───────────────────────────────────────────────────────


def sync_url(url: URL) -> URL:
    """Drop the `+asyncpg` driver suffix. Alembic and CREATE DATABASE are synchronous."""
    return url.set(drivername="postgresql")


def named_database(suffix: str) -> URL:
    """The configured database URL with a suffix on the database name."""
    base = make_url(DATABASE_URL)
    return base.set(database=f"{base.database}_{suffix}")


def recreate_database(url: URL) -> None:
    """DROP IF EXISTS + CREATE, connected to the maintenance database.

    AUTOCOMMIT because CREATE DATABASE cannot run inside a transaction, and
    `pg_terminate_backend` because a connection left open by an earlier run — a pool
    that outlived its engine, a debugger session — would otherwise make the drop hang
    rather than fail.
    """
    admin = create_engine(
        sync_url(url).set(database="postgres"), isolation_level="AUTOCOMMIT"
    )
    try:
        with admin.connect() as conn:
            conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :name AND pid <> pg_backend_pid()"
                ),
                {"name": url.database},
            )
            conn.execute(text(f'DROP DATABASE IF EXISTS "{url.database}"'))
            conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    finally:
        admin.dispose()


def alembic_config(url: URL) -> Config:
    """An Alembic config pointed at `url`.

    The URL travels in the environment rather than through `set_main_option` because
    alembic.ini is an interpolating parser and a password containing `%` would turn a
    scratch-database override into an unreadable error. env.py reads the same variable.
    """
    os.environ["ALEMBIC_DATABASE_URL"] = sync_url(url).render_as_string(
        hide_password=False
    )
    return Config(ALEMBIC_INI)


def upgrade(url: URL, revision: str = "head") -> None:
    command.upgrade(alembic_config(url), revision)


def downgrade(url: URL, revision: str = "base") -> None:
    command.downgrade(alembic_config(url), revision)


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def database_url() -> Iterator[URL]:
    """`speaklab_test`, freshly created and migrated to head.

    Session-scoped and synchronous. Synchronous matters: Alembic is a blocking API, and
    a session-scoped *async* fixture would need an event loop that outlives the
    function-scoped ones pytest-asyncio gives each test.
    """
    url = named_database("test")
    recreate_database(url)
    upgrade(url)
    yield url


@pytest_asyncio.fixture
async def db_engine(database_url: URL):
    """One async engine per test.

    Per test rather than per session because each test runs in its own event loop, and
    an asyncpg connection made in one loop cannot be used from another — the symptom is
    an `attached to a different loop` error several tests after the one that caused it.
    """
    test_engine = create_async_engine(database_url)
    yield test_engine
    await test_engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def seeded(db_session: AsyncSession) -> AsyncSession:
    """The scenarios and passages, loaded.

    Uses the real loader rather than a fixture factory, so the rows the endpoints are
    tested against are the rows a user would actually get. It is idempotent, so running
    it before every test costs two SELECTs after the first.
    """
    await seed(db_session)
    await db_session.commit()
    return db_session


@pytest_asyncio.fixture
async def client(db_engine) -> AsyncGenerator[AsyncClient, None]:
    """The app, with `get_db` pointed at the test database."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async def _get_test_db() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = _get_test_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()

    # The health endpoint probes the database through the module-level engine rather
    # than through get_db — it is a liveness check, and a liveness check that only sees
    # the connection a request was given would report on the wrong thing. Disposing it
    # here keeps that engine's pool from outliving the loop this test ran in.
    await engine.dispose()
