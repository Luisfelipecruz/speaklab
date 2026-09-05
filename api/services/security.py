"""Password hashing and access tokens.

Two primitives, no framework. Nothing in this module imports FastAPI or touches the
database, which is what lets the hashing tests run without a request and the token tests
run without a user.

**Argon2id, via argon2-cffi.** Library defaults are used
deliberately rather than pinned here: argon2-cffi's `PasswordHasher` defaults track the
current RFC 9106 guidance and are raised by its maintainers over time, and
`check_needs_rehash` plus the rehash-on-login in `routers/auth.py` is the mechanism that
carries existing rows forward when they do. Pinning the parameters in this file would
freeze them at whatever was current the day it was written and quietly opt out of that.

The one number worth knowing: the defaults ask for **64 MiB per hash**. That is the
point of Argon2 — it is what makes a GPU attack expensive — but it is also a real
resource cost per concurrent login, and it is the first thing to look at if this ever
runs somewhere with a small memory limit and logins start being OOM-killed.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import (
    InvalidHashError,
    VerificationError,
    VerifyMismatchError,
)

from config import ACCESS_TOKEN_TTL_HOURS, JWT_ALGORITHM, JWT_SECRET

_hasher = PasswordHasher()

# Verified against when the email is unknown, so that "no such user" and "wrong
# password" cost the same wall-clock time. Without it, login is a user-enumeration
# oracle: the miss returns in microseconds and the hit takes however long Argon2 takes,
# and the difference is large enough to read over the network without any statistics.
# Computed once at import — this is the only place a constant password is acceptable.
_DUMMY_HASH = _hasher.hash("a password no account has, used only to burn the same time")


class TokenError(Exception):
    """A token that did not verify.

    One exception for every reason — expired, tampered, signed with another key,
    missing a subject, subject not an integer. The caller turns all of them into the
    same 401, because the difference between them is information about this system's
    internals and is of use to precisely one kind of caller.
    """


# ── Passwords ───────────────────────────────────────────────────────────────


def hash_password(password: str) -> str:
    """Argon2id, encoded string form: `$argon2id$v=19$m=...,t=...,p=...$salt$hash`.

    The parameters travel inside the hash, which is why changing them later does not
    invalidate existing rows — `verify_password` reads each row's own cost and
    `needs_rehash` reports which rows are behind.
    """
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """True if `password` produced `password_hash`.

    Returns False rather than raising for every failure, including
    `InvalidHashError` — a row whose `password_hash` is not a valid Argon2 string is a
    corrupt row, and the right behaviour for a corrupt row is a failed login rather
    than a 500 that tells the caller the column is malformed.
    """
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def verify_dummy_password(password: str) -> bool:
    """Burn one hash verification and return False. Always.

    Called on the no-such-user path so that the two failures are indistinguishable from
    the outside. See `_DUMMY_HASH`.
    """
    verify_password(password, _DUMMY_HASH)
    return False


def needs_rehash(password_hash: str) -> bool:
    """True when a row was hashed with weaker parameters than the current defaults."""
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        # Unparseable is certainly not current. Saying True here means the next
        # successful login replaces it — except that a row this broken cannot produce a
        # successful login, so in practice this is a statement of fact, not a repair.
        return True


# ── Tokens ──────────────────────────────────────────────────────────────────


def create_access_token(user_id: int, ttl: timedelta | None = None) -> str:
    """A signed JWT whose subject is the user id.

    `sub` is a *string*. PyJWT 2.10 validates that claim's type on decode and rejects a
    numeric subject, so writing `int` here produces a token this module cannot read back
    — a failure that shows up as every request 401ing after a library bump rather than
    at the point of the mistake.
    """
    now = datetime.now(timezone.utc)
    expires = now + (
        ttl if ttl is not None else timedelta(hours=ACCESS_TOKEN_TTL_HOURS)
    )
    payload = {"sub": str(user_id), "iat": now, "exp": expires}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> int:
    """The user id, or `TokenError`.

    `algorithms=[JWT_ALGORITHM]` is a whitelist, not a hint. Passing the algorithm from
    the token's own header is the `alg: none` family of vulnerabilities, and PyJWT
    requires the list precisely so that it cannot be skipped by accident.
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc

    subject = payload.get("sub")
    if subject is None:
        raise TokenError("token has no subject")
    try:
        return int(subject)
    except (TypeError, ValueError) as exc:
        raise TokenError(f"subject is not a user id: {subject!r}") from exc
