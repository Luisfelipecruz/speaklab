"""Register, log in, log out, and read or amend the profile. FR-1 to FR-4.

**Five operations, where the plan's API surface forecast four.** The fifth is
`POST /auth/logout`, and it is not scope creep — it is forced by the decision above it.
The token lives in an httpOnly cookie precisely so that no script can read it, and the
consequence of that is that no script can delete it either. Without a server operation
to clear the cookie there is no way to log out at all. §6 of the plan and the
cookie decision were written independently and could not both be right; the count is
the one that gives.

**The token is set as a cookie and never returned in a body.** A response containing the
token would be the same token in a place the browser stores differently — the caller
would have somewhere to put it, and the httpOnly flag on the cookie would then be
protecting a copy.
"""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from config import (
    ACCESS_TOKEN_TTL_HOURS,
    COOKIE_SAMESITE,
    COOKIE_SECURE,
    SESSION_COOKIE_NAME,
)
from database import get_db
from db_models import User
from dependencies import current_user
from models.auth import LoginRequest, ProfileUpdate, RegisterRequest, UserProfile
from services.security import (
    create_access_token,
    hash_password,
    needs_rehash,
    verify_dummy_password,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])

# One message for a wrong password and for an email with no account. Two messages would
# turn this endpoint into a way to ask whether a given person has an account here, which
# for a language-practice tool is a question worth not answering.
_BAD_CREDENTIALS = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password"
)


def _set_session_cookie(response: Response, user_id: int) -> None:
    """Issue the session cookie.

    `path="/"` because the API serves audio and progress from outside `/auth`, and a
    cookie scoped to the issuing path would be sent to precisely the endpoints that do
    not need it.
    """
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=create_access_token(user_id),
        max_age=ACCESS_TOKEN_TTL_HOURS * 3600,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path="/",
    )


@router.post(
    "/register", response_model=UserProfile, status_code=status.HTTP_201_CREATED
)
async def register(
    body: RegisterRequest, response: Response, db: AsyncSession = Depends(get_db)
) -> User:
    """Create an account and log it in. FR-1, FR-3.

    Registration returns a session rather than redirecting to a login form, because the
    alternative is asking someone for the password they typed nine seconds ago.

    Uniqueness is enforced by catching the constraint violation rather than by a SELECT
    beforehand. A pre-check reads better and is wrong: between the check and the insert
    two concurrent registrations both see nothing, and the loser gets a 500 out of the
    unique index instead of the 409 this returns. The database is the only thing that
    can actually decide this, so it is the thing that is asked.
    """
    user = User(
        email=body.email.lower(),
        password_hash=hash_password(body.password),
        native_language=body.native_language,
        cefr_self_assessed=(
            body.cefr_self_assessed.value if body.cefr_self_assessed else None
        ),
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with that email already exists",
        ) from None

    await db.refresh(user)
    _set_session_cookie(response, user.id)
    return user


@router.post("/login", response_model=UserProfile)
async def login(
    body: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)
) -> User:
    """Exchange credentials for a session cookie. FR-2.

    The no-such-user branch verifies against a dummy hash before failing, so that the
    two rejections take the same time. See `services/security.py`.
    """
    user = await db.scalar(select(User).where(User.email == body.email.lower()))
    if user is None:
        verify_dummy_password(body.password)
        raise _BAD_CREDENTIALS

    if not verify_password(body.password, user.password_hash):
        raise _BAD_CREDENTIALS

    # Argon2's cost parameters travel inside each hash, so raising them later leaves old
    # rows readable but weak. This is the only moment the plaintext is available to fix
    # that, and it costs one hash on the logins that need it and nothing on the rest.
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)

    _set_session_cookie(response, user.id)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> None:
    """Clear the session cookie.

    Deliberately requires no authentication. An expired or malformed cookie is exactly
    the state a user most needs to be able to clear, and a logout that 401s when the
    session is already broken leaves the browser holding a cookie it cannot get rid of.

    What this does not do is revoke the token. There is no server-side session table
    (D23, D24), so a copy taken from the browser beforehand stays valid until it expires.
    That is the cost of the stateless design and it is bounded by `ACCESS_TOKEN_TTL_HOURS`.
    """
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path="/",
    )


@router.get("/me", response_model=UserProfile)
async def read_me(user: User = Depends(current_user)) -> User:
    """The current account. Also the frontend's session check — a 401 here means
    "show the login page", which is why it is cheap and does one query."""
    return user


@router.patch("/me", response_model=UserProfile)
async def update_me(
    body: ProfileUpdate,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Change native language, self-assessed band, or audio retention. FR-26.

    `exclude_unset=True` rather than `exclude_none=True`, and the difference is a real
    one: a body of `{"cefr_self_assessed": null}` means *clear it*, and under
    `exclude_none` that instruction would be dropped and answered with a 200 showing the
    old value.
    """
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(user, field, value.value if hasattr(value, "value") else value)
    await db.flush()
    return user
