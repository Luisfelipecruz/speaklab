"""Rebuild the progress snapshots every account is owed.

    docker compose exec api python -m scripts.rollup              # everyone, what is stale
    docker compose exec api python -m scripts.rollup --force      # everyone, everything
    docker compose exec api python -m scripts.rollup --user 5
    docker compose exec api python -m scripts.rollup --dry-run

Ending a session rolls that account up already, so on a working system this has nothing
to do. It exists for the three cases where that is not enough: read-aloud scoring, which
finishes after the request that started it and belongs to a session nobody ever "ends";
turns filled in later by an analysis backfill; and a change to the arithmetic itself,
after which every stored snapshot is a number computed by code that no longer exists.

`--force` is for that last case and is the only reason to reach for it. Without it a
period whose newest turn is older than its snapshot is skipped, so a run over an unchanged
corpus is a few queries and no writes.

**Safe to run beside a live API.** A rollup is a pure function of rows that are already
final — analysed turns and scored readings — so the worst a concurrent session end can do
is compute the same period twice and write the same numbers.
"""

import argparse
import asyncio
import sys

from sqlalchemy import select

from database import async_session
from db_models import User
from services.rollup import is_stale, rebuild_user


async def run(user_id: int | None, force: bool, dry_run: bool) -> int:
    async with async_session() as db:
        query = select(User.id, User.email).order_by(User.id)
        if user_id is not None:
            query = query.where(User.id == user_id)
        accounts = (await db.execute(query)).all()

        if not accounts:
            print("no accounts" if user_id is None else f"no account with id {user_id}")
            return 1 if user_id is not None else 0

        if dry_run:
            for account_id, email in accounts:
                stale = await is_stale(db, account_id)
                print(
                    f"  user {account_id:>4}  {email:<40} "
                    f"{'needs a rollup' if stale else 'up to date'}"
                )
            return 0

        written = 0
        for account_id, email in accounts:
            periods = await rebuild_user(db, account_id, force=force)
            written += len(periods)
            print(
                f"  user {account_id:>4}  {email:<40} "
                + (
                    ", ".join(f"{p.period} {p.start}" for p in periods)
                    if periods
                    else "nothing to do"
                )
            )
        await db.commit()

    print(f"{written} snapshot{'' if written == 1 else 's'} written")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user", type=int, default=None, help="one account, by id")
    parser.add_argument(
        "--force",
        action="store_true",
        help="rewrite every period, not only the ones with newer data underneath",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="say who is out of date and stop"
    )
    args = parser.parse_args()

    sys.exit(asyncio.run(run(args.user, args.force, args.dry_run)))


if __name__ == "__main__":
    main()
