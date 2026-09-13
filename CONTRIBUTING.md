# Contributing to SpeakLab

Thank you for looking. SpeakLab is a small project, and one rule shapes every change to it:
**a figure is measured, dated and named with what produced it, or it is not written
down.** A number in a README, a pull request or a code comment that nobody re-ran reads
exactly like one somebody did, and this is a project about measuring honestly.

## What helps most

- **Recordings for the pronunciation pairs.** Criterion S4 — that deliberately
  mispronounced readings score measurably worse than clean ones — is measured on about
  five minutes of one person reading three sentences twice, once naturally and once with
  the marked words said wrong. Nobody has recorded them yet. The protocol is
  [eval/golden/pron/README.md](eval/golden/pron/README.md). Your own voice only, and only
  if you are content for it to be published in this repository.
- **A real microphone.** No person has held the record button in Chrome or Safari; a
  synthetic voice has driven it in a headless browser. An issue saying what happened, with
  the browser and the operating system, is a contribution.
- **Anything in [docs/limitations.md](docs/limitations.md)**, which lists what does not
  exist yet and what each gap would take.

For anything larger than a fix, open an issue first and say what would show it works —
which command, which figure. A change nobody can measure is hard to accept here.

## Setting up

The [Quick start](README.md#quick-start) is the whole setup: Docker, Ollama on the host
with `gemma3:4b` pulled, then `make setup`. Every step is idempotent, so it is also the
command to run after pulling.

## Before you open a pull request

Everything runs in containers, as CI runs it:

| | |
|---|---|
| `make lint` | ruff and black over the API, check only; `make fmt` fixes in place |
| `make test` | The API suite against Postgres. Tests that need a model service skip when it is not up |
| `make test-frontend` | Jest and React Testing Library |
| `docker compose run --rm --no-deps frontend pnpm run typecheck` | TypeScript |
| `docker compose run --rm --no-deps frontend pnpm run lint` | ESLint |
| `make site` | The project site, built as the Pages workflow builds it, with its tests. A link to a file or a heading that does not exist fails it; `make site-serve` shows it on <http://localhost:8004> |

CI runs five jobs on every pull request: the API's lint and tests with the evaluation
harness's own tests; the frontend's lint, types, tests and build; a check that the Compose
file parses with every profile; a Trivy scan that fails on a HIGH or CRITICAL
vulnerability with a fixed release, a Dockerfile that runs as root, or a secret; and the
project site's tests and build. `main` takes a change only when all five pass. CI runs
again every Monday on `main`, and then the frontend job also audits the installed packages
and lists what has a newer release.

If your change moves a measured figure, run what measures it — `make eval` runs every
suite into [docs/evaluation.md](docs/evaluation.md) — and update the figure wherever it is
quoted, with its date. `docs/evaluation.md` is never edited by hand.

## Dependencies

- **Python requirements are pinned exactly**, one file per service under `infra/`. The
  API's test and lint tools are in `infra/api/requirements-dev.txt` and never in the image
  the API runs from.
- **The frontend uses pnpm**, at the version `packageManager` names in
  `frontend/package.json`. Add a package with
  `docker compose run --rm --no-deps frontend pnpm add <name>` and commit
  `frontend/pnpm-lock.yaml` with it. pnpm refuses a release less than a day old, and runs
  no dependency's install script unless `frontend/pnpm-workspace.yaml` allows it; allowing
  one is a change to review, not a default.
- **Dependabot proposes updates weekly** for the Python requirements, the base images,
  Compose's images and the actions. It cannot yet update the frontend's lockfile — its
  updater does not run the pnpm release `packageManager` names — so CI's Monday run lists
  what is behind in its summary, and those updates are made by hand with `pnpm update`.
  An update to a model library — faster-whisper, Piper, onnxruntime, transformers, torch —
  changes what the product measures, and needs `make eval` before it merges.
- **Every service runs as an unprivileged account**, and every published port is bound to
  `127.0.0.1`. Keep both.

## Rules the code keeps

- **Nothing plotted over time comes from a language model.** Deterministic code measures;
  the model explains. Prompt drift must never be able to look like progress.
- **No pronunciation claim from a component that did not hear the waveform.**
- **The error taxonomy is closed.** A proposal outside it is refused and counted, never
  stored as valid.
- **The API image carries no model weights and no torch.** Models live in the `asr`,
  `tts` and `pron` services, and a test asserts it.
- **Another account's data answers 404, never 403**, so a request cannot learn what
  exists.
- **Comments describe what the code does now.** No dates, no history, no ticket or
  document numbers: state the reasoning directly.
- **Never commit audio or model weights.** `.gitignore` covers them. The evaluation
  fixtures under `eval/golden/` are the one exception, added with `git add -f`.

## Commits and pull requests

- One pull request per change, squash-merged.
- Commit messages are one line with a conventional prefix — `feat:`, `fix:`, `docs:`,
  `chore:`.
- A choice that cost time to learn gets a record in [docs/decisions/](docs/decisions/):
  what was decided, why, and what would reopen it.
- Say in the pull request what you measured, and how.

## Releases

A release is one version's entry in [docs/changelog.md](docs/changelog.md), published from
the commit that carries it.

1. The pull request that finishes a version sets `VERSION` in `api/config.py` and adds
   the changelog's entry for it, `## [x.y.z] — date · name`. CI's Site job fails when the
   version in the code has no entry.
2. Once it is merged, the maintainer tags the merge commit on `main` —
   `git tag -a vx.y.z -m vx.y.z <commit>`, then `git push origin vx.y.z`.
3. The Release workflow checks that the tag is on `main` and that its commit carries that
   version, and publishes the release with the entry as its notes. `make release-notes
   V=x.y.z` prints the same notes.

The project site is rebuilt from `main` on every merge.

## Conduct and security

Everyone taking part follows the [code of conduct](CODE_OF_CONDUCT.md). Report a
vulnerability as [SECURITY.md](SECURITY.md) describes, never in a public issue.
