"""The OpenAPI document reads as documentation: every operation says what it does, and
every section says what it is for.

`/docs` is what a reader opens after the README, and FastAPI's defaults there are a
function name per operation and not a word about any section. These tests read the
document the running app serves, so an operation added without a docstring is named here.
"""

from main import api_routes, app

SCHEMA = app.openapi()
OPERATIONS = [
    (method.upper(), path, operation)
    for path, item in SCHEMA["paths"].items()
    for method, operation in item.items()
]


def test_the_route_walk_finds_every_operation_the_document_lists():
    """The walk the tests here and in test_ownership.py loop over, checked against what the
    app actually serves. A walk that found nothing would let every loop over it pass
    without asserting anything."""
    walked = {
        (method, route.path)
        for route in api_routes()
        for method in route.methods - {"HEAD", "OPTIONS"}
    }

    assert walked == {(method, path) for method, path, _ in OPERATIONS}


def test_every_operation_has_a_description():
    missing = [f"{m} {p}" for m, p, op in OPERATIONS if not op.get("description")]

    assert missing == []


def test_every_summary_is_a_sentence_about_the_operation_not_its_function_name():
    for route in api_routes():
        default = route.name.replace("_", " ").title()
        assert route.summary, route.path
        assert route.summary != default, route.path
        assert len(route.summary) <= 90, (route.path, route.summary)


def test_every_section_an_operation_is_filed_under_is_described():
    described = {tag["name"]: tag.get("description") for tag in SCHEMA.get("tags", [])}
    used = {tag for _, _, op in OPERATIONS for tag in op.get("tags", [])}

    assert used <= set(described), used - set(described)
    assert all(described[tag] for tag in used)
    assert not [f"{m} {p}" for m, p, op in OPERATIONS if not op.get("tags")]
