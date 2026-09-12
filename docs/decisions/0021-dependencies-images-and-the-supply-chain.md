# 0021 — Dependencies, images and the supply chain

Status: accepted · 2026-09-12

A review on 2026-09-12 scored the project's security 41 of 100. Trivy found 3 CRITICAL
and about 100 HIGH findings in each Python image and 4 and 45 in the frontend's; the
Python web stack was months behind with reachable advisories (python-multipart and
Starlette's form parsing, Starlette's Range handling); every container ran as root and
published its port on every interface, the database's with a development password; Next.js
15 had 39 days of support left; nothing proposed an update and nothing scanned one. Most of
it was mechanical. These were the choices in fixing it.

## What was decided

1. **The Python web stack moves to its current releases in all four services** —
   FastAPI 0.141.1 with Starlette 1.6.0, uvicorn 0.52.4, python-multipart 0.0.32, and in
   the API PyJWT 2.14.0 and the database libraries' current patch releases. The API's test
   and lint tools move to `infra/api/requirements-dev.txt` and a `test` stage, out of the
   image the API runs from.
2. **The app walks its own routers, not `app.routes`.** FastAPI 0.137 stopped copying an
   included router's operations into `app.routes`, which is now a tree of internal objects.
   Three things read it: two ownership tests, which failed; the loop that makes each
   operation's summary the first sentence of its docstring, which silently stopped; and the
   test of those summaries, which passed with nothing to check. `main.ROUTERS` is the one
   list of routers, included in a loop, and `api_routes()` walks them; a test asserts that
   the walk finds exactly the operations the OpenAPI document lists, so no loop over it can
   pass empty again.
3. **The lint's rules are named.** ruff 0.16's default rule set is wider than the one this
   code was written against and reported 140 findings. `ruff.toml` names E4, E7, E9 and F,
   the old default; widening them is its own change. black 26's style is applied: seven
   files.
4. **Every service runs as an unprivileged account** — `speaklab`, uid 10001, in the four
   Python images, the same id in each because they share the model cache; `node` in the
   frontend. A job, `volume-owner`, runs before them and hands any file on the named
   volumes owned by someone else to uid 10001, symlinks included, then exits. **Accepted
   cost:** one more container in the graph, run on every `up`; on a volume that is already
   right it changes nothing.
5. **Each image is pinned to its base's exact release and applies the distribution's
   published fixes at build time**; curl is gone and the health checks are in the
   Dockerfiles, as a line of Python or busybox `wget`. **Accepted cost:** the upgrade layer
   makes the Python images larger — api 814 to 826 MB, asr 740 to 790, tts 672 to 722, pron
   1.78 to 1.84 GB.
6. **Every published port is bound to 127.0.0.1.**
7. **The frontend installs with pnpm 12, not npm**, at the owner's request. pnpm refuses a
   release less than a day old (strict, because it is set explicitly), refuses a release
   published with weaker evidence of its origin than an earlier release of the same
   package, and runs no install script not allowed by name; both scripts in the tree are
   denied, and lint, types, the tests and the build pass without them. A scan of all 874
   packages against the registry found three releases the trust check refuses, each an
   older-line release by its own maintainer with a matching release in its repository;
   two remain in the tree and are excepted by exact version, the third left it with Node
   24's types. npm and corepack are removed from the image, and so are pnpm's store and its
   cache of registry metadata once the install is done: the image is 1.05 GB, from 1.66 GB.
   `qs` moves to 6.16.0.
8. **Node 24, the active LTS, replaces Node 22, and Next 16.3.5 with React 19.3.0 replaces
   Next 15**, whose support ends on 2026-10-21. Nothing in the code used what Next 16
   removes — every request API was already awaited, and there is no middleware, image
   optimisation or runtime config. Turbopack builds and serves. Next 16 pins a PostCSS
   release past every published advisory, so the override Next 15's copy needed is gone.
   ESLint moves to `eslint-config-next`'s own flat configs, and **two rules React Hooks'
   recommended set takes from the React Compiler are off** — refs read or written during
   render (15 places, all in the three recorders) and state set synchronously in an effect
   (6) — for decision 3's reason: the code is written to the rules of hooks and
   exhaustive dependencies, which stay on, and rewriting the recorders and hooks to the
   compiler's rules is a change of its own. The containerised dev server sees an edit on
   the host without polling, so Compose's polling variable, which only webpack read, is
   gone.
9. **Postgres is pinned to 16.15 and stays on Debian.** The Alpine variant carries far
   fewer findings but sorts text differently, so an existing database would have to be
   dumped and restored to move.
10. **CI's token is read-only, every action is pinned to a commit, and a fourth job runs
    Trivy** from its image pinned by digest rather than through `trivy-action`, whose tags
    were once moved to point at malicious code (GHSA-69fq-xp46-6x23). It fails on a HIGH
    or CRITICAL vulnerability with a fixed release, a Dockerfile misconfiguration, or a
    secret. Dependabot proposes updates weekly for pip in four directories, npm, the base
    images, Compose's images and the actions; torch and torchaudio are left to hand,
    because the pron Dockerfile repeats their versions.
11. **Python stays at 3.12.** It has security releases until 2028-10, and a current 3.14
    base scans the same.
12. **The model libraries are not upgraded here.** None carries a published
    vulnerability, and each changes what the product measures, so each waits for
    `make eval`.

    > **Superseded by [0022](0022-the-model-libraries.md).** Each was upgraded alone and
    > measured against the image before it; nothing the product measures moved.

## Measured

| | Before | After |
|---|---|---|
| api, asr, tts images, Trivy CRITICAL / HIGH | 3 / 98–104 | **0 / 44**, none with a fix |
| pron | 3 / 105 | 0 / 45, one in a library (NLTK) with no fix |
| frontend | 4 / 45 | **0 / 0** |
| `postgres` | 19 / 155 (`:16`) | 14 / 101 (`:16.15`), upstream's |
| The repository, as CI scans it | — | 0 fixable HIGH or CRITICAL, 0 misconfigurations, 0 secrets |
| API suite | 1 049, 1 011 pass | **1 050, 1 012 pass**, 38 need a model service, no warnings |
| Frontend | 316 / 49, Next 15 | 316 / 49 on Next 16.3.5 and React 19.3.0; `tsc`, ESLint and the Turbopack build green; every signed-in page renders with a real session |

All on 2026-09-12, in Docker, with the live stack brought up the way `make setup` brings
it up: every service healthy, every model loaded under the new account, a recording written
to the audio volume.

## Found on the way

- `next build` fails on this machine's network inside a container, fetching the Geist
  fonts: Node's fallback between address families times out where `wget` connects. The
  image as it was before this change fails the same way, and the build passes with
  `NODE_OPTIONS=--no-network-family-autoselection`.
- pnpm refused Next 16.3.5 a day after its release: its Windows x64 binary was published
  43 minutes after the package itself, and the install waited until that too was a day
  old.
- `next dev` writes an `AGENTS.md` and a `CLAUDE.md` into the project when it detects an
  AI coding agent from its environment. The container is given no such variable, and
  neither file appeared.

## Revisit if

- a package excepted from the trust check publishes a release with provenance on its line;
- Dependabot cannot update a lockfile written by pnpm 12;
- a service has to be reached from another machine — then it needs authentication, not a
  wider port.
