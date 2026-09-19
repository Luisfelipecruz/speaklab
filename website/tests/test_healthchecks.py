"""A container's healthcheck must reach its own port.

Inside these images `localhost` resolves to `::1` first. Python's `urllib` tries every
address the name resolves to, so the API and model services are fine with it; busybox
`wget` tries the first and stops, and a Next server listening on IPv4 only refuses it —
so the frontend could serve every request and still be reported unhealthy. A healthcheck
made with `wget` therefore names the numeric loopback address.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DOCKERFILES = sorted((ROOT / "infra").glob("*/Dockerfile"))


def _healthchecks(path: Path) -> list[str]:
    """Each HEALTHCHECK instruction as one line, its continuations joined."""
    joined = path.read_text().replace("\\\n", " ")
    return [line for line in joined.splitlines() if line.startswith("HEALTHCHECK")]


def test_every_dockerfile_declares_a_healthcheck():
    assert DOCKERFILES, "no infra/*/Dockerfile found"
    for path in DOCKERFILES:
        assert _healthchecks(path), f"{path.relative_to(ROOT)} has no HEALTHCHECK"


def test_no_wget_healthcheck_names_localhost():
    for path in DOCKERFILES:
        for check in _healthchecks(path):
            if "wget" not in check:
                continue
            assert "localhost" not in check, (
                f"{path.relative_to(ROOT)}: wget tries one address, and localhost is "
                f"::1 in the image; use 127.0.0.1:\n{check}"
            )


def test_the_frontend_healthcheck_fetches_the_ipv4_loopback():
    checks = _healthchecks(ROOT / "infra" / "frontend" / "Dockerfile")
    assert len(checks) == 2, "one healthcheck per stage, dev and runner"
    for check in checks:
        assert "http://127.0.0.1:3000" in check
