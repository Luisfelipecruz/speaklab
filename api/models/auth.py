"""Wire shapes for registration, login and the profile.

The rule this module exists to enforce is one line long: **`password_hash` appears in no
response model.** It is the same discipline as `scenarios.persona_prompt` in
`models/scenario.py` — a column that is loaded on every query and serialised by nothing —
and it is enforced the same way, by there being no field for it to land in rather than by
remembering to exclude it. `tests/test_auth.py` asserts it against every auth response.

Passwords are constrained at both ends. A floor because eight characters is the least
that is worth calling a password, and a ceiling because the request body is attacker-
controlled and Argon2 asks for 64 MiB per hash: without a cap, a one-megabyte password
field is a cheap way to make the server work hard. Argon2 has no 72-byte truncation
problem of its own — that is bcrypt — so 128 is a resource limit, not a correctness one.
"""

from datetime import datetime
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    model_validator,
)

from models.common import CEFRBand, ORMModel

# ISO 639-1, optionally with a region: `es`, `pt-BR`. Constrained where it is defined
# rather than checked where it is used, like `Slug`. It selects the L1 phoneme priors at
# m8 (PRD §7.4, FR-3), so a free-text language field would mean a prior keyed on
# "Spanish", "spanish" and "es" as three different first languages.
LanguageCode = Annotated[
    str, StringConstraints(pattern=r"^[a-z]{2}(-[A-Z]{2})?$", max_length=5)
]

Password = Annotated[str, Field(min_length=8, max_length=128)]


class RegisterRequest(BaseModel):
    """FR-1 and FR-3 in one body.

    Native language is captured here rather than being offered later in a settings page
    because m8 needs it to say anything useful the first time, and a preference nobody
    is ever prompted for is a column full of defaults.
    """

    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: Password
    native_language: LanguageCode = "es"
    cefr_self_assessed: CEFRBand | None = None


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str


class ProfileUpdate(BaseModel):
    """PATCH /auth/me. Every field optional, but not all of them absent.

    `extra="forbid"` matters more here than anywhere else in the file: a PATCH that
    silently ignores `retain_audioo` returns 200 with the old value, and the user is
    told their audio will be deleted while it is being kept. FR-26 is a promise about
    data, so the endpoint that changes it fails loudly or not at all.
    """

    model_config = ConfigDict(extra="forbid")

    native_language: LanguageCode | None = None
    cefr_self_assessed: CEFRBand | None = None
    retain_audio: bool | None = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> "ProfileUpdate":
        if not self.model_fields_set:
            raise ValueError("supply at least one field to update")
        return self


class UserProfile(ORMModel):
    """What the account looks like from outside. No hash, by construction."""

    id: int
    email: EmailStr
    native_language: str
    cefr_self_assessed: str | None
    retain_audio: bool
    created_at: datetime
