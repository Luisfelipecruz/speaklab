"""Who is asking, and may they have this row.

Two things live here, and they are deliberately the *only* two. FR-4 says no endpoint
returns another user's data, and the way that requirement is usually broken is not by
writing a wrong check — it is by writing no check on the one endpoint added in a hurry.
So there is one dependency that answers "who", one helper that answers "may they", and
`tests/test_ownership.py` walks the router table asserting that every route either uses
the first or is on a short, explicit list of public paths. A future milestone that adds
`GET /sessions/{id}` without authentication fails that test rather than shipping.

**Cross-user reads are 404, not 403.** A 403 is a confirmation: it tells the caller the
row exists and belongs to somebody else, which is exactly the fact they were probing
for. Incrementing an id against a 403 enumerates the table. Against a 404 it is
indistinguishable from an id that was never issued.
"""

from typing import TypeVar

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import SESSION_COOKIE_NAME
from database import get_db
from db_models import User
from db_models.base import Base
from services.security import TokenError, decode_access_token

# Every 401 from this module says the same thing. "No token", "expired", "signature
# does not verify" and "the user was deleted" are four different facts about this
# system's internals, and the caller who benefits from being able to tell them apart is
# not the one who is logged out.
_UNAUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
)


async def current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    """The authenticated account, or 401.

    The token is read from the cookie and from nowhere else — no `Authorization: Bearer`
    fallback. That is a decision, not an omission (D24): accepting a header as well would
    reintroduce every place a token can be read by script, which is the thing the
    httpOnly cookie exists to prevent, and it would do it invisibly. When a non-browser
    client eventually needs access, it gets a token type of its own with its own scopes,
    not a second way to present a session cookie.
    """
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise _UNAUTHENTICATED

    try:
        user_id = decode_access_token(token)
    except TokenError:
        raise _UNAUTHENTICATED from None

    user = await db.scalar(select(User).where(User.id == user_id))
    if user is None:
        # A well-signed token for an account that no longer exists. Rejected rather
        # than trusted: the signature proves the token was issued, not that the row
        # behind it survived.
        raise _UNAUTHENTICATED
    return user


Owned = TypeVar("Owned", bound=Base)


async def get_owned_or_404(
    db: AsyncSession, model: type[Owned], row_id: int, user: User
) -> Owned:
    """One row of `model`, by id, belonging to `user`. 404 otherwise.

    A single function rather than a check written at each call site, because the two
    conditions are folded into one query: `WHERE id = :id AND user_id = :user` cannot be
    half-applied. The failure mode it removes is the fetch-then-compare shape, where the
    comparison is a separate statement somebody can forget or write against the wrong
    variable, and where the row has already been loaded by the time it is refused.

    Used by `GET /audio/{id}` (m8), `GET /sessions/{id}` (m6) and `GET /attempts/{id}`
    (m8). It is exercised now, at m3, against `audio_assets` — the only user-scoped table
    that exists yet — so that the guard the later milestones depend on is tested by the
    milestone that wrote it.
    """
    row = await db.scalar(
        select(model).where(model.id == row_id, model.user_id == user.id)
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No {model.__tablename__[:-1]} with id {row_id}",
        )
    return row
