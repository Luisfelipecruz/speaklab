"""Recount the forms of every analysed turn and relink its corrections to them.

    docker compose exec api python -m scripts.reparse              # every analysed turn
    docker compose exec api python -m scripts.reparse --turn 18
    docker compose exec api python -m scripts.reparse --dry-run

For after a change to the parser's counting or to the join between a correction and its
verb form. Both are functions of the stored transcript and the stored corrections, so this
needs no model and changes no correction: it rewrites `grammar_usage` and the two form
columns of `language_errors`, and nothing else. Run `make rollup` after it; every turn it
touches is newer than the snapshots computed from it.

It prints each turn whose counts changed, form by form, because a recount that moved a
number nobody can see is a recount nobody can check.
"""

import argparse
import asyncio
import sys

from database import async_session
from services.analysis import analysed_turn_ids, reparse_turn


async def run(turn_id: int | None, dry_run: bool) -> int:
    async with async_session() as db:
        turns = await analysed_turn_ids(db)
    if turn_id is not None:
        turns = [turn for turn in turns if turn == turn_id]
        if not turns:
            print(f"turn {turn_id} is not an analysed user turn")
            return 1

    print(f"{len(turns)} analysed user turns")
    if dry_run or not turns:
        return 0

    changed = corrections = linked = 0
    for turn in turns:
        done = await reparse_turn(turn, async_session)
        if done is None:
            continue
        corrections += done.corrections
        linked += done.linked
        moved = {
            form: (done.forms_before.get(form, 0), done.forms_after.get(form, 0))
            for form in sorted(set(done.forms_before) | set(done.forms_after))
            if done.forms_before.get(form, 0) != done.forms_after.get(form, 0)
        }
        if moved:
            changed += 1
            print(
                f"  turn {turn:>5}  "
                + ", ".join(f"{form} {old}→{new}" for form, (old, new) in moved.items())
            )
    print(
        f"{changed} turns recounted differently; {linked} of {corrections} corrections "
        "linked to a verb form"
    )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--turn", type=int, help="one turn rather than all of them")
    parser.add_argument(
        "--dry-run", action="store_true", help="count the turns and stop"
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(run(args.turn, args.dry_run)))


if __name__ == "__main__":
    main()
