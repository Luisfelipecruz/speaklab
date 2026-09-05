"""How a measurement suite hands its numbers to the harness.

The four suites are pytest files, and that is deliberate: they need fixtures, async, the
skip machinery, and the ability to be run one at a time by somebody debugging a service.
But pytest's output is prose for a human, and `eval/run.py` needs figures. Scraping the
one to get the other is a parser that breaks the first time a suite prints an extra line.

So a suite that has finished measuring calls `record()`. When `EVAL_OUT_DIR` names a
writable directory it writes one JSON file; when it does not — which is `make test`, CI,
and anybody running a suite by hand — it does nothing at all and the suite behaves
exactly as it did before. The measurement never depends on being collected.

**The directory is never inside `eval/`.** The corpus a system is evaluated on is mounted
read-only so that the system cannot rewrite it, and results are not fixtures. `docker-compose.yml` mounts `./.eval` writable for this and
nothing else.

**A suite that did not run records nothing**, and that is the property the whole report
rests on. `eval/run.py` sees an absent file and reports the suite as not run. There is no
path by which a skipped suite produces a passing figure, because a skipped suite produces
no figure — the code that would write one never executes.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ENV_VAR = "EVAL_OUT_DIR"


def destination() -> Path | None:
    """Where results go, or `None` when nobody asked for them."""
    configured = os.environ.get(ENV_VAR, "").strip()
    return Path(configured) if configured else None


def record(suite: str, payload: dict[str, Any]) -> Path | None:
    """Write one suite's numbers, and return where they went.

    Adds the two fields every result needs and no suite should have to remember: what it
    is called, and when it was measured. A figure without a date is a figure that will be
    quoted a year from now against a model that has been replaced twice.

    Failures to write are deliberately not swallowed. A collection directory that was
    asked for and cannot be written to is a broken run, and a harness that quietly
    produced no result would report the suite as "not run" — which is a lie about a suite
    that ran perfectly.
    """
    directory = destination()
    if directory is None:
        return None

    directory.mkdir(parents=True, exist_ok=True)
    body = {
        "suite": suite,
        "measured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **payload,
    }
    path = directory / f"{suite}.json"
    path.write_text(json.dumps(body, indent=2, sort_keys=False) + "\n")
    return path


# ── Reaching the harness's own code ─────────────────────────────────────────

# `eval/` is not on the import path and must not be made importable as a package: `eval`
# is a builtin name, and a directory that shadows it inside `/app` would be a trap laid
# for somebody else. It is also mounted read-only, so Python cannot write bytecode into
# it — importing by path avoids ever asking. `test_phone_map.py` reaches the pron
# service's source the same way and for the same reasons.
_HARNESS_ROOTS = (
    Path("/app/eval"),
    Path(__file__).resolve().parents[2] / "eval",
)


def harness_root() -> Path | None:
    """Where the evaluation harness lives, in whichever layout this is running in."""
    return next(
        (root for root in _HARNESS_ROOTS if (root / "scoring.py").is_file()), None
    )


def load_harness(name: str):
    """Import one of the harness's modules by path, or raise saying where it looked.

    The suites share their arithmetic with `eval/report.py` rather than keeping a second
    copy of it. Two implementations of a Wilson interval is one implementation and one
    liability: the day they disagree, the figure in the report and the figure in the test
    output are both defensible and only one of them is right.
    """
    import importlib.util
    import sys

    root = harness_root()
    if root is None:
        raise ModuleNotFoundError(
            f"the evaluation harness is not reachable; looked in {list(_HARNESS_ROOTS)}"
        )
    qualified = f"speaklab_eval_{name}"
    if qualified in sys.modules:
        return sys.modules[qualified]

    spec = importlib.util.spec_from_file_location(qualified, root / f"{name}.py")
    if spec is None or spec.loader is None:
        raise ModuleNotFoundError(f"{root / f'{name}.py'} is not importable")
    module = importlib.util.module_from_spec(spec)

    # Registered BEFORE it is executed, and both halves of that matter. `@dataclass`
    # resolves its own module through `sys.modules[cls.__module__]` while the class body
    # is still being processed, so a module absent from sys.modules raises an
    # AttributeError on None during import — which pytest reports as a collection error,
    # taking the whole file down rather than skipping it.
    sys.modules[qualified] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        del sys.modules[qualified]
        raise
    return module
