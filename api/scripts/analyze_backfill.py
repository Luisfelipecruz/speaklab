"""Analyse the user turns that have not been analysed yet.

Every turn recorded before the analysers existed is sitting at `pending`, and so is any
turn whose labelling model was down when it was spoken. This walks them, oldest first,
and does the work.

    docker compose exec api python -m scripts.analyze_backfill          # a batch
    docker compose exec api python -m scripts.analyze_backfill --all    # everything
    docker compose exec api python -m scripts.analyze_backfill --dry-run

**One turn at a time, and a batch by default.** Each turn is a model call of a second or
more, and they queue behind one Ollama regardless — running them concurrently would make
the total less predictable rather than shorter. The batch bound means an interrupted run
costs one batch of work rather than all of it, and running again picks up exactly where
this one stopped, because the state lives on the row.

**Safe to run twice, and safe to run while the API is serving.** A turn is claimed before
it is worked on, so a live job and this script cannot both write rows for the same turn.

It prints what it did per turn rather than a total at the end. A backfill over a corpus
that produces nothing is indistinguishable from one that never started, unless it says
so as it goes.
"""

import argparse
import asyncio
import sys

from config import ANALYSIS_BATCH_SIZE
from database import async_session
from services.analysis import analyse_turn, pending_turn_ids
from services.llm import get_provider


async def backfill(limit: int | None, dry_run: bool) -> int:
    async with async_session() as db:
        outstanding = await pending_turn_ids(db)

    if not outstanding:
        print("nothing outstanding: every user turn has been analysed")
        return 0

    print(f"{len(outstanding)} user turns outstanding")
    if dry_run:
        print("dry run: " + ", ".join(str(turn_id) for turn_id in outstanding))
        return 0

    todo = outstanding if limit is None else outstanding[:limit]
    if len(todo) < len(outstanding):
        print(f"doing {len(todo)} of them; run again for the rest")

    provider = get_provider()
    failed = 0

    for turn_id in todo:
        outcome = await analyse_turn(turn_id, async_session, provider)
        if outcome.status == "failed":
            failed += 1
        print(
            f"  turn {turn_id:>5}  {outcome.status:<10} "
            f"{outcome.features} forms, {outcome.errors} errors, "
            f"{outcome.rejected} rejected"
            + (f"  — {outcome.detail}" if outcome.detail else "")
        )

    async with async_session() as db:
        remaining = len(await pending_turn_ids(db))
    print(f"{len(todo) - failed} analysed, {failed} failed, {remaining} still to do")
    return 1 if failed else 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--all",
        action="store_true",
        help="do every outstanding turn rather than one batch",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=ANALYSIS_BATCH_SIZE,
        help=f"how many turns to do (default {ANALYSIS_BATCH_SIZE})",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="list what is outstanding and stop"
    )
    args = parser.parse_args()

    sys.exit(asyncio.run(backfill(None if args.all else args.limit, args.dry_run)))


if __name__ == "__main__":
    main()
