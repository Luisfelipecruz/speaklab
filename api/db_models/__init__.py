"""The write path: SQLAlchemy ORM models, twelve tables.

This module is the barrel, and importing it is what registers every table on
`Base.metadata`. That matters more than convenience: `alembic/env.py` imports this and
nothing else, so a model file that is written but never imported here is invisible to
autogenerate — the table would simply not appear in the next migration, and the failure
would be silent.

The read path is `api/models/` (Pydantic). Two layers on purpose: the column set and the
response shape are different questions, and `scenarios.persona_prompt` is the standing
example — a column that exists, is loaded, and is never serialised to a client.
"""

from db_models.attempt import ATTEMPT_STATUS, Attempt
from db_models.base import Base
from db_models.metrics import (
    FluencyMetrics,
    GrammarUsage,
    LanguageError,
    ProgressSnapshot,
)
from db_models.passage import Passage
from db_models.phoneme import PhonemeScore
from db_models.scenario import Scenario
from db_models.session import SESSION_MODE, SESSION_STATUS, PracticeSession
from db_models.turn import Turn
from db_models.user import AudioAsset, User

__all__ = [
    "ATTEMPT_STATUS",
    "SESSION_MODE",
    "SESSION_STATUS",
    "Attempt",
    "AudioAsset",
    "Base",
    "FluencyMetrics",
    "GrammarUsage",
    "LanguageError",
    "Passage",
    "PhonemeScore",
    "PracticeSession",
    "ProgressSnapshot",
    "Scenario",
    "Turn",
    "User",
]
