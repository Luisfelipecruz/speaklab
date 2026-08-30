"""FR-4: no endpoint returns another user's data.

The first test in this file is the one that matters, and it is the reason the file
exists at m3 rather than at m6 when the first user-scoped resource is built. It does not
test a route — it enumerates *every* route the application has registered and asserts
that each one either depends on `current_user` or appears in an explicit table of public
paths, with a written reason.

That shape was chosen over a per-endpoint check because per-endpoint checks test the
endpoints somebody remembered. FR-4 is a claim about all of them, including the one
added at m6 by somebody moving quickly, and the only test that can make that claim is
one that reads the router table. When `POST /sessions` arrives unauthenticated, this
fails and names it.

The second half tests the guard itself — `get_owned_or_404` — against `audio_assets`,
the one user-scoped table that exists at m3. m6 and m8 build on that function, so it is
tested by the milestone that wrote it rather than by the ones that inherit it.
"""

import pytest
from fastapi import HTTPException
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute

from db_models import AudioAsset, User
from dependencies import current_user, get_owned_or_404
from main import app
from services.security import hash_password

# Every route that answers without a session, and why. The reason column is not
# decoration: this is the list somebody edits to make the test below pass, and an entry
# added without a reason is an endpoint that was opened up because a test complained.
PUBLIC_ROUTES: dict[tuple[str, str], str] = {
    ("GET", "/health"): "the compose healthcheck curls it; it has no credentials",
    ("GET", "/health/models"): "reports on containers, not on people",
    ("POST", "/auth/register"): "creating the account that will hold the session",
    ("POST", "/auth/login"): "obtaining the session",
    (
        "POST",
        "/auth/logout",
    ): "clearing a cookie, including an expired one that cannot authenticate",
    ("GET", "/scenarios"): "seeded catalogue content, identical for everyone",
    ("GET", "/scenarios/{slug}"): "seeded catalogue content, identical for everyone",
    ("GET", "/passages"): "seeded catalogue content, identical for everyone",
    ("GET", "/passages/{slug}"): "seeded catalogue content, identical for everyone",
}


def _depends_on(dependant: Dependant, target) -> bool:
    """Walk a route's dependency tree looking for `target`.

    Recursive rather than a scan of the top level, because a route that depends on
    something which itself depends on `current_user` is still scoped — and at m6 the
    session routes are expected to be written exactly that way.
    """
    if dependant.call is target:
        return True
    return any(_depends_on(sub, target) for sub in dependant.dependencies)


def _api_routes() -> list[tuple[str, str, APIRoute]]:
    """(method, path, route) for everything the app serves.

    `APIRoute` only — Starlette's own routes for `/docs` and `/openapi.json` carry no
    dependency tree, and asserting a policy about authentication on the schema endpoint
    would be a category error. If those should ever require a session that is a
    middleware decision, not a dependency one.
    """
    found = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
            found.append((method, route.path, route))
    return found


def test_every_route_is_either_scoped_to_a_user_or_declared_public():
    """FR-4, asserted over the router table rather than route by route.

    Set equality in both directions, on purpose:

    * a route that is neither scoped nor listed fails — the m6 case, an endpoint
      shipped without authentication;
    * a route that is listed but *is* scoped also fails — which catches the stale
      entry left behind after an endpoint was correctly locked down, so the table
      cannot quietly become a list of things that used to be public.
    """
    unscoped = {
        (method, path)
        for method, path, route in _api_routes()
        if not _depends_on(route.dependant, current_user)
    }

    missing = unscoped - set(PUBLIC_ROUTES)
    stale = set(PUBLIC_ROUTES) - unscoped

    assert not missing, (
        "these routes require no session and are not declared public — either add "
        f"`current_user` or add them to PUBLIC_ROUTES with a reason: {sorted(missing)}"
    )
    assert (
        not stale
    ), f"declared public but actually scoped; remove them from PUBLIC_ROUTES: {sorted(stale)}"


def test_the_user_scoped_routes_are_the_ones_expected_at_m6():
    """A companion to the test above, which would also pass if *nothing* were scoped and
    everything were listed as public. This one names the routes that must be locked.

    It is meant to be edited by each milestone that adds a scoped route — m4 added
    `GET /audio/{asset_id}`, m6 added the six session routes — and the edit is the point.
    A route arriving in this set without somebody typing it here is a route nobody decided
    should be private.

    m6 is the milestone where this stopped being a formality. Everything scoped before it
    was one row deep: a profile, or a recording read by id. A session is a tree — turns,
    word timings, transcripts, and audio of somebody's actual voice — and it is reached
    through a sequential integer, so `GET /sessions/41` is a guess anybody can make. The
    other half of that guarantee is `get_owned_or_404` folding existence and ownership
    into one WHERE, tested below and again in test_sessions.py against a second account.
    """
    scoped = {
        (method, path)
        for method, path, route in _api_routes()
        if _depends_on(route.dependant, current_user)
    }
    assert scoped == {
        ("GET", "/auth/me"),
        ("PATCH", "/auth/me"),
        ("GET", "/audio/{asset_id}"),
        ("POST", "/sessions"),
        ("GET", "/sessions"),
        ("GET", "/sessions/{session_id}"),
        ("DELETE", "/sessions/{session_id}"),
        ("POST", "/sessions/{session_id}/end"),
        ("POST", "/sessions/{session_id}/turns"),
    }


# ── The guard itself ────────────────────────────────────────────────────────


@pytest.fixture
def two_users():
    return (
        User(email="owner@example.test", password_hash=hash_password("owner-password")),
        User(email="other@example.test", password_hash=hash_password("other-password")),
    )


async def test_a_row_is_returned_to_its_owner(db_session, two_users):
    owner, _ = two_users
    db_session.add(owner)
    await db_session.flush()

    asset = AudioAsset(
        user_id=owner.id,
        path="/audio/owner/1.wav",
        duration_ms=4200,
        sample_rate=16000,
        format="wav",
        sha256="a" * 64,
    )
    db_session.add(asset)
    await db_session.flush()

    found = await get_owned_or_404(db_session, AudioAsset, asset.id, owner)
    assert found.id == asset.id

    await db_session.rollback()


async def test_another_users_row_is_404_and_not_403(db_session, two_users):
    """The status code is the test.

    403 confirms the row exists and belongs to somebody else — which is the fact the
    request was probing for, and it makes incrementing an id an enumeration of the
    table. 404 is indistinguishable from an id that was never issued.
    """
    owner, other = two_users
    db_session.add_all([owner, other])
    await db_session.flush()

    asset = AudioAsset(
        user_id=owner.id,
        path="/audio/owner/2.wav",
        duration_ms=1000,
        sample_rate=16000,
        format="wav",
        sha256="b" * 64,
    )
    db_session.add(asset)
    await db_session.flush()

    with pytest.raises(HTTPException) as raised:
        await get_owned_or_404(db_session, AudioAsset, asset.id, other)

    assert raised.value.status_code == 404
    assert raised.value.status_code != 403

    await db_session.rollback()


async def test_a_row_that_does_not_exist_is_the_same_404(db_session, two_users):
    """Same status and same shape as the row that exists and belongs to someone else.
    If the two differed, the difference would be the leak."""
    owner, _ = two_users
    db_session.add(owner)
    await db_session.flush()

    with pytest.raises(HTTPException) as raised:
        await get_owned_or_404(db_session, AudioAsset, 987654321, owner)

    assert raised.value.status_code == 404

    await db_session.rollback()


async def test_two_accounts_do_not_see_each_other(client, other_client):
    """End to end, through two cookie jars rather than two calls with one.

    A single client shares one jar, so logging the second account in would overwrite the
    first cookie and the test would be one user twice.
    """
    from tests.conftest import register_account

    first = await register_account(client)
    second = await register_account(other_client)

    assert first["id"] != second["id"]
    assert (await client.get("/auth/me")).json()["id"] == first["id"]
    assert (await other_client.get("/auth/me")).json()["id"] == second["id"]
