"""Registration, login, logout and the profile.

The tests worth reading first are the ones that are not about happy paths:

* `test_registration_survives_the_request_that_created_it` — proves the test client's
  session actually commits. An override that does not would leave the whole suite green
  while every write through the API was silently rolled back.
* `test_an_unknown_email_and_a_wrong_password_are_indistinguishable` — the login
  endpoint must not be usable to ask whether somebody has an account here.
* `test_no_auth_response_contains_the_password_hash` — asserted against the raw response
  text rather than against parsed keys, so a hash nested inside some future envelope
  still fails it.
"""

from datetime import timedelta

import jwt
import pytest
from tests.conftest import PASSWORD, register_account, unique_email
from httpx import AsyncClient
from sqlalchemy import select

from config import JWT_ALGORITHM, JWT_SECRET, SESSION_COOKIE_NAME
from db_models import User
from services.security import create_access_token


# ── Registration ────────────────────────────────────────────────────────────


async def test_registration_returns_the_profile_and_a_session(client: AsyncClient):
    email = unique_email()
    response = await client.post(
        "/auth/register",
        json={"email": email, "password": PASSWORD, "native_language": "pt-BR"},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["email"] == email
    assert body["native_language"] == "pt-BR"
    assert body["retain_audio"] is True
    assert SESSION_COOKIE_NAME in response.cookies


async def test_registration_survives_the_request_that_created_it(client: AsyncClient):
    """A second request sees the account the first one made.

    This is the commit test. It passes only if `get_db`'s transaction boundary is
    reproduced by the test override — see the `client` fixture in conftest.
    """
    profile = await register_account(client)

    me = await client.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["id"] == profile["id"]


async def test_the_same_email_cannot_register_twice(client: AsyncClient):
    email = unique_email()
    await register_account(client, email=email)

    again = await client.post(
        "/auth/register", json={"email": email, "password": PASSWORD}
    )
    assert again.status_code == 409
    assert "already exists" in again.json()["detail"]


async def test_the_email_is_stored_lowercased(client: AsyncClient):
    """Otherwise `Ana@example.com` and `ana@example.com` are two accounts.

    The unique index is on the raw column, so case folding has to happen before the
    insert or the constraint protects nothing.
    """
    email = unique_email()
    await register_account(client, email=email.upper())

    login = await client.post(
        "/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert login.status_code == 200
    assert login.json()["email"] == email


@pytest.mark.parametrize(
    "body, why",
    [
        ({"email": "not-an-email", "password": PASSWORD}, "malformed address"),
        ({"email": "a@example.test", "password": "short"}, "under eight characters"),
        ({"email": "b@example.test", "password": "x" * 129}, "over the length cap"),
        (
            {
                "email": "c@example.test",
                "password": PASSWORD,
                "native_language": "Spanish",
            },
            "not an ISO 639-1 code",
        ),
        (
            {
                "email": "d@example.test",
                "password": PASSWORD,
                "cefr_self_assessed": "B7",
            },
            "not a CEFR band",
        ),
        (
            {"email": "e@example.test", "password": PASSWORD, "admin": True},
            "a field the model does not declare",
        ),
    ],
)
async def test_registration_rejects(client: AsyncClient, body: dict, why: str):
    response = await client.post("/auth/register", json=body)
    assert response.status_code == 422, f"should reject {why}: {response.text}"


async def test_the_stored_hash_is_argon2id(client: AsyncClient, db_session):
    """Asserted against the column rather than against the library.

    The prefix is the part that matters: it names the variant, and `argon2id` rather
    than `argon2i` or `argon2d` is the one that resists both GPU and side-channel
    attacks. A library default that changed would show up here.
    """
    profile = await register_account(client)

    stored = await db_session.scalar(
        select(User.password_hash).where(User.id == profile["id"])
    )
    assert stored.startswith("$argon2id$")
    assert PASSWORD not in stored


# ── Login ───────────────────────────────────────────────────────────────────


async def test_login_issues_a_session(client: AsyncClient):
    email = unique_email()
    await register_account(client, email=email)
    client.cookies.clear()

    response = await client.post(
        "/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert response.status_code == 200
    assert SESSION_COOKIE_NAME in response.cookies
    assert (await client.get("/auth/me")).status_code == 200


async def test_an_unknown_email_and_a_wrong_password_are_indistinguishable(
    client: AsyncClient,
):
    """Same status, same body. Anything else is a user-enumeration oracle."""
    email = unique_email()
    await register_account(client, email=email)

    wrong_password = await client.post(
        "/auth/login", json={"email": email, "password": "not-the-password"}
    )
    no_such_user = await client.post(
        "/auth/login", json={"email": unique_email(), "password": PASSWORD}
    )

    assert wrong_password.status_code == no_such_user.status_code == 401
    assert wrong_password.json() == no_such_user.json()


async def test_a_failed_login_does_not_replace_a_working_session(client: AsyncClient):
    """A 401 must not clear the cookie the caller already had.

    Otherwise one mistyped password on a re-authentication prompt logs the user out of
    the session they were in the middle of.
    """
    await register_account(client)

    failed = await client.post(
        "/auth/login", json={"email": unique_email(), "password": PASSWORD}
    )
    assert failed.status_code == 401
    assert (await client.get("/auth/me")).status_code == 200


# ── The cookie ──────────────────────────────────────────────────────────────


async def test_the_session_cookie_is_httponly_and_scoped_to_the_whole_api(
    client: AsyncClient,
):
    email = unique_email()
    response = await client.post(
        "/auth/register", json={"email": email, "password": PASSWORD}
    )

    header = response.headers["set-cookie"]
    assert "HttpOnly" in header, "a token readable by script is a token in localStorage"
    assert "Path=/" in header, "audio and progress live outside /auth"
    assert "SameSite=lax" in header
    # COOKIE_SECURE defaults to 0 because the laptop stack is http. A `Secure` cookie
    # here would be set by the API, dropped by the browser, and the only symptom would
    # be a login that appears to work and a /auth/me that 401s.
    assert "Secure" not in header


async def test_the_token_is_never_in_a_response_body(client: AsyncClient):
    """The cookie is httpOnly so that no script can read the token. Returning the same
    token in the body would hand it to the script anyway."""
    email = unique_email()
    registered = await client.post(
        "/auth/register", json={"email": email, "password": PASSWORD}
    )
    logged_in = await client.post(
        "/auth/login", json={"email": email, "password": PASSWORD}
    )

    token = registered.cookies[SESSION_COOKIE_NAME]
    for response in (registered, logged_in):
        assert token not in response.text
        assert "token" not in response.json()


async def test_no_auth_response_contains_the_password_hash(client: AsyncClient):
    email = unique_email()
    responses = [
        await client.post(
            "/auth/register", json={"email": email, "password": PASSWORD}
        ),
        await client.post("/auth/login", json={"email": email, "password": PASSWORD}),
        await client.get("/auth/me"),
        await client.patch("/auth/me", json={"native_language": "fr"}),
    ]
    for response in responses:
        assert "$argon2" not in response.text
        assert "password" not in response.text.lower()


# ── Tokens that should not work ─────────────────────────────────────────────


async def test_a_request_with_no_cookie_is_401(client: AsyncClient):
    assert (await client.get("/auth/me")).status_code == 401


@pytest.mark.parametrize("bad", ["", "not-a-jwt", "a.b.c"])
async def test_a_malformed_cookie_is_401(client: AsyncClient, bad: str):
    client.cookies.set(SESSION_COOKIE_NAME, bad)
    assert (await client.get("/auth/me")).status_code == 401


async def test_an_expired_token_is_401(client: AsyncClient, account: dict):
    client.cookies.set(
        SESSION_COOKIE_NAME,
        create_access_token(account["id"], ttl=timedelta(seconds=-1)),
    )
    assert (await client.get("/auth/me")).status_code == 401


async def test_a_token_signed_with_another_key_is_401(
    client: AsyncClient, account: dict
):
    """The signature is the whole mechanism. If this passes, the cookie is a claim
    rather than a proof and anyone can write one."""
    forged = jwt.encode(
        {"sub": str(account["id"])}, "not-the-secret", algorithm="HS256"
    )
    client.cookies.set(SESSION_COOKIE_NAME, forged)
    assert (await client.get("/auth/me")).status_code == 401


async def test_a_token_with_a_non_numeric_subject_is_401(client: AsyncClient):
    forged = jwt.encode({"sub": "administrator"}, JWT_SECRET, algorithm=JWT_ALGORITHM)
    client.cookies.set(SESSION_COOKIE_NAME, forged)
    assert (await client.get("/auth/me")).status_code == 401


async def test_a_valid_token_for_an_account_that_does_not_exist_is_401(
    client: AsyncClient,
):
    """A correct signature proves the token was issued, not that the row survived."""
    client.cookies.set(SESSION_COOKIE_NAME, create_access_token(2_147_483_647))
    assert (await client.get("/auth/me")).status_code == 401


# ── Logout ──────────────────────────────────────────────────────────────────


async def test_logout_clears_the_session(client: AsyncClient, account: dict):
    response = await client.post("/auth/logout")

    assert response.status_code == 204
    assert not client.cookies.get(SESSION_COOKIE_NAME)
    assert (await client.get("/auth/me")).status_code == 401


async def test_logout_works_without_a_session(client: AsyncClient):
    """The state most in need of clearing is a broken cookie, and a logout that 401s on
    an expired session leaves the browser holding something it cannot delete."""
    client.cookies.set(SESSION_COOKIE_NAME, "expired-or-nonsense")
    assert (await client.post("/auth/logout")).status_code == 204


# ── The profile ─────────────────────────────────────────────────────────────


async def test_me_returns_the_current_account(client: AsyncClient, account: dict):
    body = (await client.get("/auth/me")).json()
    assert body == account


async def test_patch_me_updates_only_what_was_sent(client: AsyncClient, account: dict):
    response = await client.patch("/auth/me", json={"retain_audio": False})

    assert response.status_code == 200
    body = response.json()
    assert body["retain_audio"] is False
    assert body["native_language"] == account["native_language"]
    assert (await client.get("/auth/me")).json()["retain_audio"] is False


async def test_patch_me_can_clear_a_field(client: AsyncClient):
    """An explicit `null` means clear it, and must not be confused with absent."""
    await register_account(client, cefr_self_assessed="B2")
    assert (await client.get("/auth/me")).json()["cefr_self_assessed"] == "B2"

    response = await client.patch("/auth/me", json={"cefr_self_assessed": None})
    assert response.json()["cefr_self_assessed"] is None


async def test_patch_me_rejects_an_empty_body(client: AsyncClient, account: dict):
    assert (await client.patch("/auth/me", json={})).status_code == 422


async def test_patch_me_rejects_a_misspelled_field(client: AsyncClient, account: dict):
    """`retain_audioo` must not return 200 with the old value. Audio retention is a
    promise about whether a recording is deleted; an endpoint that silently ignores it
    breaks the promise and reports success."""
    response = await client.patch("/auth/me", json={"retain_audioo": False})
    assert response.status_code == 422
    assert (await client.get("/auth/me")).json()["retain_audio"] is True


async def test_patch_me_requires_a_session(client: AsyncClient):
    assert (
        await client.patch("/auth/me", json={"retain_audio": False})
    ).status_code == 401


# ── The primitives, without a request ───────────────────────────────────────


def test_two_hashes_of_one_password_differ():
    """Per-hash salt. Identical hashes for identical passwords would mean a rainbow
    table works and that two rows reveal a shared password."""
    from services.security import hash_password

    assert hash_password(PASSWORD) != hash_password(PASSWORD)


def test_verify_accepts_the_password_and_rejects_everything_else():
    from services.security import hash_password, verify_password

    stored = hash_password(PASSWORD)
    assert verify_password(PASSWORD, stored) is True
    assert verify_password(PASSWORD + " ", stored) is False
    assert verify_password("", stored) is False


def test_verify_returns_false_on_a_corrupt_hash_rather_than_raising():
    """A malformed `password_hash` column is a corrupt row. The right answer is a failed
    login, not a 500 that tells the caller the column is malformed."""
    from services.security import verify_password

    assert verify_password(PASSWORD, "not-an-argon2-hash") is False


def test_a_fresh_hash_does_not_need_rehashing():
    from services.security import hash_password, needs_rehash

    assert needs_rehash(hash_password(PASSWORD)) is False


@pytest.mark.parametrize(
    "value, expect_dev_key",
    [("", True), ("   ", False), ("a-real-deployment-secret", False)],
)
def test_a_blank_jwt_secret_falls_back_to_the_development_key(
    value: str, expect_dev_key: bool
):
    """Compose passes an unset `${JWT_SECRET:-}` through as an empty string.

    Read with `os.environ.get("JWT_SECRET", DEV_JWT_SECRET)` that empty string wins, and
    the result is the worst of both: every token signed with a zero-length key, and no
    startup warning, because "" is not the sentinel the warning compares against. The
    `or` in config.py is what makes blank mean absent, and this is the test that fails
    if somebody ever tidies it back into a `.get` default.

    Run in a subprocess because `config` is a module of constants read once at import,
    and reloading it inside the suite would leave the rest of the tests looking at
    whichever value happened to land last.
    """
    import os
    import subprocess
    import sys

    from tests.conftest import API_ROOT

    # `API_ROOT`, not a literal "/app". The container mounts api/ at /app and CI runs
    # pytest with `working-directory: api`, so a hardcoded path passes on a laptop and
    # fails in the pipeline — where nobody is watching it fail for the right reason.
    result = subprocess.run(
        [sys.executable, "-c", "import config; print(config.JWT_SECRET_IS_DEV)"],
        env={**os.environ, "JWT_SECRET": value},
        capture_output=True,
        text=True,
        cwd=API_ROOT,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(expect_dev_key)
