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
import uuid
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
    """The app, with `get_db` pointed at the test database.

    The override **commits**, exactly as the real `get_db` does. That is not decoration.
    Written the obvious way — `async with factory() as session: yield session` — the
    override quietly removes the transaction boundary, and every write made through the
    client is rolled back when the session closes. Until m3 the suite only read, so it
    was green and meaningless in the same breath; the first symptom would have been
    `POST /auth/register` returning 201 and the next request 401ing on a user that never
    existed. `test_auth.py::test_registration_survives_the_request_that_created_it`
    exists to fail if this drifts back.
    """
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async def _get_test_db() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

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


# ── Accounts ────────────────────────────────────────────────────────────────
#
# The test database is created once per session and never truncated between tests, so
# two tests that both register `a@example.com` would collide on the unique index — and
# the second one would fail with a 409 that has nothing to do with what it was testing.
# Every account therefore gets an address of its own.


def unique_email(label: str = "user") -> str:
    """An address no other test has used."""
    return f"{label}-{uuid.uuid4().hex[:12]}@example.com"


PASSWORD = "practice-makes-permanent"


async def register_account(
    client: AsyncClient, email: str | None = None, password: str = PASSWORD, **fields
) -> dict:
    """Register through the API and return the profile body.

    Through the API rather than by inserting a row, because a fixture that writes its
    own `User` with its own hash is a fixture that can drift from what registration
    actually produces — and the tests that matter here are about exactly that path.
    """
    response = await client.post(
        "/auth/register",
        json={"email": email or unique_email(), "password": password, **fields},
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest_asyncio.fixture
async def account(client: AsyncClient) -> dict:
    """One registered, logged-in account. The client carries its cookie."""
    return await register_account(client)


@pytest_asyncio.fixture
async def other_client(db_engine) -> AsyncGenerator[AsyncClient, None]:
    """A second browser, with its own cookie jar.

    Two `AsyncClient`s rather than one, because a single client shares one jar: logging
    the second account in would overwrite the first one's cookie, and a cross-user test
    written that way is really testing one user twice.
    """
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async def _get_test_db() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _get_test_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ── Audio storage ───────────────────────────────────────────────────────────


@pytest.fixture
def audio_root(tmp_path, monkeypatch):
    """Point the storage layer at a temporary directory.

    Without this the suite would write into `/audio`, which is a Docker volume in the
    container and a path that does not exist on a developer's laptop. Patched on the
    module rather than on `config`, because `services.audio` binds the name at import.

    Lived in `test_audio.py` until m6, when the conversation tests needed the same thing:
    every stored turn writes a file, and a suite that leaves WAVs in a volume is a suite
    whose second run tests different state from its first.
    """
    from services import audio as audio_service

    monkeypatch.setattr(audio_service, "AUDIO_ROOT", str(tmp_path))
    return tmp_path


# ── Stub models ─────────────────────────────────────────────────────────────
#
# The conversation loop is three services deep, and none of them is what the loop's own
# tests are about. What is about to be tested is prompt assembly, a token budget,
# summarisation, transaction boundaries and error mapping — all of which are decided in
# this codebase and none of which need a model to be running. So the recogniser, the
# voice and the LLM are all replaced here.
#
# The measurement suites are the other half of this arrangement. `test_conversation_live.py`
# runs the same paths against the real containers and skips when they are absent, which
# is where every number that gets published comes from. Stubs prove the logic; only the
# live suite is allowed to prove a latency.


def silent_wav(duration_ms: int = 200, sample_rate: int = 22050) -> bytes:
    """A real, playable WAV of silence.

    Real rather than a header-shaped byte string, because `services/wav.py` parses these
    and joins them: a fake would test the fake. The frame count varies with
    `duration_ms`, so a concatenation test can assert the output length is the sum of
    its inputs and mean it.
    """
    import io
    import wave

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(sample_rate)
        writer.writeframes(b"\x00\x00" * round(sample_rate * duration_ms / 1000))
    return buffer.getvalue()


class StubProvider:
    """A scripted LLM. Records every message list it was given.

    `calls` is the important attribute and the reason this is a class rather than a
    lambda: most of what m6 has to get right is *what was in the prompt* — the persona on
    every turn, the digest once it exists, the history under budget — and those are
    assertions about the request, not about the reply.

    `stream` yields word-sized deltas rather than the whole reply in one, because the
    sentence accumulator downstream is built to reassemble sentences from fragments that
    arrive mid-word, and a stub that yielded whole sentences would never exercise it.
    """

    def __init__(self, replies=None, model: str = "stub-model") -> None:
        self.replies = list(replies or ["That sounds reasonable. What happened next?"])
        self.calls: list[list] = []
        self._model = model

    @property
    def model(self) -> str:
        return self._model

    def _next(self) -> str:
        return self.replies[(len(self.calls) - 1) % len(self.replies)]

    def _completion(self, messages, text: str):
        from services.llm import Completion, estimate_messages

        return Completion(
            text=text,
            model=self._model,
            prompt_tokens=estimate_messages(messages),
            completion_tokens=max(1, len(text) // 4),
            latency_ms=1,
        )

    async def complete(self, messages, max_tokens=None):
        self.calls.append(messages)
        return self._completion(messages, self._next())

    async def stream(self, messages, max_tokens=None):
        import re

        self.calls.append(messages)
        text = self._next()
        for delta in re.findall(r"\S+\s*", text):
            yield delta
        yield self._completion(messages, text)


class BrokenProvider(StubProvider):
    """A provider that is down. Raises on every call, as `OllamaProvider` would."""

    def __init__(self, error=None) -> None:
        super().__init__()
        from services.llm import LlmUnavailable

        self._error = error or LlmUnavailable("ConnectError: [Errno 111] refused")

    async def complete(self, messages, max_tokens=None):
        self.calls.append(messages)
        raise self._error

    async def stream(self, messages, max_tokens=None):
        self.calls.append(messages)
        raise self._error
        yield  # pragma: no cover — makes this an async generator, as the protocol says


@pytest.fixture
def provider():
    """A stub provider wired into the app for the whole test.

    Overriding `get_provider` rather than patching an import: it is a FastAPI dependency
    precisely so that this is one line, and so that no test has to know which module the
    endpoint imported it into.
    """
    from services.llm import get_provider

    stub = StubProvider()
    app.dependency_overrides[get_provider] = lambda: stub
    yield stub
    app.dependency_overrides.pop(get_provider, None)


@pytest.fixture
def voice(monkeypatch):
    """Replace the tts service with something that returns real WAVs instantly.

    Patched on `services.conversation`, which is where `speak` is bound. The duration
    scales with the text so that a two-sentence reply really does produce a longer file
    than a one-sentence reply, which is what makes the concatenation assertions mean
    something.
    """
    from models.speech import Speech
    from services import conversation

    spoken: list[str] = []

    async def fake_speak(text, voice=None, length_scale=None, client=None):
        spoken.append(text)
        duration_ms = max(80, len(text) * 4)
        return Speech(
            audio=silent_wav(duration_ms),
            voice=voice or "stub-voice",
            sample_rate=22050,
            duration_ms=duration_ms,
            sentences=1,
            length_scale=1.0,
            latency_ms=1,
        )

    monkeypatch.setattr(conversation, "speak", fake_speak)
    return spoken


@pytest.fixture
def recogniser(monkeypatch):
    """Replace the asr service. Returns whatever the test queues up.

    `heard` is a list the test appends transcripts to; each call pops the next one, and
    a test that queues nothing gets a default. Word timings are generated rather than
    fixed so that `turns.words` is a plausible array of the right length — m9 computes
    fluency from exactly this shape, and a stub that stored an empty list would leave
    that column untested until the milestone that reads it.
    """
    from models.audio import DecoderSettings, SourceMedia, Transcription, Word
    from routers import turns as turns_router

    heard: list[str] = []

    async def fake_transcribe(data, filename="recording", content_type=None):
        text = (
            heard.pop(0) if heard else "I worked on that project for about two years."
        )
        words = [
            Word(w=word, start_ms=index * 400, end_ms=index * 400 + 350, logprob=-0.2)
            for index, word in enumerate(text.split())
        ]
        return Transcription(
            text=text,
            words=words,
            confidence=0.93,
            timestamp_fixups=0,
            language="en",
            model="stub-whisper",
            decoder=DecoderSettings(beam_size=5, vad_filter=True, compute_type="int8"),
            source=SourceMedia(
                format="wav",
                codec="pcm_s16le",
                sample_rate=16000,
                channels=1,
                duration_ms=max(400, len(words) * 400),
            ),
            latency_ms=12,
        )

    monkeypatch.setattr(turns_router, "transcribe", fake_transcribe)
    return heard
