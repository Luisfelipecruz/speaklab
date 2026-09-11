"""Turning collected measurements into `docs/evaluation.md`, and into verdicts.

Two jobs, and the second one is the reason this file exists separately from `run.py`.

**Rendering** is the obvious half: results in, markdown out.

**Adjudication** is the half worth reviewing. Somebody has to decide whether 0.500
detection precision over six proposals means criterion S5 is failed, and the answer is
that it means nothing at all — six trials cannot place a figure against a 0.70 bar in
either direction. Getting that wrong in the generous direction is how an evaluation
harness becomes a machine for producing green ticks, so the rule is written here, in one
pure function, and `api/tests/test_eval_harness.py` feeds it fixtures whose verdicts are
known and checks it produces them.

Three rules govern every verdict, in this order:

1. **No result, no verdict.** A suite that did not run produces `not run`. There is no
   input to this module that makes a missing measurement into a met criterion, because
   the code that would write a result never executed. This is checked by a test that
   passes an empty dictionary and asserts nothing comes back met.
2. **Too few trials, no verdict.** Below `scoring.DECIDABLE_TRIALS` the answer is
   `undecidable` — *including when the figure is above the bar*. A precision of 1.000
   over three proposals is three proposals. This is the rule that would be quietly
   dropped in a tidy-up, so it has its own test with a passing-looking fixture.
3. **Otherwise, compare.** And print the interval beside the point estimate, always.

Pure and dependency-free on purpose: it runs on the host, where the only thing installed
is Python.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import scoring  # noqa: E402

MET = "met"
NOT_MET = "not met"
UNDECIDABLE = "undecidable"
NOT_RUN = "not run"

MARK = {MET: "✅", NOT_MET: "❌", UNDECIDABLE: "◐", NOT_RUN: "—"}

# The precision bar S5 states. Here rather than in the comparison so that a reader of the
# report and a reader of this file are looking at the same number.
S5_PRECISION_BAR = 0.70

# S7's bar, and the second half of it that a session count alone cannot express: twenty
# sessions on one afternoon is not a thirty-day trend.
S7_SESSION_BAR = 20
S7_DAY_BAR = 3


@dataclass(frozen=True)
class Verdict:
    criterion: str
    statement: str
    verdict: str
    figure: str = "—"
    sample: str = "—"
    detail: str = ""

    @property
    def mark(self) -> str:
        return MARK[self.verdict]


@dataclass
class Report:
    verdicts: list[Verdict] = field(default_factory=list)
    results: dict = field(default_factory=dict)
    skips: dict = field(default_factory=dict)


def _missing(criterion: str, statement: str, suite: str, skips: dict) -> Verdict:
    reason = skips.get(suite) or f"the {suite} suite produced no result"
    return Verdict(criterion, statement, NOT_RUN, detail=reason)


def _s4(results: dict, skips: dict) -> Verdict:
    statement = (
        "GOP separates deliberately mispronounced from correctly pronounced recordings "
        "of the same passage, with the gap reported as a measured effect size"
    )
    pairs = results.get("pron_pairs")
    if pairs:
        clean, broken = pairs["clean_mean"], pairs["broken_mean"]
        return Verdict(
            "S4",
            statement,
            MET if pairs["cohens_d"] and pairs["cohens_d"] > 0 else NOT_MET,
            figure=f"d = {pairs['cohens_d']:.2f}, clean {clean:+.2f} vs broken {broken:+.2f}",
            sample=f"{pairs['pairs']} pairs, {pairs['broken_phones']} broken phones",
        )

    probe = results.get("pron")
    if probe is None:
        return _missing("S4", statement, "pron", skips)

    # The probe ran and S4 still has no answer, which is a distinction the report has to
    # keep. Reference perturbation scores real speech against a phone the speaker did not
    # produce; a learner error is gradient, and the 8-nat gap is an upper bound on it.
    # Reporting the probe as if it were S4 is the single most tempting mistake available
    # to this harness.
    return Verdict(
        "S4",
        statement,
        NOT_RUN,
        figure="—",
        sample=f"{probe.get('clean_broken_pairs', 0)} clean/broken pairs recorded",
        detail=(
            "The reference-perturbation probe ran and passed; that is an upper bound on "
            "separation, not this criterion. S4 needs the same passage read twice by the "
            "same speaker in the same sitting, once correctly and once with the marked "
            "words mispronounced. See eval/golden/pron/README.md for the protocol."
        ),
    )


def _s5(results: dict, skips: dict) -> Verdict:
    statement = (
        "Error detection scores at least "
        f"{S5_PRECISION_BAR:.2f} precision on the golden set of hand-labelled turns"
    )
    errors = results.get("errors")
    if errors is None:
        return _missing("S5", statement, "errors", skips)

    scored = errors["scored"]
    hits = errors["true_positives"] + errors["mislabelled"]
    rate = scoring.proportion(hits, scored)
    figure = rate.format() if scored else "n/a (nothing scored)"
    sample = (
        f"{errors['turns']} turns, {errors['words']} words, "
        f"{errors['labelled_errors']} labelled errors, {scored} scored proposals"
    )

    if scored == 0:
        return Verdict(
            "S5", statement, NOT_RUN, figure, sample, "no proposal was scored"
        )
    if rate.undecidable:
        return Verdict(
            "S5",
            statement,
            UNDECIDABLE,
            figure,
            sample,
            (
                f"{scored} scored proposals cannot place a figure against "
                f"{S5_PRECISION_BAR:.2f} in either direction. The interval above spans "
                "most of the scale. This is not a hedge — it is what "
                f"{scoring.DECIDABLE_TRIALS} trials would be needed to avoid."
            ),
        )
    return Verdict(
        "S5",
        statement,
        MET if rate.rate >= S5_PRECISION_BAR else NOT_MET,
        figure,
        sample,
    )


def _s6(results: dict, skips: dict, readme: str = "") -> Verdict:
    statement = "ASR word error rate on the golden set is measured and published"
    asr = results.get("asr")
    if asr is None:
        return _missing("S6", statement, "asr", skips)

    percent = f"{asr['wer'] * 100:.2f}"
    figure = f"{percent} % ({asr['errors']}/{asr['reference_words']} words)"
    sample = f"{asr['utterances']} utterances, {asr['reference_words']} reference words"

    # The criterion is "measured and published", and the second half is checkable. A
    # A README quoting a figure the harness cannot reproduce is the exact thing the
    # count-it-do-not-recall-it rule exists to catch, and catching it needs no judgement:
    # the string is there or it is not.
    if readme and percent not in readme:
        return Verdict(
            "S6",
            statement,
            NOT_MET,
            figure,
            sample,
            (
                f"measured {percent} %, which does not appear in README.md. The number "
                "is measured but not published, or published stale."
            ),
        )
    return Verdict("S6", statement, MET, figure, sample)


def _s7(results: dict, skips: dict) -> Verdict:
    statement = (
        "The progress page renders 30-day trends for all four metric families from "
        f"at least {S7_SESSION_BAR} real sessions"
    )
    corpus = results.get("corpus")
    if corpus is None:
        return _missing("S7", statement, "corpus", skips)

    busiest = corpus.get("busiest_account") or {}
    sessions = busiest.get("sessions", 0)
    days = busiest.get("days_with_practice", 0)
    figure = f"{sessions} sessions on {days} calendar day{'' if days == 1 else 's'}"
    sample = (
        f"{corpus['sessions']} sessions across {corpus['accounts_with_practice']} "
        f"accounts; {corpus['analysed_user_turns']} analysed turns, "
        f"{corpus['words']} words, {corpus['scored_readings']} scored readings"
    )

    # Read against one account rather than the total, because the progress page belongs
    # to one person. Five accounts with four sessions each is twenty sessions and no
    # trend on anybody's screen.
    if sessions >= S7_SESSION_BAR and days >= S7_DAY_BAR:
        return Verdict("S7", statement, MET, figure, sample)
    return Verdict(
        "S7",
        statement,
        NOT_MET,
        figure,
        sample,
        (
            "Counted against the best-provisioned account, because the progress page is "
            "per-user. A trend also needs more than one day: a period is a point, and "
            "no direction is claimed below three of them."
        ),
    )


def adjudicate(
    results: dict, skips: dict | None = None, readme: str = ""
) -> list[Verdict]:
    """Every criterion this harness can settle, and nothing it cannot."""
    skips = skips or {}
    return [
        _s4(results, skips),
        _s5(results, skips),
        _s6(results, skips, readme),
        _s7(results, skips),
    ]


# Criteria the harness deliberately does not grade, and where each is settled instead.
# Listed in the report because a criteria table with four rows and no explanation reads
# as a project with four criteria.
ELSEWHERE = (
    (
        "S1",
        "Clean clone reaches all-healthy with no manual editing",
        "a person, on a clean clone",
    ),
    (
        "S2",
        "10-turn conversation end to end, p95 turn latency ≤ 3 s",
        "`make turn-latency`",
    ),
    (
        "S3",
        "Read-aloud returns per-phoneme GOP within 10 s",
        "`make pron-golden`, latency test",
    ),
    (
        "S8",
        "Recommendations state a measured reason traceable to a stored metric",
        "`api/tests/test_recommend.py`",
    ),
    ("S9", "Test suite green in-container; count matches the README", "`make test`"),
    (
        "S10",
        "Every claim in the README is counted, not recalled",
        "this document, and m12",
    ),
)


# ── Rendering ───────────────────────────────────────────────────────────────


def _fmt(value, places: int = 3, dash: str = "—") -> str:
    if value is None:
        return dash
    if isinstance(value, float):
        return f"{value:.{places}f}"
    return str(value)


def _suite_heading(name: str, title: str, results: dict, skips: dict) -> list[str]:
    lines = [f"### {title}", ""]
    result = results.get(name)
    if result is None:
        lines += [
            f"**Not run.** {skips.get(name, 'no result was produced')}",
            "",
            "No figure is reported for a suite that did not run, and none is carried "
            "forward from a previous run. A stale number under a fresh date is worse "
            "than no number.",
            "",
        ]
        return lines
    lines += [f"Measured {result['measured_at']}.", ""]
    return lines


def _asr_section(results: dict, skips: dict) -> list[str]:
    lines = _suite_heading(
        "asr", "Speech recognition — word error rate", results, skips
    )
    asr = results.get("asr")
    if asr is None:
        return lines
    lines += [
        f"| {asr['model']} | |",
        "|---|---|",
        f"| Word error rate | **{asr['wer'] * 100:.2f} %** |",
        f"| Errors / reference words | {asr['errors']} / {asr['reference_words']} |",
        f"| Substitutions, deletions, insertions | {asr['substitutions']}, "
        f"{asr['deletions']}, {asr['insertions']} |",
        f"| Utterances | {asr['utterances']} |",
        f"| Ceiling this suite asserts | {asr['ceiling'] * 100:.0f} % |",
        "",
        f"One word is {100 / asr['reference_words']:.2f} % of this figure. It separates a "
        "working pipeline from a broken one and `small.en` from `tiny.en`; it does not "
        "rank two configurations a few errors apart.",
        "",
    ]
    return lines + _drill(results.get("drill"))


def _drill(drill: dict | None) -> list[str]:
    """Whether a mistake said aloud reaches the transcript, as the spoken drill reads it."""
    if drill is None:
        return []
    sentences = drill["sentences"]
    said, corrected = drill["spoken_as_said"], drill["spoken_as_corrected"]
    lines = [
        "#### A mistake said aloud: heard, or repaired",
        "",
        f"Measured {drill['measured_at']}, `{drill['model']}` hearing the voice "
        f"`{drill['voice']}`: {sentences} hand-labelled learner sentences, each spoken as "
        "the learner said it and as corrected, and compared the way the spoken drill "
        "compares a learner saying it again — what was heard where the correction belongs.",
        "",
        "| Spoken | Heard as the correction | Heard as said | Something else | Nothing |",
        "|---|---|---|---:|---:|",
    ]
    for name, counts in (("With the mistake", said), ("Corrected", corrected)):
        lines.append(
            f"| {name} | {scoring.proportion(counts['corrected'], sentences).format()} | "
            f"{scoring.proportion(counts['original'], sentences).format()} | "
            f"{counts['other']} | {counts['unheard']} |"
        )
    repaired = [
        item
        for item in drill.get("unexpected", [])
        if item["spoken_as"] == "said" and item["verdict"] == "corrected"
    ]
    lines += [
        "",
        "A mistake heard as the correction is the drill's blind spot: the learner said it "
        "wrong and the drill would show it right. One clear synthetic voice gives the "
        "recogniser the most to go on, so this is the rate for the clearest speech there "
        "is, not for a learner's.",
        "",
    ]
    if repaired:
        lines += ["Heard as the correction:", ""]
        lines += [f"- `{item['spoken']}` → `{item['heard']}`" for item in repaired]
        lines.append("")
    return lines


def _pron_section(results: dict, skips: dict) -> list[str]:
    lines = _suite_heading(
        "pron", "Pronunciation — goodness of pronunciation", results, skips
    )
    pron = results.get("pron")
    if pron is None:
        return lines
    lines += [
        "| Reference perturbation probe | |",
        "|---|---|",
        f"| Detected below the clean 5th percentile | **{pron['detected']}/{pron['probes']}** |",
        f"| Competing phone named | {pron['named']}/{pron['located']} |",
        f"| Mean GOP drop | {_fmt(pron['mean_drop'], 3)} nats |",
        f"| Detection threshold (5th pctile of clean) | {_fmt(pron['threshold'], 3)} |",
        "",
        "**This is not criterion S4.** The probe scores real human speech against text "
        "containing a phone the speaker did not produce — a categorically different "
        "sound. A learner's error is gradient: a retracted /s/, an unreleased final "
        "stop. The gap above is an upper bound on what separation is achievable, and S4 "
        "asks for the real one.",
        "",
        f"Clean/broken pairs recorded: **{pron.get('clean_broken_pairs', 0)}**.",
        "",
    ]
    return lines


def _errors_section(results: dict, skips: dict) -> list[str]:
    lines = _suite_heading(
        "errors", "Error detection — precision against hand labels", results, skips
    )
    errors = results.get("errors")
    if errors is not None:
        lines += _golden_errors(errors)
    lines += _planted_errors(results.get("rules"))
    lines += _form_join(results.get("forms"))
    return lines


def _golden_errors(errors: dict) -> list[str]:
    scored = errors["scored"]
    hits = errors["true_positives"] + errors["mislabelled"]
    detection = scoring.proportion(hits, scored)
    labelling = scoring.proportion(errors["true_positives"], scored)
    recall = scoring.proportion(hits, errors["reachable"])
    detectors = errors.get("by_detector")
    # A result written before the rule layer existed has one detector, and its figures
    # are the model's.
    who = f"{errors['model']} and the rule layer" if detectors else errors["model"]
    lines = [
        f"| {who} on `{errors['golden_set']}` | |",
        "|---|---|",
        f"| Detection precision | **{detection.format()}** |",
        f"| Labelling precision | {labelling.format()} |",
        f"| Detection recall | {recall.format()} |",
        f"| Turns / words | {errors['turns']} / {errors['words']} |",
        f"| Labelled errors, clear of the confidence gate | "
        f"{errors['labelled_errors']}, {errors['reachable']} |",
        f"| Model proposals, rejected by the taxonomy | {errors['proposed']}, "
        f"{errors['rejected']} |",
        f"| Scored, excluded as unknowable | {scored}, {errors['excluded']} |",
        f"| True positives / right span wrong label / false positives | "
        f"{errors['true_positives']} / {errors['mislabelled']} / "
        f"{errors['false_positives']} |",
        "",
        f"Rejection reasons: `{errors['rejection_reasons'] or '{}'}`.",
        "",
    ]
    if detectors:
        lines += [
            "The figures above are the product's — what a learner is shown, and what "
            "S5 is graded on. Each detector on its own, with the model scored on "
            "everything it proposed including what a rule superseded, so that its "
            "figure is its own:",
            "",
            "| | Scored | Detection precision | Labelling precision | TP / wrong "
            "label / FP | Excluded |",
            "|---|---:|---|---|---|---:|",
        ]
        for name, key in (
            (f"`{errors['model']}` alone", "llm"),
            ("Rules alone", "rule"),
        ):
            tally = detectors[key]
            found = tally["true_positives"] + tally["mislabelled"]
            lines.append(
                f"| {name} | {tally['scored']} | "
                f"{scoring.proportion(found, tally['scored']).format()} | "
                f"{scoring.proportion(tally['true_positives'], tally['scored']).format()}"
                f" | {tally['true_positives']} / {tally['mislabelled']} / "
                f"{tally['false_positives']} | {tally['excluded']} |"
            )
        lines += [
            "",
            f"Model proposals superseded by a rule making the same correction: "
            f"{errors.get('superseded', 0)}.",
            "",
            "The model's finding has been stable since it was first measured: it finds "
            "roughly the right words and files them under the wrong category. The rule "
            "layer decides the category for the two errors a parse can settle — "
            "agreement and a missing article — and this golden set holds almost none of "
            "either, so on it the layer can say little. The planted errors below are "
            "what it can be judged on until a learner makes more of them.",
            "",
        ]
    else:
        lines += [
            "The gap between detection and labelling precision is the finding, and it "
            "has been stable since the detector was built: it finds roughly the right "
            "words and files them under the wrong category. That is a job for a rule "
            "layer or a second classifying pass, not for a larger model — `mistral:7b` "
            "measured worse.",
            "",
        ]
    return lines


def _planted_errors(rules: dict | None) -> list[str]:
    """The rule layer on native English with one error planted at a time. No model."""
    if rules is None:
        return []
    labels = {"agreement": "Subject–verb agreement", "article": "Missing article"}
    lines = [
        "#### The rule layer on planted errors",
        "",
        f"Measured {rules['measured_at']}, with no model: the repository's native "
        f"English — {rules['texts']} texts, {rules['words']} words — with one verb put "
        "out of agreement or one indefinite article removed at a time, and each copy "
        "given to the rules.",
        "",
        "| | Planted | Caught | Wrong fix | Missed | Proposed elsewhere |",
        "|---|---:|---|---:|---:|---:|",
    ]
    for family, counts in rules["planted"].items():
        planted = counts.get("planted", 0)
        caught = scoring.proportion(counts.get("caught", 0), planted)
        lines.append(
            f"| {labels.get(family, family)} | {planted} | {caught.format()} | "
            f"{counts.get('wrong_fix', 0)} | {counts.get('missed', 0)} | "
            f"{counts.get('elsewhere', 0)} |"
        )
    lines += [
        "",
        "A planted error sits in otherwise clean English, so this is an upper bound on "
        "what the layer catches in a learner's speech, where the parse is worse. What it "
        "does settle is that when the layer speaks it is right: a wrong fix, or a "
        "proposal away from the planted error, would be a false one stated with full "
        "confidence. The article rule covers two shapes on purpose — a noun after `be` "
        "with a pronoun subject, and a role after `as`: everywhere else, whether a bare "
        "noun is missing its article depends on whether it can be counted, which a parse "
        "cannot say.",
        "",
    ]
    return lines


def _form_join(forms: dict | None) -> list[str]:
    """How often a correction is filed under the verb forms a teacher would name. No model."""
    if forms is None:
        return []
    names = {
        "labelled": "Development set — the join was built against it",
        "held_out": "Held out — never changed the join",
        "golden": f"Golden set, `{forms.get('golden_set')}` — real learner turns",
    }
    lines = [
        "#### Which verb form a correction was made in",
        "",
        f"Measured {forms['measured_at']}, with no model: hand-labelled corrections, each "
        "with the form its words were said in and the form it needs, given to the join "
        "that accuracy per form is computed from.",
        "",
        "| | Corrections | Both forms right | One side found | Wrong form |",
        "|---|---:|---|---:|---:|",
    ]
    for name, counts in forms["sets"].items():
        exact = scoring.proportion(counts.get("exact", 0), counts.get("cases", 0))
        lines.append(
            f"| {names.get(name, name)} | {counts.get('cases', 0)} | {exact.format()} | "
            f"{counts.get('partial', 0)} | {counts.get('wrong', 0)} |"
        )
    lines += [
        "",
        "A side the join cannot find is a verb the parser lost, commonest in an "
        "unpunctuated transcript; that side is left out of accuracy per form rather "
        "than guessed. A wrong form would count a mistake against a form the learner "
        "did not get wrong, and the suite fails on one.",
        "",
    ]
    return lines


def _personas_section(results: dict, skips: dict) -> list[str]:
    lines = _suite_heading(
        "personas",
        "Persona adherence — character, and the judge that grades it",
        results,
        skips,
    )
    personas = results.get("personas")
    if personas is None:
        return lines

    guardrails = scoring.proportion(*personas["guardrails_clean"])
    character = scoring.proportion(*personas["in_character"])
    elicited = scoring.proportion(*personas["elicited"])
    judge = scoring.proportion(*personas["judge_agreement"])
    rounds = personas.get("injection_rounds", 0)
    attempts = personas.get("injection_attempts", rounds)
    leaked = personas.get("injection_leaked", 0)
    injection = scoring.proportion(leaked, attempts)
    # A result file written before descriptions were counted has quoting as its only
    # way of giving the instructions away.
    gave_away = scoring.proportion(
        personas.get("injection_gave_away", leaked), attempts
    )
    described = scoring.proportion(personas.get("injection_described", 0), attempts)
    stepped = scoring.proportion(personas.get("injection_broke_role", 0), attempts)
    phrasings = personas.get("injections") or []
    scenarios = len({row["scenario"] for row in phrasings}) or 1
    phrasing_rows = [
        f"| `{row['probe']}` | {row['scenario']} "
        f"| {row.get('gave_away', row['leaked'])} of {row['attempts']} "
        f"| {row['leaked']} | {row.get('described', 0)} | {row['broke_role']} |"
        for row in phrasings
    ]
    by_rule = personas.get("violations_by_rule") or {}
    rule_rows = [
        f"| {rule} | {count} |" for rule, count in sorted(by_rule.items())
    ] or ["| — | every reply was clean |"]
    lines += [
        f"| {personas['model']} | |",
        "|---|---|",
        f"| Replies clean on every deterministic rule | **{guardrails.format()}** |",
        f"| Judged in character | {character.format()} |",
        f"| Judged to invite the declared grammar | {elicited.format()} |",
        f"| Unparseable judgements | {personas['unparseable']} |",
        f"| Forms named outside the closed list | {personas['outside_vocabulary']} |",
        "",
        "Which rules were broken, and by how many of the "
        f"{personas['probes']} replies:",
        "",
        "| Rule | Replies |",
        "|---|---|",
        *rule_rows,
        "",
        f"**The judge, measured against hand labels: {judge.format()}.** "
        + (
            f"It got these wrong: `{personas['judge_missed']}`."
            if personas["judge_missed"]
            else "It agreed with every one."
        ),
        "",
        "Read the judge's line before the two judged rates above it. Ten replies chosen "
        "to be obvious are a floor, not a validation — a judge that clears them has "
        "shown only that it is not broken. It is the one place in this system where a "
        "language model produces a number, and the exemption holds because nothing here "
        "reaches a learner's chart, which is the line a language model does not cross "
        "here.",
        "",
        "The deterministic rules — sentence cap, placeholder names, commentary on the "
        "speaker's English, stepping out of role, quoting its own brief — need no judge "
        "at all, which is why they are reported first.",
        "",
        "#### An instruction spoken inside the scene",
        "",
        f"Asked to step outside the scene and give its instructions away, "
        f"{len(phrasings) or 1} ways across {scenarios} "
        f"scenario{'s' if scenarios != 1 else ''}, {rounds} times each:",
        "",
        "| | |",
        "|---|---|",
        f"| Gave its instructions away | **{gave_away.format()}** |",
        f"| … by quoting them | {injection.format()} |",
        f"| … by describing them | {described.format()} |",
        f"| Stepped out of the scene | {stepped.format()} |",
        "",
        *(
            [
                "| Phrasing | Scenario | Gave them away | Quoted | Described "
                "| Stepped out |",
                "|---|---|---|---|---|---|",
                *phrasing_rows,
                "",
            ]
            if phrasing_rows
            else []
        ),
        "Quoting is a run of six or more words shared verbatim with anything in the "
        "request nobody in the scene said — the brief, the goal, the rules, the "
        "reminder before the speaker's words — and not already said aloud in the scene. "
        'Describing is the first person on its own instructions: "I was told to", '
        '"I\'m designed to", "my prompt". Stepping out is a phrase such as "system '
        'prompt" or "as an AI". A reply can do more than one, so the parts do not sum. '
        "A paraphrase that does none of them is counted by none.",
        "",
        "`services/conversation` tells the model that anything in a speaker turn is "
        "something a person said out loud inside the scene and never an instruction, "
        "repeats that in the reminder placed before the speaker's words, and puts those "
        "words inside quotation marks as speech. The rate above is how often that holds.",
        "",
        "**What this is and is not.** The brief is not a secret — every persona ships in "
        "`api/seeds/scenarios.json` and anybody can read it — so a leak discloses "
        "nothing. What breaks is the exercise: the practice partner stops being a "
        "practice partner, and it can be made to stop by *speaking*, which in an app "
        "driven by a microphone is the only input there is. It is a role-integrity "
        "finding, not a confidentiality one, and calling it the second would be its own "
        "kind of dishonesty.",
        "",
        "**Reported rather than asserted**, on the same rule every model-facing figure "
        "here follows: this is a property of a 4-billion-parameter model and a prompt, "
        "not of the code under review, and it belongs in a document with its rate "
        'attached rather than in a red test that says only "sometimes".',
        "",
    ]
    return lines


def _corpus_section(results: dict, skips: dict) -> list[str]:
    lines = ["### The corpus these figures rest on", ""]
    corpus = results.get("corpus")
    if corpus is None:
        lines += [f"**Not counted.** {skips.get('corpus', 'no census was taken')}", ""]
        return lines
    busiest = corpus.get("busiest_account") or {}
    lines += [
        f"Counted {corpus['counted_at']}, across every account.",
        "",
        "| | |",
        "|---|---|",
        f"| Accounts, of which have practised | {corpus['accounts']}, "
        f"{corpus['accounts_with_practice']} |",
        f"| Sessions — conversation / read-aloud | {corpus['conversation_sessions']} / "
        f"{corpus['read_aloud_sessions']} |",
        f"| User turns, analysed | {corpus['user_turns']}, "
        f"{corpus['analysed_user_turns']} |",
        f"| Words | {corpus['words']} |",
        f"| Scored readings, phone instances | {corpus['scored_readings']}, "
        f"{corpus['phone_instances']} |",
        f"| Calendar days with practice | {corpus['days_with_practice']} |",
        f"| Busiest single account | {busiest.get('sessions', 0)} sessions on "
        f"{busiest.get('days_with_practice', 0)} "
        f"{'day' if busiest.get('days_with_practice') == 1 else 'days'} |",
        f"| First / last session | {corpus['first_session']} / "
        f"{corpus['last_session']} |",
        "",
        "Every undecidable and unmet verdict above traces back to this table. The "
        "instruments are built and tested; what does not exist is speech to point them "
        "at.",
        "",
    ]
    return lines


def render(
    results: dict,
    verdicts: list[Verdict],
    skips: dict | None = None,
    failures: dict | None = None,
    generated_at: datetime | None = None,
    revision: str = "unknown",
) -> str:
    """The whole document. Deterministic given its inputs, so it can be tested."""
    skips = skips or {}
    failures = failures or {}
    stamp = (generated_at or datetime.now()).strftime("%Y-%m-%d %H:%M")
    ran = [name for name in ("asr", "pron", "errors", "personas") if name in results]

    lines = [
        "# Evaluation",
        "",
        f"Generated by `make eval` on **{stamp}**, at revision `{revision}`.",
        "",
        "**Do not edit this file by hand.** Every number in it was produced by a command "
        "on the date above, and a hand-edited figure is indistinguishable from a "
        "measured one. Re-run `make eval` instead.",
        "",
        "Four suites, one census. Suites that ran: "
        + (", ".join(f"`{name}`" for name in ran) if ran else "**none**")
        + f" ({len(ran)} of 4).",
        "",
    ]
    if failures:
        lines += [
            "> **A suite ran and failed on this run.** "
            + "; ".join(f"`{name}` — {why}" for name, why in failures.items()),
            ">",
            "> Figures below from a suite that did not finish clean are still real "
            "measurements, and are still worth reading. What they are not is a whole "
            "suite's worth of evidence.",
            "",
        ]
    lines += [
        "## How to read this",
        "",
        "| | Means |",
        "|---|---|",
        f"| {MARK[MET]} | Measured, and it clears the bar |",
        f"| {MARK[NOT_MET]} | Measured, and it does not |",
        f"| {MARK[UNDECIDABLE]} | Measured, and the sample cannot settle it either way |",
        f"| {MARK[NOT_RUN]} | Not measured. No figure, and none carried forward |",
        "",
        f"The distinction between {MARK[UNDECIDABLE]} and {MARK[NOT_MET]} is the one this "
        "project keeps getting wrong in conversation and must not get wrong in writing. "
        f"Below {scoring.DECIDABLE_TRIALS} trials no figure here is allowed to decide a "
        "criterion, and that applies in the flattering direction too: a precision of "
        "1.000 over three proposals is three proposals.",
        "",
        "## Success criteria this harness settles",
        "",
        "| | Criterion | Verdict | Figure | Sample |",
        "|---|---|---|---|---|",
    ]
    for verdict in verdicts:
        lines.append(
            f"| {verdict.mark} | **{verdict.criterion}** — {verdict.statement} | "
            f"{verdict.verdict} | {verdict.figure} | {verdict.sample} |"
        )
    lines.append("")

    detailed = [verdict for verdict in verdicts if verdict.detail]
    if detailed:
        lines += ["### Why", ""]
        for verdict in detailed:
            lines += [
                f"**{verdict.criterion} — {verdict.verdict}.** {verdict.detail}",
                "",
            ]

    lines += [
        "## Criteria settled elsewhere",
        "",
        "| | Criterion | Measured by |",
        "|---|---|---|",
    ]
    for identifier, statement, where in ELSEWHERE:
        lines.append(f"| {identifier} | {statement} | {where} |")
    lines += [
        "",
        "Listed so that a table of four criteria is not read as a project with four.",
        "",
        "## The suites",
        "",
    ]
    lines += _asr_section(results, skips)
    lines += _pron_section(results, skips)
    lines += _errors_section(results, skips)
    lines += _personas_section(results, skips)
    if failures:
        lines += [
            "### Suites that did not finish clean",
            "",
            "| Suite | What happened |",
            "|---|---|",
            *(f"| `{name}` | {why} |" for name, why in failures.items()),
            "",
        ]
    lines += _corpus_section(results, skips)

    lines += [
        "## What would change these numbers",
        "",
        "In the order they would help, and none of them is code:",
        "",
        "1. **Five minutes of recording.** Each pronunciation passage read twice by the "
        "same speaker at the same microphone — once correctly, once mispronouncing the "
        "marked words. That is the whole of criterion S4, and it also unblocks the GOP "
        "threshold question, which ships empty rather than guessed because calibrating "
        "it needs more than one speaker.",
        "2. **More recorded conversation, on more than one day.** It is the only thing "
        "that moves S5 and S7 at once: more turns means more labelled errors to score a "
        "detector against, and more days means a trend with a direction in it.",
        "3. **Not the rule layer, on this corpus.** It exists for the two categories a "
        "parse can decide — subject–verb agreement and a missing article — and is right "
        "when it speaks, but the golden set holds no agreement error and one article "
        "error in a shape it leaves alone. It cannot move S5 until more speech is "
        "recorded, which is item 2 again. It also makes the category mix partly a "
        "property of the detector, which is why each detector is reported apart.",
        "",
        "## Reproducing this",
        "",
        "```bash",
        "make up                  # postgres, api, asr, tts",
        "make pron-up             # the pronunciation service, 1.78 GB",
        "ollama serve             # on the host, with the configured model pulled",
        "make eval                # every suite that can run, then this document",
        "```",
        "",
        "Each suite is also runnable on its own — `make asr-wer`, `make pron-golden`, "
        "`make error-precision`, `make persona-adherence` — and each prints more detail "
        "than lands here. A suite whose service is not up **skips**; it does not fail. "
        "That is what lets CI run the deterministic subset with no model layer at all.",
        "",
    ]
    return "\n".join(lines) + "\n"
