# Changelog

One entry per milestone. Numbers here are counted against the running system at the time
of writing, never recalled — if a figure cannot be re-measured it does not belong here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [0.1.0] — 2026-08-29 · m1, scaffold

The stack exists and reports on itself. No feature does.

### Added

- **Compose stack.** Seven services declared, three started by default
  (`postgres`, `api`, `frontend`). `asr`, `tts`, `pron`, `ollama` and the `test` job sit
  behind profiles, which is what lets this file name build contexts that m4, m5 and m8
  have not created yet.
- **API.** FastAPI on Python 3.12, async SQLAlchemy 2.0 against PostgreSQL 16.
  Two operations: `GET /health` and `GET /health/models`.
- **Frontend.** Next.js 15, React 19, Tailwind v4, shadcn/ui. One page, which renders
  `/health` — the only check that covers browser → frontend container → API container →
  Postgres. It has a healthcheck of its own (busybox `wget --spider`, 60 s start period
  because `next dev` compiles the first route on demand), so all three default containers
  report `healthy` rather than merely `up`.
- **CI.** Three jobs: API lint and tests, frontend lint/types/build, and a Compose parse
  of the default stack and of every profile.

### Measured

| | |
|---|---|
| Containers up and healthy | 3 of 3 |
| `GET /health`, warm | 13–20 ms over 5 calls |
| API test suite | 13 passed in 0.21 s |
| API image | 422 MB |
| API operations | 2 of the 29 forecast |

### Decided

- **No `infra/postgres/` image or `init.sql`.** Plain `postgres:16`. With no extensions
  to add, a Dockerfile whose only line is `FROM postgres:16` implies a customisation
  that does not exist, and an `init.sql` that created tables would be a second source of
  truth alongside the Alembic revisions that own the schema from m2.
- **API on 8002, not 8001.** 8001 is occupied by an unrelated stack on this machine.
- **Next.js 15.5.24, not 15.5.12.** The version the plan was written against carries
  24 published advisories, all fixed within the 15.5 line.
- **The API build context is the repository root**, so the image carries `api/` and runs
  without a bind mount. `.dockerignore` keeps that context small; without it every build
  would ship `spike/.venv` (875 MB) and `frontend/node_modules` (549 MB) to the daemon.

### Known

- `npm audit` reports 2 advisories against the copy of `postcss` bundled inside Next 15's
  own `node_modules`. The only fix upstream is Next 16, which is outside this plan. It
  affects CSS source-map loading in the build pipeline, not the served application.
- `/health` reports `degraded` on a fresh checkout. That is correct: no model service
  exists before m4.

### Not in this release

Everything else. The schema and seeds (m2), accounts (m3), speech in and out (m4, m5),
the conversation loop (m6, m7), pronunciation scoring (m8), grammar analysis (m9),
progress (m10), the evaluation harness (m11).
