"""The evaluation harness: run every suite that can run, and write down what happened.

    make eval                      # everything, into docs/evaluation.md
    python3 eval/run.py --only asr
    python3 eval/run.py --local --out /tmp/evaluation.md    # what CI does

**Why this is a script on the host and not another pytest file.** The four measurements
are pytest suites, and they should stay that way: they need fixtures, async, and the skip
machinery, and each one has to be runnable on its own by somebody debugging a service.
What they are not is a report. Pytest's output is prose for a person watching it scroll
past, and scraping figures back out of prose is a parser that breaks the first time a
suite prints an extra line. So each suite writes its numbers as JSON (`tests/eval_out.py`)
and this collects them.

**The one property this file exists to preserve.** Every suite here *skips* when its
service, model or golden set is absent, and a skipped suite writes nothing. This runner
therefore cannot report a figure for a suite that did not run, because there is no figure
to report — not by convention, but because the code that would produce one never
executed. A harness that turned those skips into failures would make CI red for reasons
that have nothing to do with the code under review, and a harness that turned them into
passes would be worse.

**Exit codes.** Zero when every suite either measured or skipped. One when a suite *ran
and failed*, which is a different event and the only one worth failing a pipeline over.
The report is written either way: a failing suite is a fact worth publishing.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import report as report_module  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / ".eval"

# Where the container writes. `/app` is `./api`, so this has to be a mount of its own —
# see docker-compose.yml. Never inside `eval/`: the corpus a system is evaluated on is
# mounted read-only so the system cannot rewrite it, and results are not fixtures.
CONTAINER_RESULTS = "/app/.eval"

# pytest's `-rs` summary line, which is where a skip reason is legible. Used only to
# explain a skip in prose. Nothing about a verdict depends on this regular expression
# matching, and if it stops matching the report says "skipped" without the detail.
SKIP_LINE = re.compile(r"^SKIPPED \[\d+\] [^:]+:\d+: (.+)$", re.MULTILINE)


@dataclass(frozen=True)
class Suite:
    name: str
    path: str
    title: str
    env: dict[str, str]
    target: str


SUITES = (
    Suite(
        "asr",
        "tests/test_asr_golden.py",
        "Speech recognition",
        {"ASR_URL": "http://asr:8101"},
        "make asr-wer",
    ),
    Suite(
        "pron",
        "tests/test_gop.py",
        "Pronunciation",
        {"PRON_URL": "http://pron:8103"},
        "make pron-golden",
    ),
    Suite(
        "errors",
        "tests/test_error_precision.py",
        "Error detection",
        {"OLLAMA_BASE_URL": "http://host.docker.internal:11434"},
        "make error-precision",
    ),
    Suite(
        "personas",
        "tests/test_persona_adherence.py",
        "Persona adherence",
        {"OLLAMA_BASE_URL": "http://host.docker.internal:11434"},
        "make persona-adherence",
    ),
)


def revision() -> str:
    """The commit these numbers describe. Read-only; this repository's agents never write git."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return result.stdout.strip() or "unknown"


def _skip_reason(output: str, fallback: str) -> str:
    reasons = SKIP_LINE.findall(output)
    if not reasons:
        return fallback
    # The first distinct reason is the one that matters; a suite skipping for two
    # different reasons at once is a suite whose service and golden set are both absent.
    unique = list(dict.fromkeys(reason.strip() for reason in reasons))
    return unique[0]


def run_suite(suite: Suite, local: bool, verbose: bool) -> tuple[bool, str]:
    """Run one suite. Returns (it failed, what to say about it).

    The exit code is read **before** the result file, and the order is a bug fix rather
    than a preference. A suite is several tests: one of them writes the figures and the
    others assert. Checking for the file first reports "measured" for a suite whose
    measurement passed and whose assertions failed — which is precisely the run worth
    hearing about, and it was silently swallowed the first time this ran.
    """
    if local:
        command = [sys.executable, "-m", "pytest", suite.path, "-q", "-rs"]
        cwd = ROOT / "api"
        env = {**os.environ, "EVAL_OUT_DIR": str(RESULTS)}
    else:
        command = ["docker", "compose", "--profile", "tools", "run", "--rm"]
        for key, value in {**suite.env, "EVAL_OUT_DIR": CONTAINER_RESULTS}.items():
            command += ["-e", f"{key}={value}"]
        command += ["test", "python", "-m", "pytest", f"/app/{suite.path}", "-q", "-rs"]
        cwd = ROOT
        env = dict(os.environ)

    print(f"  {suite.name:<10} … ", end="", flush=True)
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True)
    output = result.stdout + result.stderr
    if verbose:
        print()
        print(output)

    measured = (RESULTS / f"{suite.name}.json").exists()
    if result.returncode == 0:
        if measured:
            print("measured")
            return False, ""
        reason = _skip_reason(output, "the suite skipped and did not say why")
        print(f"not run — {reason}")
        return False, reason

    failing = [
        line for line in output.splitlines() if line.startswith(("FAILED", "ERROR"))
    ] or output.strip().splitlines()[-3:]
    detail = "; ".join(line.strip() for line in failing[:3])
    print(
        f"FAILED (exit {result.returncode})"
        + (" — figures still collected" if measured else "")
    )
    return True, (
        f"the suite ran and failed (exit {result.returncode}): {detail}"
        + (
            ". Its measurement wrote figures before the failure, and they are reported "
            "above — read them knowing the suite did not finish clean."
            if measured
            else ""
        )
    )


def census(local: bool) -> tuple[dict | None, str]:
    """The corpus count, which is a query rather than a measurement.

    Separate from the suites because it does not evaluate anything. It says how much
    speech exists, and every undecidable verdict in the report traces back to it.
    """
    if local:
        command = [sys.executable, "-m", "scripts.corpus", "--json"]
        cwd = ROOT / "api"
    else:
        command = [
            "docker",
            "compose",
            "exec",
            "-T",
            "api",
            "python",
            "-m",
            "scripts.corpus",
            "--json",
        ]
        cwd = ROOT

    print("  corpus     … ", end="", flush=True)
    try:
        result = subprocess.run(
            command, cwd=cwd, capture_output=True, text=True, timeout=120
        )
    except (OSError, subprocess.SubprocessError) as exc:
        print("not counted")
        return None, f"the census could not be run ({type(exc).__name__}: {exc})"
    if result.returncode != 0:
        print("not counted")
        tail = (result.stderr or result.stdout).strip().splitlines()[-2:]
        return None, "the census failed: " + " ".join(tail)
    try:
        counts = json.loads(result.stdout)
    except ValueError:
        print("not counted")
        return None, "the census produced output that is not JSON"
    print(f"{counts['sessions']} sessions, {counts['words']} words")
    return counts, ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(ROOT / "docs" / "evaluation.md"))
    parser.add_argument(
        "--local",
        action="store_true",
        help="run pytest in this process's environment instead of a container",
    )
    parser.add_argument(
        "--only",
        action="append",
        choices=[suite.name for suite in SUITES],
        default=None,
    )
    parser.add_argument(
        "--verbose", action="store_true", help="print each suite's output"
    )
    args = parser.parse_args()

    if not args.local and shutil.which("docker") is None:
        print(
            "docker is not on PATH. Use --local to run the suites in this environment."
        )
        return 2

    # A stale result from an earlier run would be reported under today's date, which is
    # the exact failure this whole document is about. Cleared before anything runs.
    if RESULTS.exists():
        shutil.rmtree(RESULTS)
    RESULTS.mkdir(parents=True)

    chosen = [suite for suite in SUITES if not args.only or suite.name in args.only]
    print(f"Running {len(chosen)} suite(s) and the corpus census.\n")

    skips: dict[str, str] = {}
    failures: dict[str, str] = {}
    failed = False
    for suite in chosen:
        suite_failed, reason = run_suite(suite, args.local, args.verbose)
        failed = failed or suite_failed
        if suite_failed:
            failures[suite.name] = reason
        if reason:
            skips[suite.name] = reason
    for suite in SUITES:
        if suite not in chosen:
            skips[suite.name] = f"not selected on this run; `{suite.target}` runs it"

    counts, why_not = census(args.local)
    if why_not:
        skips["corpus"] = why_not

    results: dict[str, dict] = {}
    for path in sorted(RESULTS.glob("*.json")):
        results[path.stem] = json.loads(path.read_text())
    if counts is not None:
        results["corpus"] = counts

    readme = (ROOT / "README.md").read_text() if (ROOT / "README.md").exists() else ""
    verdicts = report_module.adjudicate(results, skips, readme)
    document = report_module.render(
        results,
        verdicts,
        skips=skips,
        failures=failures,
        generated_at=datetime.now(),
        revision=revision(),
    )

    destination = Path(args.out)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(document)

    print(f"\nWrote {destination}\n")
    for verdict in verdicts:
        print(
            f"  {verdict.mark}  {verdict.criterion}  {verdict.verdict:<12} {verdict.figure}"
        )
    print()
    if failed:
        print(
            "A suite ran and failed. The report says so; fix the suite, not the report."
        )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
