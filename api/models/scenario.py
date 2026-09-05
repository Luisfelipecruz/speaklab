"""Scenario wire shapes.

**`persona_prompt` appears in none of them.** It is the system prompt sent to the LLM —
who the persona is, what it wants, and how hard it pushes back — and it is
withheld from the client for two reasons. It is the exercise: a user who reads "the
interviewer should challenge the candidate's timeline twice" is no longer practising the
thing the scenario was built to make them practise. And it is the attack surface: the
persona prompt is the one string in a turn that the user is not supposed to control, so
the less of it that leaves the server, the smaller the target.

Enforced by a test rather than by this note — `test_scenarios.py` asserts the substring
is absent from every response body.
"""

from pydantic import Field

from models.common import CEFRBand, ORMModel, SeedModel, Slug


class RubricCriterion(SeedModel):
    name: str
    descriptor: str


class Rubric(SeedModel):
    """What a good performance looks like, for the end-of-session report.

    Strict here, on the seed path, so a malformed rubric fails `make seed` with a path
    into the JSON. Deliberately *not* strict on the read path — see ScenarioDetail.
    """

    criteria: list[RubricCriterion] = Field(min_length=1)

    # Below this, a session report is an opinion about three sentences. It decides
    # whether a session is worth reporting on at all.
    min_turns: int = Field(ge=1)


class ScenarioSummary(ORMModel):
    """The list row. No prompt, no rubric, no goal — enough to choose from."""

    slug: str
    title: str
    description: str
    category: str
    cefr_band: CEFRBand
    target_grammar: list[str]
    target_functions: list[str]


class ScenarioDetail(ScenarioSummary):
    """One scenario, opened.

    `goal` and `rubric` are shown: telling a learner what finishing looks like and what
    is being assessed is not a spoiler, it is the brief. `persona_prompt` is not,
    because it is the other side of the exercise.

    `rubric` is `dict`, not `Rubric`, on purpose. Strict on write, tolerant on read: a
    row inserted by hand with an incomplete rubric should render imperfectly, not make
    `GET /scenarios/{slug}` return 500. The seed path is where the shape is enforced.
    """

    goal: str
    rubric: dict


class ScenarioSeed(SeedModel):
    """One record in `seeds/scenarios.json`. Every column except `id`."""

    slug: Slug
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    category: str = Field(min_length=1)
    cefr_band: CEFRBand
    persona_prompt: str = Field(min_length=1)
    goal: str = Field(min_length=1)

    # min_length=1 on both, and this is a requirement rather than a nicety. A scenario
    # declares the forms it is designed to elicit, and the eval harness checks whether it
    # actually elicited them. A scenario with no declared forms cannot fail that check,
    # so it would be permanently exempt from the one test that says whether it works.
    target_grammar: list[str] = Field(min_length=1)
    target_functions: list[str] = Field(min_length=1)

    rubric: Rubric
    is_active: bool = True
