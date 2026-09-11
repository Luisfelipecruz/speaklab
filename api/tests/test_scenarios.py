"""Scenario browsing.

The properties worth asserting are not "the endpoint returns rows". They are:

* the filters actually filter, and an unknown band is *rejected* rather than silently
  answered with an empty list;
* `persona_prompt` never leaves the server;
* every seeded scenario declares the forms it is designed to elicit, and the kinds of
  mistake it is built to draw out, because a scenario that declares none can never fail
  the check that it elicited them.
"""

from collections import Counter

import pytest
from sqlalchemy import select

from db_models import Scenario
from models.scenario import ScenarioSeed
from scripts.seed import _load
from services.taxonomy import CATEGORIES, TAXONOMY
from tests.category_labels import CASES

pytestmark = pytest.mark.usefixtures("seeded")


async def test_the_list_returns_the_eleven_seeded_scenarios(client):
    response = await client.get("/scenarios")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 11
    assert {row["slug"] for row in body} == {
        "airport-rebooking",
        "apartment-viewing",
        "courier-directions",
        "daily-standup",
        "doctors-appointment",
        "incident-explanation",
        "job-interview-backend",
        "lost-property-office",
        "restaurant-complaint",
        "sprint-retrospective",
        "training-programme-intake",
    }


async def test_the_list_row_carries_what_a_chooser_needs(client):
    row = (await client.get("/scenarios")).json()[0]

    assert set(row) == {
        "slug",
        "title",
        "description",
        "category",
        "cefr_band",
        "target_grammar",
        "target_functions",
        "target_errors",
    }


async def test_the_list_is_ordered_by_band_then_title(client):
    """An unordered list endpoint returns rows in whatever order Postgres finds them,
    which changes after an UPDATE and reshuffles a UI for no reason the user can see."""
    rows = (await client.get("/scenarios")).json()

    keys = [(row["cefr_band"], row["title"]) for row in rows]
    assert keys == sorted(keys)


async def test_band_filter_returns_only_that_band(client):
    body = (await client.get("/scenarios", params={"band": "B2"})).json()

    assert body
    assert {row["cefr_band"] for row in body} == {"B2"}


async def test_an_unknown_band_is_rejected_not_answered_with_nothing(client):
    """422, not 200 with `[]`.

    An empty list reads as "there are no scenarios at that level", which is a wrong
    answer to a question that was never valid. The closed CEFRBand enum is what makes
    the difference.
    """
    response = await client.get("/scenarios", params={"band": "B7"})

    assert response.status_code == 422


async def test_category_filter_returns_only_that_category(client):
    body = (await client.get("/scenarios", params={"category": "workplace"})).json()

    assert {row["slug"] for row in body} == {"daily-standup", "sprint-retrospective"}


async def test_target_grammar_filter_matches_inside_the_declared_list(client):
    """JSONB containment, not equality — a scenario declaring four forms must match a
    query for any one of them."""
    body = (
        await client.get("/scenarios", params={"target_grammar": "conditional_2"})
    ).json()

    assert {row["slug"] for row in body} == {
        "job-interview-backend",
        "sprint-retrospective",
    }
    for row in body:
        assert "conditional_2" in row["target_grammar"]


async def test_filters_combine_with_and(client):
    body = (
        await client.get("/scenarios", params={"band": "B1", "category": "workplace"})
    ).json()

    assert {row["slug"] for row in body} == {"daily-standup"}


async def test_a_valid_filter_that_matches_nothing_is_an_empty_list_not_a_404(client):
    response = await client.get("/scenarios", params={"category": "underwater-welding"})

    assert response.status_code == 200
    assert response.json() == []


async def test_one_scenario_by_slug(client):
    response = await client.get("/scenarios/job-interview-backend")

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Job interview — backend engineer"
    assert body["goal"]
    assert body["rubric"]["criteria"]
    assert body["rubric"]["min_turns"] >= 1


async def test_an_unknown_slug_is_a_404_that_says_which_slug(client):
    response = await client.get("/scenarios/does-not-exist")

    assert response.status_code == 404
    assert "does-not-exist" in response.json()["detail"]


# ── The persona prompt never leaves the server ──────────────────────────────


async def test_the_persona_prompt_is_absent_from_every_scenario_response(
    client, seeded
):
    """The exercise, and the attack surface.

    A user who reads "push back on something vague at least twice" is no longer
    practising the thing the scenario was built for; and the persona prompt is the one
    string in a turn the user is not supposed to control. Asserted against the real
    prompt text rather than against the key name, so a future response model that
    renames the field does not quietly pass.
    """
    scenario = await seeded.scalar(
        select(Scenario).where(Scenario.slug == "job-interview-backend")
    )
    fragment = scenario.persona_prompt[:60]

    listing = (await client.get("/scenarios")).text
    detail = (await client.get("/scenarios/job-interview-backend")).text

    assert "persona_prompt" not in listing
    assert "persona_prompt" not in detail
    assert fragment not in listing
    assert fragment not in detail


# ── The seed content itself ─────────────────────────────────────────────────


async def test_every_scenario_declares_the_forms_it_should_elicit(seeded):
    """A scenario with an empty `target_grammar` is exempt from the only check that says
    whether it works, which makes it permanently unfalsifiable."""
    scenarios = (await seeded.scalars(select(Scenario))).all()

    for scenario in scenarios:
        assert scenario.target_grammar, f"{scenario.slug} declares no target grammar"
        assert scenario.target_functions, f"{scenario.slug} declares no functions"
        assert scenario.target_errors, f"{scenario.slug} declares no kind of mistake"
        assert set(scenario.target_errors) <= CATEGORIES, scenario.slug


async def test_articles_prepositions_and_false_friends_each_have_a_scenario(client):
    """The three kinds of mistake nothing in the catalogue was written for, each drawn
    out by a scenario of its own, at three different bands."""
    rows = {row["slug"]: row for row in (await client.get("/scenarios")).json()}

    declared = {
        slug: (rows[slug]["target_errors"], rows[slug]["cefr_band"])
        for slug in (
            "lost-property-office",
            "courier-directions",
            "training-programme-intake",
        )
    }
    assert declared == {
        "lost-property-office": (["ARTICLE"], "A2"),
        "courier-directions": (["PREPOSITION"], "B1"),
        "training-programme-intake": (["LEXICAL_CHOICE"], "B2"),
    }


def test_the_labelled_sentences_belong_to_the_scenario_that_draws_them_out():
    """The sentences the three scenarios are measured with are labelled in the taxonomy,
    each with the one mistake it holds, and each in a scenario that declares its kind.
    """
    seeds = {seed.slug: seed for seed in _load("scenarios.json", ScenarioSeed)}

    for case in CASES:
        assert case.category in seeds[case.scenario].target_errors, case.transcript
        assert case.subcategory in TAXONOMY[case.category], case.transcript
        assert case.span_end > case.span_start
        assert case.corrected != case.transcript
    assert Counter(case.category for case in CASES) == {
        "ARTICLE": 20,
        "PREPOSITION": 20,
        "LEXICAL_CHOICE": 20,
    }


async def test_every_persona_prompt_forbids_correcting_the_user(seeded):
    """Correction is the analysers' job, not the persona's.

    A persona that corrects grammar mid-conversation does it badly and
    non-deterministically — and it stops the user speaking. The instruction is in every
    prompt, so it is worth a test rather than a convention.
    """
    scenarios = (await seeded.scalars(select(Scenario))).all()

    for scenario in scenarios:
        assert (
            "never correct their grammar" in scenario.persona_prompt
        ), f"{scenario.slug} does not tell the persona to stay out of the grammar"
