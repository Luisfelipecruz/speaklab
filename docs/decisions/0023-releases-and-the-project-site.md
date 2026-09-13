# 0023 — Releases and the project site

Status: accepted

A release gives a version something to point at, and a site lets the documents be read as
documents rather than as files on GitHub. The owner chose how each is made here. This
records those choices, what they rest on, and the gap in Dependabot.

## What was decided

1. **A release is cut from the changelog, by a workflow.** Pushing a tag `vX.Y.Z` runs
   `.github/workflows/release.yml`. It refuses a tag that is not on `main`, and one whose
   commit carries another version in `api/config.py`, then publishes the release with that
   version's entry as its notes and the entry's links pointed at the tag.
   `website/release_notes.py` does the cutting with the standard library alone, so the job
   installs nothing. CI's Site job fails when the version in the code has no entry, so the
   mistake is caught on the pull request, before any tag exists.
2. **Of the versions before the workflow, only 0.17.0 is a release**, at the owner's
   choice, from `18abed8`, made by hand: a workflow run for a tag uses the workflow file at
   the tagged commit, and `18abed8` has none. Every earlier version is an entry in the
   changelog. Two of them could not be tagged faithfully: no commit on `main` carries
   `0.2.0` or `0.7.0` in `api/config.py` — the commit that holds 0.2.0's work carries 0.1.0,
   and the one that holds 0.7.0's carries 0.8.0.
3. **The site is built by a script of this repository's own**, `website/build.py`, on
   markdown-it-py 4.2.0 and mdit-py-plugins 0.6.1 — the owner's choice of four. MkDocs had
   gone two years without a release, and Zensical, which its theme's authors are writing to
   replace it, was at 0.0.61 and marked alpha. Starlight would have been a second Node
   dependency tree under the pnpm policy, and GitHub's own Jekyll build checks no link.
   The builder's three pinned packages are Python requirements, which Trivy and Dependabot
   already cover.
4. **A broken link fails the build.** Every link is resolved as it is written. A link to
   another document becomes a relative link to its page, so the site works at any
   address — Pages serves it under `/speaklab/`, a preview at `/`. A link to a file that is
   not a page goes to that file on GitHub, at the commit the site was built from. A link to
   a heading resolves only if the heading exists, its id made the way GitHub makes one, so
   a link written against GitHub lands on the same heading here. A link to a file git does
   not track, a heading that does not exist, or raw HTML outside the few tags GitHub also
   shows, fails CI's Site job before it can reach `main`.
5. **The README is the home page.** Its centred header — the badges and the link row,
   GitHub's way into the file — gives way to a hero with the same title and tagline, and
   everything below it is the README as written. Every document under `docs/` is a page,
   each decision record included with an index of them, and so are CONTRIBUTING, SECURITY
   and the code of conduct. The product's own palette, in light and in dark.
6. **The one diagram is drawn by Mermaid 12.0.0 from jsDelivr**, fetched only when the
   diagram is about to be seen, and checked against the release's hash: 1.5 MB compressed,
   for one diagram on one page. Until it has drawn, and without it, the source shows.
7. **The site is published from `main` on every push**, by `.github/workflows/pages.yml`,
   with the same build CI's Site job ran on the pull request. Its token can write to Pages,
   and only in the job that publishes.
8. **Dependabot cannot update the frontend, so CI watches it every week.** Dependabot's
   run on `main` fails for `/frontend`: its updater runs pnpm 11.17.0, `packageManager`
   names 12.4.1, and the lockfile update fails while pnpm fetches its own binary — so no
   pull request, for a new release or for a vulnerability, can be opened against the
   frontend. pnpm 12 stays, at the owner's choice. The three majors that were due are
   ignored, because each waits on a decision rather than on Dependabot: ESLint 10 and
   TypeScript 7 until the lint plugins Next's configuration uses accept them, and Node's
   types until the runtime moves past Node 24. CI runs every Monday on `main`: the Security
   job's scan fails on a vulnerability published since the last push, and the frontend job
   runs `pnpm audit` and writes what `pnpm outdated` lists into the run's summary.

## Measured

- The site: 35 pages and 220 links, every one resolved — 177 to other pages, 8 to a
  heading on the same page, 9 to files on GitHub at the commit, 26 elsewhere — built in
  0.2–1.1 s, with git present as CI builds it and without it as `make site` does. In
  headless Chromium, at 1440 and 390 pixels wide, in light and with the dark palette
  forced on: the frame, the sidebar and the hero; the diagram drawn, one SVG, on the home
  page and on a page of its own.
- The builder's, the renderer's and the notes script's tests: 41.
- 0.17.0's notes: 74 lines — its entry, and a link to the changelog at the tag.
- pnpm 12.4.1 in the frontend container: `pnpm audit --audit-level high` finds no known
  vulnerability and exits 0; `pnpm outdated --format list` lists ESLint 9.39.5 → 10.10.0
  and TypeScript 6.0.3 → 7.0.2, and exits 1.
- actionlint 1.7.12: nothing in `ci.yml`, `pages.yml` or `release.yml`.
- Dependabot on `main` at `18abed8`: pip, docker, docker-compose and
  github-actions succeeded with nothing to propose; npm for `/frontend` failed on eslint,
  typescript and `@types/node`, a `HelperSubprocessFailed` while pnpm downloaded its
  12.4.1 binary.

## Revisit if

- Dependabot's updater can write a pnpm 12 lockfile: the weekly listing stops being the
  only way a frontend update is seen.
- markdown-it-py or its plugins stop being maintained, or the documents need search:
  Starlight or Zensical, whichever is then stable.
- A second diagram arrives, or Mermaid's script grows: draw the diagrams at build time.
- A version before 0.17.0 is wanted as a release: only from a commit that carries it.
