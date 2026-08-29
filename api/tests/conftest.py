"""Shared fixtures.

The client is an in-process ASGI transport, not a network call to a running container.
That is what makes `make test` a test of *this* code rather than of whatever happens to
be listening on port 8002.
"""

import os
import sys

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# The api/ directory itself is the import root — `from config import ...`, not
# `from api.config import ...` — because that is what it is inside the container, where
# api/ is mounted at /app. Keeping the two identical means a test that passes here
# passes there.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import app  # noqa: E402
from database import engine  # noqa: E402


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    await engine.dispose()
