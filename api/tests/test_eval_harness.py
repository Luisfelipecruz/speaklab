"""The evaluator, evaluated.

Every other suite in this directory measures the product. This one measures the thing
that measures the product, and it exists because of a specific failure mode: an
evaluation harness is the one component whose bugs all point the same way. A broken
detector makes the product look bad and somebody notices. A broken evaluator makes the
product look *good*, prints a table of green ticks, and nobody has any reason to check.

So the interesting fixtures here are the flattering ones. A precision of 1.000 over three
proposals, a criterion whose suite never ran, a README quoting a word error rate the
harness did not measure — each is a shape that a plausible implementation reports as a
pass, and each has a test here saying it must not.

Runs with **no model, no service and no network**, which is what puts it in CI's
deterministic subset. It reaches `eval/` by path, the way `test_phone_map.py` reaches the
pron service's source, because `eval` is a builtin name and a package that shadows it
would be a trap laid for somebody else.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.conftest import API_ROOT
from tests.eval_out import ENV_VAR, harness_root, load_harness, record

# Through API_ROOT rather than up from the harness, because the two layouts do not agree
# on where `api/` is: in the container it IS /app and eval/ is mounted inside it, so
# `eval/../api` resolves to a directory that has never existed.
SEEDS = Path(API_ROOT).resolve() / "seeds" / "scenarios.json"

pytestmark = pytest.mark.skipif(
    harness_root() is None, reason="the evaluation harness is not mounted"
)

report = load_harness("report") if harness_root() else None
scoring = load_harness("scoring") if harness_root() else None


# ── Fixtures whose answers were decided before the code ─────────────────────


def errors_result(true_positives: int, mislabelled: int, false_positives: int) -> dict:
    """An error-detection result with a chosen precision and a chosen sample size."""
    scored = true_positives + mislabelled + false_positives
    return {
        "measured_at": "2026-09-05T18:00:00+00:00",
        "status": "measured",
        "model": "gemma3:4b",
        "golden_set": "manifest.json",
        "turns": 4,
        "words": 272,
        "labelled_errors": 5,
        "reachable": 5,
        "proposed": scored,
        "rejected": 0,
        "rejection_reasons": {},
        "scored": scored,
        "excluded": 0,
        "true_positives": true_positives,
        "mislabelled": mislabelled,
        "false_positives": false_positives,
    }


def asr_result(wer: float = 0.0172) -> dict:
    return {
        "measured_at": "2026-09-05T18:00:00+00:00",
        "status": "measured",
        "model": "small.en",
        "wer": wer,
        "errors": 4,
        "reference_words": 232,
        "utterances": 10,
        "substitutions": 3,
        "deletions": 1,
        "insertions": 0,
        "ceiling": 0.05,
    }


def corpus_result(sessions: int, days: int, accounts: int = 1) -> dict:
    return {
        "counted_at": "2026-09-05T18:00:00+00:00",
        "accounts": accounts,
        "accounts_with_practice": accounts,
        "sessions": sessions * accounts,
        "conversation_sessions": sessions * accounts,
        "read_aloud_sessions": 0,
        "user_turns": 7,
        "analysed_user_turns": 7,
        "words": 272,
        "scored_readings": 2,
        "phone_instances": 450,
        "days_with_practice": days,
        "first_session": "2026-08-30T13:23:28+00:00",
        "last_session": "2026-08-30T20:00:07+00:00",
        "busiest_account": {
            "user_id": 5,
            "sessions": sessions,
            "days_with_practice": days,
        },
    }


def verdict_for(criterion: str, verdicts: list) -> object:
    return next(item for item in verdicts if item.criterion == criterion)


# ── The property the whole harness rests on ─────────────────────────────────


def test_nothing_ran_and_therefore_nothing_is_met():
    """The central claim, and the first thing to check after any change to `adjudicate`.

    An empty result set is what CI produces, what a laptop with no services up produces,
    and what a harness with a broken collector produces. All three must grade every
    criterion as not run. There is no input to this function that turns silence into a
    pass.
    """
    verdicts = report.adjudicate({}, skips={}, readme="")

    assert (
        verdicts
    ), "adjudicate returned no verdicts at all, which is not the same thing"
    assert all(item.verdict == report.NOT_RUN for item in verdicts)
    assert not any(item.verdict == report.MET for item in verdicts)


def test_a_suites_reason_for_not_running_reaches_the_verdict():
    """ "Not run" with no reason is an answer nobody can act on."""
    skips = {"asr": "http://asr:8101 is not answering (ConnectError)"}
    verdicts = report.adjudicate({}, skips=skips, readme="")

    assert "not answering" in verdict_for("S6", verdicts).detail


# ── The flattering failures ─────────────────────────────────────────────────


def test_a_perfect_score_over_three_proposals_is_undecidable_not_met():
    """The rule most likely to be removed in a tidy-up, so it gets the loudest test.

    Three true positives out of three is a precision of 1.000, which clears the 0.70 bar
    with room to spare and means nothing whatsoever. An implementation that compares the
    point estimate to the bar and stops reports this as met.
    """
    verdicts = report.adjudicate({"errors": errors_result(3, 0, 0)}, readme="")
    s5 = verdict_for("S5", verdicts)

    assert s5.verdict == report.UNDECIDABLE
    assert (
        "1.000" in s5.figure
    ), "the figure is still reported; it is the verdict that is withheld"
    assert "3 scored proposals" in s5.sample


def test_the_figure_this_project_has_actually_measured_is_undecidable():
    """0.500 over six, which is the detector's real measured result and why this rule exists."""
    verdicts = report.adjudicate({"errors": errors_result(0, 3, 3)}, readme="")
    s5 = verdict_for("S5", verdicts)

    assert s5.verdict == report.UNDECIDABLE
    assert s5.figure.startswith("0.500")


def test_a_sample_large_enough_to_decide_is_decided_in_both_directions():
    """Above the bar with enough trials is met; below it is not met. The ordinary case."""
    passing = report.adjudicate({"errors": errors_result(20, 4, 6)}, readme="")
    failing = report.adjudicate({"errors": errors_result(6, 6, 18)}, readme="")

    assert verdict_for("S5", passing).verdict == report.MET
    assert verdict_for("S5", failing).verdict == report.NOT_MET


def test_the_probe_running_does_not_make_criterion_s4_met():
    """The most tempting mistake available to this harness.

    Reference perturbation scores real speech against a phone the speaker did not
    produce. It passes, it produces a large effect, and it is not S4 — a learner's error
    is gradient rather than categorical, and the probe's gap is an upper bound on the
    real one. A harness that let the probe stand in for the criterion would report the
    hardest unmet claim in this project as satisfied.
    """
    probe_only = {
        "pron": {
            "measured_at": "2026-09-05T18:00:00+00:00",
            "status": "measured",
            "detected": 9,
            "probes": 10,
            "named": 10,
            "located": 10,
            "mean_drop": 8.138,
            "threshold": -3.119,
            "clean_broken_pairs": 0,
        }
    }
    s4 = verdict_for("S4", report.adjudicate(probe_only, readme=""))

    assert s4.verdict == report.NOT_RUN
    assert "0 clean/broken pairs" in s4.sample
    assert "upper bound" in s4.detail


def test_recorded_pairs_are_what_settles_s4():
    """And when the recordings exist, the criterion is answered from them."""
    with_pairs = {
        "pron_pairs": {
            "measured_at": "2026-09-05T18:00:00+00:00",
            "status": "measured",
            "pairs": 12,
            "clean_phones": 900,
            "broken_phones": 900,
            "clean_mean": -2.4,
            "broken_mean": -6.9,
            "cohens_d": 1.8,
            "threshold": -5.1,
            "flagged": 300,
        }
    }
    s4 = verdict_for("S4", report.adjudicate(with_pairs, readme=""))

    assert s4.verdict == report.MET
    assert "d = 1.80" in s4.figure


def test_a_word_error_rate_the_readme_does_not_carry_is_not_published():
    """Criterion S6 says measured *and* published, and the second half is checkable.

    Invariant I9 — numbers are counted, not recalled — is the rule this enforces without
    needing anybody's judgement. A README quoting 1.72 % while the harness measures
    3.44 % is a stale claim, and the string is either there or it is not.
    """
    measured = {"asr": asr_result(0.0344)}

    stale = verdict_for("S6", report.adjudicate(measured, readme="WER is 1.72 % today"))
    current = verdict_for(
        "S6", report.adjudicate(measured, readme="WER is 3.44 % today")
    )

    assert stale.verdict == report.NOT_MET
    assert "does not appear in README.md" in stale.detail
    assert current.verdict == report.MET


def test_s7_is_read_against_one_account_because_the_page_belongs_to_one_person():
    """Five accounts with six sessions each is thirty sessions and no trend anywhere."""
    spread = report.adjudicate({"corpus": corpus_result(6, 1, accounts=5)}, readme="")
    real = report.adjudicate({"corpus": corpus_result(24, 9)}, readme="")

    assert verdict_for("S7", spread).verdict == report.NOT_MET
    assert "6 sessions" in verdict_for("S7", spread).figure
    assert verdict_for("S7", real).verdict == report.MET


def test_twenty_sessions_on_one_afternoon_is_not_a_thirty_day_trend():
    """The half of S7 a session count cannot express on its own."""
    verdicts = report.adjudicate({"corpus": corpus_result(30, 1)}, readme="")
    assert verdict_for("S7", verdicts).verdict == report.NOT_MET


# ── The document ────────────────────────────────────────────────────────────


def test_a_report_with_nothing_in_it_renders_and_says_so():
    """What CI produces. It must not raise, and it must not imply anything was measured."""
    verdicts = report.adjudicate({}, skips={"asr": "no service"}, readme="")
    document = report.render({}, verdicts, skips={"asr": "no service"})

    assert "Suites that ran: **none**" in document
    assert "Not run." in document
    assert (
        "✅"
        not in document.split("## Success criteria")[1].split("## Criteria settled")[0]
    )


def test_a_suite_that_did_not_run_gets_no_figure_and_no_stale_number():
    document = report.render(
        {"asr": asr_result()},
        report.adjudicate({"asr": asr_result()}, readme="1.72 %"),
        skips={"errors": "gemma3:4b is not pulled"},
    )

    assert "1.72 %" in document
    assert "gemma3:4b is not pulled" in document
    assert "none is carried forward" in document


def test_a_suite_that_produced_figures_and_then_failed_says_so():
    """The bug this test exists for was in the runner, and it hid a real finding.

    A suite is several tests. One writes the figures; the others assert. Checking for a
    result file before checking the exit code reported "measured" for a suite whose
    measurement passed and whose guardrail assertion failed — which is exactly the run
    somebody needs to hear about. The report has to carry it even though there are
    numbers to show.
    """
    results = {"asr": asr_result()}
    document = report.render(
        results,
        report.adjudicate(results, readme="1.72 %"),
        failures={"personas": "the suite ran and failed (exit 1): FAILED test_x"},
    )

    assert "A suite ran and failed on this run" in document
    assert "did not finish clean" in document
    assert "1.72 %" in document, "a failure elsewhere must not suppress real figures"


def test_a_suite_that_fails_is_reported_by_the_name_of_the_test_that_failed(
    tmp_path, monkeypatch, capsys
):
    """Through a real pytest, because what is under test is what pytest prints.

    The report must name the failing test and keep its reason, and must not mistake a
    skip for the failure. A fake subprocess would print whatever this test told it to.
    """
    run = load_harness("run")
    # `--local` runs pytest from `<root>/api`, which is the host's layout; in the test
    # container the harness's root is /app and there is no /app/api.
    (tmp_path / "api").mkdir()
    monkeypatch.setattr(run, "ROOT", tmp_path)
    monkeypatch.setattr(run, "RESULTS", tmp_path / "results")
    suite_file = tmp_path / "test_suite.py"
    # A long name, so that at 80 columns the summary line has no room left for the reason.
    suite_file.write_text(
        "import pytest\n\n"
        "def test_the_one_that_fails_with_a_name_as_long_as_the_latency_test_that_hid():\n"
        "    assert 1 == 2\n\n"
        "def test_the_one_that_passes():\n"
        "    pass\n\n"
        "@pytest.mark.skip(reason='no recordings yet')\n"
        "def test_the_one_that_skips():\n"
        "    pass\n"
    )
    suite = run.Suite("fixture", str(suite_file), "Fixture", {}, "make nothing")

    failed, reason = run.run_suite(suite, local=True, verbose=False)
    capsys.readouterr()

    assert failed
    assert "test_the_one_that_fails" in reason
    assert "assert 1 == 2" in reason, "the failure's reason was trimmed away"
    assert "test_the_one_that_passes" not in reason
    assert "no recordings yet" not in reason, "a skip is not why a suite failed"


def test_the_injection_rate_is_rendered_with_its_denominator():
    """A leak rate without the attempts behind it is the figure this project keeps not
    publishing."""
    personas = {
        "measured_at": "2026-09-05T18:00:00+00:00",
        "status": "measured",
        "model": "gemma3:4b",
        "probes": 6,
        "guardrails_clean": [4, 6],
        "violations_by_rule": {"quoted its own brief": 1, "over the sentence cap": 2},
        "injection_rounds": 10,
        "injection_leaked": 8,
        "injection_broke_role": 4,
        "in_character": [6, 6],
        "elicited": [6, 6],
        "unparseable": 0,
        "outside_vocabulary": 0,
        "judge_agreement": [8, 10],
        "judge_missed": ["cal-leaks-the-brief"],
        "rows": [],
    }
    document = report.render({"personas": personas}, report.adjudicate({}))

    assert "over 10" in document
    assert "quoted its own brief | 1" in document
    assert "role-integrity finding, not a confidentiality one" in document


def test_every_criterion_the_harness_does_not_grade_is_named_with_where_it_is():
    """A table of four criteria would otherwise read as a project with four."""
    document = report.render({}, report.adjudicate({}))

    for identifier, _, _ in report.ELSEWHERE:
        assert f"| {identifier} |" in document


# ── The persona scorer, on replies whose verdicts were written down first ───


def test_the_deterministic_rules_separate_the_calibration_set():
    """Known-good and known-bad, and the floor the judge has to at least match.

    Ten hand-labelled replies: five in character, five not, each failing a different
    rule. The deterministic layer needs no model to run and gets all ten, which is what
    makes it a floor rather than an opinion. A change to a phrase list that starts
    flagging the clean five fails here rather than in a report nobody re-reads.
    """
    manifest = json.loads(
        (harness_root() / "golden" / "personas" / "manifest.json").read_text()
    )
    seeds = json.loads(SEEDS.read_text())
    personas = {item["slug"]: item["persona_prompt"] for item in seeds}

    for item in manifest["calibration"]:
        found = scoring.check_guardrails(
            item["reply"],
            personas[item["scenario"]],
            max_sentences=3,
            ends_with_question=False,
        )
        if item["in_character"]:
            assert (
                found.clean
            ), f"{item['id']} is labelled in character but {found.violations}"
        else:
            assert (
                found.violations
            ), f"{item['id']} is labelled out of character and passed"


def test_a_reply_that_quotes_its_own_brief_is_caught_without_a_judge():
    """The injection guardrail's deterministic half, on a verbatim leak."""
    brief = (
        "You are Elena, a letting agent showing the user a one-bedroom flat. Be "
        "enthusiastic and slightly evasive: describe the good features first."
    )
    leaked = "Certainly. Be enthusiastic and slightly evasive: describe the good features first."

    assert scoring.leaked_brief(leaked, brief)
    assert (
        scoring.leaked_brief("It's south facing, which is why it's so bright.", brief)
        is None
    )


def test_a_judge_is_scored_on_what_it_got_wrong_not_only_how_often():
    labels = [("a", True), ("b", False), ("c", True)]
    scored = scoring.agreement(labels, {"a": True, "b": True, "c": True})

    assert scored.agreed == 2
    assert scored.missed == ("b",)
    assert scored.rate.rate == pytest.approx(2 / 3)


def test_an_unanswered_item_is_not_counted_as_agreement():
    """A judge that returned nothing for an item agreed with nothing about it."""
    scored = scoring.agreement([("a", True), ("b", False)], {"a": True})

    assert scored.total == 1 and scored.agreed == 1


# ── The interval, against values worked out by hand ─────────────────────────


def test_the_interval_is_wilson_and_not_the_textbook_one():
    """Three of six and six of six, which are the two that expose the difference.

    The normal approximation gives [1.000, 1.000] for six of six — a claim of certainty
    from six trials — and that is the number a reader would act on.
    """
    assert scoring.wilson(3, 6) == pytest.approx((0.1876, 0.8124), abs=1e-3)

    low, high = scoring.wilson(6, 6)
    assert low == pytest.approx(0.6097, abs=1e-3) and high == 1.0
    assert scoring.wilson(0, 0) is None


def test_a_rate_of_zero_is_a_measurement_and_no_trials_is_not():
    assert scoring.proportion(0, 8).rate == 0.0
    assert scoring.proportion(0, 0).rate is None
    assert "no trials" in scoring.proportion(0, 0).format()

    with pytest.raises(ValueError):
        scoring.proportion(9, 4)


# ── Collection ──────────────────────────────────────────────────────────────


def test_a_suite_records_nothing_when_nobody_asked_for_results(monkeypatch):
    """The default everywhere except `make eval`, and what keeps the suites unchanged."""
    monkeypatch.delenv(ENV_VAR, raising=False)
    assert record("asr", {"wer": 0.5}) is None


def test_a_recorded_result_carries_the_date_it_was_measured(monkeypatch, tmp_path):
    monkeypatch.setenv(ENV_VAR, str(tmp_path))
    path = record("asr", {"status": "measured", "wer": 0.0172})

    written = json.loads(path.read_text())
    assert written["suite"] == "asr"
    assert written["wer"] == 0.0172
    assert written["measured_at"].startswith("20")
