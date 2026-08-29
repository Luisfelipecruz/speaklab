"""Async engine and session factory.

Two choices worth being able to defend in a review:

1. `async_sessionmaker` rather than `sessionmaker(class_=AsyncSession)`. The latter is
   the SQLAlchemy 1.4 idiom and still works, but 2.0 ships a properly typed async
   factory, so the session type is inferred rather than asserted.

2. `expire_on_commit=False`. With the default `True`, committing expires every loaded
   attribute, so touching an object afterwards — serialising it into a response, for
   example — triggers a lazy refresh, and implicit IO in an async context raises
   `MissingGreenlet`. Turning it off keeps loaded state usable after commit, which is
   exactly what a request/response cycle needs.
"""

import os
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config import DATABASE_URL

# SQL_ECHO=1 logs every statement SQLAlchemy emits. It exists so a query count can be
# shown rather than claimed — the same reason it exists in the reference project.
engine = create_async_engine(DATABASE_URL, echo=os.environ.get("SQL_ECHO") == "1")

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a session with a transaction boundary.

    The trade-off worth naming: the pooled connection is held for the whole request, so
    a slow non-database step inside an endpoint keeps it checked out. Under load that is
    how a pool of 5-10 connections is exhausted. The turn endpoint in m6 calls three
    model services and an LLM inside one request, so it will need a narrower `async with`
    around just its queries rather than this dependency.
    """
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
