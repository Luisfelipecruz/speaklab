"""What the detector does with a model's answer, without a model in the room.

The provider is a stub returning scripted text, so every case here is about the part this
system owns: what it sends, what it accepts, what it refuses, and what it marks. Whether
`gemma3:4b` is any good at the labelling itself is a different question, measured against
real transcripts in `test_error_precision.py`.
"""

import json

import pytest

from config import ANALYSIS_TEMPERATURE, ASR_CONFIDENCE_FLOOR
from services.errors import INSTRUCTION, detect, low_confidence_spans
from services.taxonomy import CATEGORIES
from tests.conftest import BrokenProvider, StubProvider

TRANSCRIPT = "yesterday I go to the office and I speak with my manager"


def reply(*errors: dict) -> str:
    return json.dumps({"errors": list(errors)})


def an_error(**overrides) -> dict:
    base = {
        "category": "VERB_TENSE",
        "subcategory": "missing_past_marker",
        "original": "I go to the office",
        "correction": "I went to the office",
        "explanation": "Yesterday needs the past simple.",
        "confidence": 0.9,
    }
    base.update(overrides)
    return base


def words(*pairs: tuple[str, float]) -> list[dict]:
    """Word timings whose text joins to a transcript, with the given probabilities."""
    import math

    out, start = [], 0
    for text, probability in pairs:
        out.append(
            {
                "w": text,
                "start_ms": start,
                "end_ms": start + 300,
                "logprob": math.log(probability),
            }
        )
        start += 400
    return out


# ── What is sent ────────────────────────────────────────────────────────────


async def test_the_prompt_carries_every_category_the_taxonomy_has():
    """A model cannot pick from a list it was not given, and a category missing from the
    prompt would show up only as errors of that kind never being found."""
    for category in CATEGORIES:
        assert category in INSTRUCTION


async def test_labelling_asks_for_a_temperature_of_zero():
    """Labelling is a measurement. The same utterance has to produce the same errors on a
    re-run, or re-running a backfill would rewrite a learner's history."""
    provider = StubProvider([reply()])
    await detect(provider, TRANSCRIPT, None)
    assert provider.temperatures == [ANALYSIS_TEMPERATURE]


async def test_the_worked_examples_are_not_drawn_from_the_golden_set():
    """An example taken from the set precision is measured against would be the model
    marking its own homework."""
    import json as _json

    from services.errors import EXAMPLES
    from tests.eval_out import harness_root

    # harness_root() finds eval/ in both the host and the container layout. Both sets are
    # checked, because precision is measured against the local one too.
    root = harness_root()
    golden = root / "golden" / "errors" if root is not None else None
    manifests = [
        golden / name
        for name in ("manifest.json", "manifest.local.json")
        if golden is not None and (golden / name).is_file()
    ]
    if not manifests:
        pytest.skip("the golden set has not been built")
    transcripts = {
        item["transcript"]
        for manifest in manifests
        for item in _json.loads(manifest.read_text())["items"]
    }
    for utterance, _ in EXAMPLES:
        assert utterance not in transcripts


# ── What is accepted ────────────────────────────────────────────────────────


async def test_an_accepted_error_points_at_the_real_text():
    detection = await detect(StubProvider([reply(an_error())]), TRANSCRIPT, None)
    assert len(detection.errors) == 1
    accepted = detection.errors[0].accepted
    assert TRANSCRIPT[accepted.span_start : accepted.span_end] == accepted.original


async def test_an_empty_error_list_is_a_normal_answer():
    """A turn with no mistakes in it is the answer a good speaker gets, and it must not
    look like a failure."""
    detection = await detect(StubProvider([reply()]), TRANSCRIPT, None)
    assert detection.status == "ok"
    assert detection.errors == []
    assert detection.rejected == []


@pytest.mark.parametrize(
    "text",
    [
        '```json\n{"errors": []}\n```',
        '```\n{"errors": []}\n```',
        'Here you are:\n{"errors": []}',
    ],
)
async def test_a_fenced_or_prefaced_answer_is_still_read(text):
    """A model wraps JSON in a fence more often than not. An analysis that failed on
    three backticks would be reporting on the fence rather than on the model."""
    detection = await detect(StubProvider([text]), TRANSCRIPT, None)
    assert detection.status == "ok"


async def test_a_bare_array_is_accepted():
    """The content is exactly right and the wrapper is missing. Counting that as a whole
    unusable turn would throw away good labelling to enforce a brace."""
    detection = await detect(StubProvider([json.dumps([an_error()])]), TRANSCRIPT, None)
    assert len(detection.errors) == 1


# ── What is refused, and counted ────────────────────────────────────────────


async def test_an_out_of_taxonomy_label_is_refused_and_kept():
    """Refusing it is the requirement; keeping it is what makes the refusal a
    measurement rather than a silent drop."""
    detection = await detect(
        StubProvider([reply(an_error(category="SPELLING"))]), TRANSCRIPT, None
    )
    assert detection.errors == []
    assert [r.reason for r in detection.rejected] == ["unknown_category"]
    assert detection.rejection_rate == 1.0


async def test_the_rejection_rate_is_over_everything_proposed():
    """It is the number a decision to change models would be made from, so it has to
    count the proposals that passed as well as the ones that did not."""
    detection = await detect(
        StubProvider(
            [
                reply(
                    an_error(),
                    an_error(category="SPELLING", original="I speak with my manager"),
                )
            ]
        ),
        TRANSCRIPT,
        None,
    )
    assert detection.proposed == 2
    assert detection.rejection_rate == 0.5


async def test_an_invented_location_is_refused():
    """The model quotes; this system finds. A quote that is not in the transcript is a
    location the model made up, and it does not become an underline."""
    detection = await detect(
        StubProvider([reply(an_error(original="I went to the shops"))]),
        TRANSCRIPT,
        None,
    )
    assert [r.reason for r in detection.rejected] == ["original_not_in_transcript"]


async def test_a_reply_that_is_not_json_is_reported_as_such():
    """Salvaging prose into an error list would make "the model labelled nothing" and
    "the model ignored the format" the same result."""
    detection = await detect(
        StubProvider(["I am sorry, I cannot help with that."]), TRANSCRIPT, None
    )
    assert detection.status == "unparseable"
    assert detection.errors == []


async def test_a_model_that_is_down_leaves_the_turn_retryable():
    """Analysis runs behind the conversation and nobody is waiting for it. A provider
    that is down must not take the job with it."""
    detection = await detect(BrokenProvider(), TRANSCRIPT, None)
    assert detection.status == "unavailable"
    assert "LlmUnavailable" in detection.detail


async def test_a_turn_with_no_transcript_is_skipped_rather_than_sent():
    provider = StubProvider([reply()])
    detection = await detect(provider, "   ", None)
    assert detection.status == "skipped"
    assert provider.calls == []


# ── The per-word confidence gate ────────────────────────────────────────────


async def test_the_gate_marks_the_word_and_not_the_turn():
    """The turn score is the mean of the per-word scores, so one badly heard word inside
    a confident turn is averaged away. A turn-level threshold cannot reach it."""
    heard = words(("let's", 0.99), ("look", 0.97), ("department", 0.41), ("here", 1.0))
    transcript = "let's look department here"
    spans = low_confidence_spans(transcript, heard)
    assert [transcript[start:end] for start, end in spans] == ["department"]


async def test_an_error_on_a_doubtful_word_is_kept_and_marked():
    """Deleting it would leave a transcript with a hole in it; counting it would let a
    mishearing move an accuracy trend. So it is shown, and marked."""
    transcript = "let's look department here"
    heard = words(("let's", 0.99), ("look", 0.97), ("department", 0.41), ("here", 1.0))
    detection = await detect(
        StubProvider(
            [
                reply(
                    an_error(
                        category="PREPOSITION",
                        subcategory="missing",
                        original="look department",
                        correction="look at the apartment",
                    )
                )
            ]
        ),
        transcript,
        heard,
    )
    assert len(detection.errors) == 1
    assert detection.errors[0].asr_suspect


async def test_an_error_clear_of_every_doubtful_word_is_not_marked():
    transcript = "let's look department here"
    heard = words(("let's", 0.99), ("look", 0.97), ("department", 0.41), ("here", 1.0))
    detection = await detect(
        StubProvider(
            [
                reply(
                    an_error(
                        category="PRONOUN",
                        subcategory="omitted_subject",
                        original="let's look",
                        correction="let us look",
                    )
                )
            ]
        ),
        transcript,
        heard,
    )
    assert not detection.errors[0].asr_suspect


async def test_the_gate_is_read_from_the_configured_floor():
    transcript = "one two"
    just_under = words(("one", ASR_CONFIDENCE_FLOOR - 0.01), ("two", 0.99))
    just_over = words(("one", ASR_CONFIDENCE_FLOOR + 0.01), ("two", 0.99))
    assert low_confidence_spans(transcript, just_under)
    assert not low_confidence_spans(transcript, just_over)


async def test_words_that_do_not_line_up_with_the_transcript_are_skipped():
    """A span in the wrong place would mark a correct error as doubtful. Better to miss
    a marker than to move one."""
    transcript = "a completely different sentence"
    heard = words(("nothing", 0.2), ("matches", 0.2))
    assert low_confidence_spans(transcript, heard) == []


# ── The rule layer beside the model ─────────────────────────────────────────

AGREEING = "my sister work in a bank near the station"


def ruled(text: str):
    from services import grammar, rules

    return rules.propose(grammar.parse(text))


def agreement_error(**overrides) -> dict:
    return an_error(
        **{
            "category": "SUBJECT_VERB_AGREEMENT",
            "subcategory": "third_person_s",
            "original": "my sister work",
            "correction": "my sister works",
            **overrides,
        }
    )


async def test_a_rule_proposal_is_stored_as_the_rules():
    detection = await detect(StubProvider([reply()]), AGREEING, None, ruled(AGREEING))
    assert [(e.detector, e.accepted.correction) for e in detection.errors] == [
        ("rule", "my sister works")
    ]


async def test_a_rule_proposal_does_not_wait_for_the_model():
    """The rule layer needs no model, so a model that is down costs the model's half of
    the labelling and nothing else."""
    detection = await detect(BrokenProvider(), AGREEING, None, ruled(AGREEING))
    assert detection.status == "unavailable"
    assert [e.detector for e in detection.errors] == ["rule"]


async def test_the_models_copy_of_a_rule_correction_is_superseded_not_stored():
    """One mistake, proposed by both detectors, is one row. The model's copy is kept apart
    rather than dropped, because it is still something the model proposed."""
    detection = await detect(
        StubProvider([reply(agreement_error())]), AGREEING, None, ruled(AGREEING)
    )
    assert [e.detector for e in detection.errors] == ["rule"]
    assert [e.accepted.original for e in detection.superseded] == ["my sister work"]


async def test_a_mislabelled_copy_is_superseded_too():
    """The model's commonest failure: the right words, the right correction, the wrong
    category. The rule's category is decidable, so the rule's row is the one kept."""
    mislabelled = agreement_error(
        category="VERB_TENSE",
        subcategory="wrong_progressive_aspect",
        original="sister work in a bank",
        correction="sister works in a bank",
    )
    detection = await detect(
        StubProvider([reply(mislabelled)]), AGREEING, None, ruled(AGREEING)
    )
    assert [e.detector for e in detection.errors] == ["rule"]
    assert len(detection.superseded) == 1


async def test_a_different_mistake_in_the_same_words_is_kept():
    """Overlapping a rule's span is not the same claim. "in a bank" corrected to "at a
    bank" is about a preposition, and the rule said nothing about it."""
    preposition = an_error(
        category="PREPOSITION",
        subcategory="wrong",
        original="work in a bank",
        correction="work at a bank",
    )
    detection = await detect(
        StubProvider([reply(preposition)]), AGREEING, None, ruled(AGREEING)
    )
    assert sorted(e.detector for e in detection.errors) == ["llm", "rule"]
    assert detection.superseded == []


async def test_a_superseded_proposal_is_not_a_refusal():
    """The rejection rate says whether the model can do the labelling. A proposal that
    passed the gate and lost to a rule making the same correction is not a failure of
    the model, and must not move that rate."""
    from services.errors import SUPERSEDED

    detection = await detect(
        StubProvider([reply(agreement_error())]), AGREEING, None, ruled(AGREEING)
    )
    assert detection.rejected == []
    assert detection.proposed == 1
    assert detection.rejection_rate == 0.0
    assert [record["reason"] for record in detection.not_stored()] == [SUPERSEDED]


async def test_the_rules_are_not_counted_as_proposals_by_the_model():
    detection = await detect(StubProvider([reply()]), AGREEING, None, ruled(AGREEING))
    assert detection.proposed == 0
    assert detection.rejection_rate is None


async def test_a_rule_proposal_on_a_doubtful_word_is_marked():
    """The per-word gate is not the model's: a recogniser that dropped an -s produces
    exactly the text an agreement error does, so a rule row on a doubtful word is kept
    out of the rates like any other."""
    heard = words(
        ("my", 0.99),
        ("sister", 0.98),
        ("work", 0.3),
        ("in", 0.99),
        ("a", 0.99),
        ("bank", 0.99),
        ("near", 0.99),
        ("the", 0.99),
        ("station", 0.99),
    )
    detection = await detect(StubProvider([reply()]), AGREEING, heard, ruled(AGREEING))
    assert detection.errors[0].asr_suspect
