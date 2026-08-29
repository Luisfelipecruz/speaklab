"""Shared read-path types.

Two layers exist — `db_models/` for columns, `models/` for wire shapes — because they
answer different questions. The clearest case is `scenarios.persona_prompt`: a column
that is loaded on every query and serialised by nothing. Collapsing the layers would
make it visible by default, and the only thing stopping a persona's instructions from
being shipped to the browser would be nobody having noticed.

The seed models here are strict on purpose. `seeds/*.json` is hand-written content, and
the difference between validating it at load time and validating it at request time is
the difference between a seed run that fails with a line number and an endpoint that
500s a week later.
"""

from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints


class CEFRBand(str, Enum):
    """The band vocabulary, closed.

    A query parameter typed as this returns 422 for `?band=B7` instead of quietly
    returning an empty list — which reads to a caller as "no scenarios exist at that
    level", a wrong answer rather than a rejected question.
    """

    A1 = "A1"
    A2 = "A2"
    B1 = "B1"
    B2 = "B2"
    C1 = "C1"
    C2 = "C2"


# The 39 ARPAbet phones, unstressed, as g2p_en emits them. `passages.phoneme_focus` is
# validated against this at seed time.
#
# m8's phone_map.py carries the ARPAbet -> eSpeak-IPA table from the m0 spike, where all
# 39 mapped with no residue. That module must assert its own keys equal this tuple: two
# copies of a phone set that drift apart is handoff trap 1, and a phone missing from one
# of them is a pronunciation error that is never scored and never reported as unscored.
# fmt: off
ARPABET_PHONES = (
    "AA", "AE", "AH", "AO", "AW", "AY", "B",  "CH", "D",  "DH",
    "EH", "ER", "EY", "F",  "G",  "HH", "IH", "IY", "JH", "K",
    "L",  "M",  "N",  "NG", "OW", "OY", "P",  "R",  "S",  "SH",
    "T",  "TH", "UH", "UW", "V",  "W",  "Y",  "Z",  "ZH",
)
# fmt: on

# Lowercase, hyphen-separated, no leading or trailing hyphen. The slug is the seed key
# and it ends up in a URL, so it is constrained where it is defined rather than checked
# wherever it is used.
Slug = Annotated[
    str, StringConstraints(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=64)
]


class ORMModel(BaseModel):
    """Base for anything read out of a SQLAlchemy row."""

    model_config = ConfigDict(from_attributes=True)


class SeedModel(BaseModel):
    """Base for anything read out of `seeds/*.json`.

    `extra="forbid"` is the point. Without it a typo in a seed file — `target_gramar` —
    is silently dropped, the row loads with an empty list, and the scenario quietly
    stops declaring what it was written to elicit.
    """

    model_config = ConfigDict(extra="forbid")
