"""How much practice this system has actually seen, counted rather than remembered.

    docker compose exec api python -m scripts.corpus
    docker compose exec api python -m scripts.corpus --json

Three of this project's success criteria are not statements about code. S4 asks whether
GOP separates broken readings from clean ones, S5 asks for 0.70 detection precision on the
golden set, and S7 asks for thirty-day trends across four families from twenty sessions.
All three are unmet, and all three are unmet for the same reason: there is not enough
recorded speech. That is a fact about a database, and `eval/run.py` needs it as a number.

**This exists because a published number has to be counted rather than recalled.** The
evaluation report states what the corpus holds, and a report quoting last week's figure
under this week's date is the exact failure that rule is about. So the census is a query, it runs as part of `make eval`, and its
output carries the timestamp it was taken at.

It counts across every account, not one, because the criteria are about the evidence this
system has rather than about any person's progress. The definitions are the rollup's,
deliberately: an analysed user turn is what `services/rollup.py` treats as one, so the
number here and the number under the charts cannot drift apart.
"""

import argparse
import asyncio
import json
from datetime import datetime, timezone

from sqlalchemy import distinct, func, select

from database import async_session
from db_models import Attempt, PhonemeScore, PracticeSession, Turn, User
from db_models.metrics import FluencyMetrics


async def census() -> dict:
    async with async_session() as db:
        accounts = await db.scalar(select(func.count(User.id)))
        sessions = await db.scalar(select(func.count(PracticeSession.id)))
        conversations = await db.scalar(
            select(func.count(PracticeSession.id)).where(
                PracticeSession.mode == "conversation"
            )
        )
        readings = await db.scalar(
            select(func.count(PracticeSession.id)).where(
                PracticeSession.mode == "read_aloud"
            )
        )

        # An analysed user turn, by the rollup's definition: role user, analysis done.
        analysed = await db.scalar(
            select(func.count(Turn.id)).where(
                Turn.role == "user", Turn.analyzed_at.is_not(None)
            )
        )
        user_turns = await db.scalar(
            select(func.count(Turn.id)).where(Turn.role == "user")
        )
        words = await db.scalar(select(func.sum(FluencyMetrics.word_count))) or 0

        scored = await db.scalar(
            select(func.count(Attempt.id)).where(Attempt.status == "scored")
        )
        phone_instances = await db.scalar(select(func.count(PhonemeScore.id)))

        # Calendar days and distinct accounts with anything on them. Twenty sessions on
        # one day is not the same corpus as twenty sessions across a month, and S7 is a
        # claim about trends, so the spread is the part that matters.
        days = await db.scalar(
            select(func.count(distinct(func.date(PracticeSession.started_at))))
        )
        practised = await db.scalar(
            select(func.count(distinct(PracticeSession.user_id)))
        )
        first = await db.scalar(select(func.min(PracticeSession.started_at)))
        last = await db.scalar(select(func.max(PracticeSession.started_at)))

        # S7 is a claim about a page, and the progress page belongs to one account. A
        # system total answers a different question: five accounts with two sessions
        # each is ten sessions and no trend anywhere. So the criterion is read against
        # the best-provisioned account, and that account is found rather than assumed.
        per_account = (
            await db.execute(
                select(
                    PracticeSession.user_id,
                    func.count(PracticeSession.id),
                    func.count(distinct(func.date(PracticeSession.started_at))),
                )
                .group_by(PracticeSession.user_id)
                .order_by(func.count(PracticeSession.id).desc())
            )
        ).all()
        busiest = (
            {
                "user_id": per_account[0][0],
                "sessions": per_account[0][1],
                "days_with_practice": per_account[0][2],
            }
            if per_account
            else None
        )

    return {
        "counted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "accounts": accounts,
        "accounts_with_practice": practised,
        "sessions": sessions,
        "conversation_sessions": conversations,
        "read_aloud_sessions": readings,
        "user_turns": user_turns,
        "analysed_user_turns": analysed,
        "words": int(words),
        "scored_readings": scored,
        "phone_instances": phone_instances,
        "days_with_practice": days,
        "first_session": first.isoformat() if first else None,
        "last_session": last.isoformat() if last else None,
        "busiest_account": busiest,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json", action="store_true", help="machine-readable, for eval/run.py"
    )
    args = parser.parse_args()

    counts = asyncio.run(census())
    if args.json:
        print(json.dumps(counts, indent=2))
        return 0

    width = max(len(key) for key in counts)
    for key, value in counts.items():
        print(f"{key.replace('_', ' '):<{width}}  {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
