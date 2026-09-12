# 0020 — Polish: the export, the waiting states, the first run and the walkthrough

Status: accepted · 2026-09-12

m16 is the last milestone, and its goal is a stranger who clones the repository, runs it,
and understands the engineering. Most of it is documentation, and documentation needs no
decision. These did.

## What was decided

1. **The whole history leaves as one JSON document, and recordings are addresses in it**,
   not bytes: `GET /progress/export`, sent as a download. The password hash and the
   bookkeeping that runs a conversation are left out. 31 operations.
2. **Every signed-in page has a loading state of its own, shaped like the page**, and a
   test reads the file tree to keep it that way. A page that throws gets a retry that asks
   the server again; an address that leads nowhere gets a page that does not say whether
   the thing ever existed. **Accepted cost:** a not-found decided after streaming has begun
   is sent with status 200.
3. **An operation's summary in the OpenAPI document is the first sentence of its
   docstring**, set in one place, and a test fails on an operation without one.
4. **The recording protocol is folded into the pronunciation set's README, not copied from
   `spike/`**, and raw recordings are ignored by git.
5. **S1: the build is not changed.** Measured cold again, the same build met the five
   minutes it had missed two days earlier. The difference was the connection, and both runs
   are reported.
6. **The walkthrough's learner is the project's synthetic voice**, at the owner's choice,
   and the video says so on screen. The still on the README's first screen is in the
   repository; the video is not.

## 1. The export

FR-25 — *a user can export their full history as JSON* — was the one requirement with
nothing behind it. `GET /progress/export` returns the account without its password hash;
every session with its turns, each turn with its word timings, fluency figures, the verb
forms counted in it and the corrections found in it; every reading with each scored
sound; every spoken answer with what was counted and what the model said; and the weekly
snapshots the progress page reads. Scenarios, passages and prompts are named by slug:
they are catalogue content, the same for every account, and not part of anybody's
history.

**Recordings are listed, not embedded** — length, format, hash and the `/audio/{id}`
address that streams each one to its owner. A JSON file is no place for megabytes of
base64, and that address is ownership-checked like everything else.

**Left out on purpose:** the password hash, which is a credential rather than a record,
and three things kept to run a conversation rather than to describe one — the summary a
long conversation is condensed into for the model, the token counts, and the analyser's
refused proposals.

Ten queries, each filtered to the caller and grouped in Python; walking the ORM's
relationships would have been a query per session and another per turn. Like every
progress operation it takes no user id, so there is no request that exports somebody
else's history, and `test_ownership.py` names the route among the scoped ones.

**Checked against the live database**, with a session cookie minted for each account:
for all 6 accounts, the sessions, turns, corrections, readings, scored sounds, answers,
snapshots and recordings in the export equal a `COUNT(*)` of the tables. The largest, 26
turns, 3 readings and 679 scored sounds, is 198 594 bytes and took 17 ms.

A link to it sits under the account's email in the rail. It is a plain link rather than a
fetch: the API answers with an attachment, so the browser saves the file, and a top-level
navigation carries the session cookie.

## 2. Waiting, failing, and nothing there

Every signed-in page is rendered on the server with the session cookie forwarded, so a
click on the rail waits for the API. **No route had a loading state**, and the previous
page stayed on screen through that wait: a click that seemed to do nothing. Now each of
the 12 signed-in pages has its own `loading.tsx`, and the group has one more: a skeleton
shaped as a grid of cards, a list, a row of figures or one document, so the layout does
not jump when the page arrives, with its purpose said in words for a screen reader. A
page without its own would borrow the nearest one above it — a scenario loading under the
catalogue's grid — so `app/boundaries.test.ts` reads the tree and names any page that has
none.

**A page that throws something it did not expect** shows an error panel inside the shell,
so every other section is still one click away. Its retry refreshes the route before
resetting it, because a server component that threw has no client state to reset. A
production build withholds the server's message and sends a digest; the panel shows it,
and it matches the error line in the frontend's logs. The same panel serves the pages
outside the shell, and `global-error.tsx` covers the root layout itself with a sentence
and a button.

**An address that leads nowhere** says "Nothing here" and offers a way back, without
saying whether the thing ever existed: another account's conversation answers 404 exactly
as a deleted one does, and a page that told the two apart would tell a stranger which ids
are taken.

**The cost, measured and accepted.** `/does-not-exist` answers 404; `/sessions/abc` answers
200 with "Nothing here" inside the shell. On a page with a loading state the response has
started streaming before the page decides it has nothing to show, and the status line has
already gone. This is a local application with no crawler to mislead, and the page is what
a person reads. Dropping the loading states from the detail pages is what 404 would cost.

**The empty states were checked, not rebuilt.** Each section already says what it is
waiting for rather than drawing an empty frame — *Start here* on the home page, *You have
not practised anything yet* in the history, *There is nothing to chart yet* on the
progress page, and the grammar and answers pages in the same way.

## 3. The OpenAPI document

`/docs` is what a reader opens after the README. It titled each operation after its
function — *Read Me*, *Add Turn*, *Health Models* — described none of its ten sections, and
`GET /passages` had no docstring at all. Each summary is now the first sentence of the
operation's docstring, set once in `main.py` after the routers are registered; the ten tags
are described in the order a reader meets the product. Three docstrings were rewritten
because their first sentence was not a summary — *The chooser.*, *Speak; be heard; be
answered.* — and the missing one was written. `tests/test_openapi.py` fails on an
operation without a docstring, a summary that is still the function's name, or a tag
without a description.

## 4. The recording protocol

The pronunciation pairs that would settle S4 are recorded by a person, following a
protocol that lived in gitignored `spike/RECORD.md` — out of reach of a clone. The
pronunciation set's own README already held the lines to say and the conversion; it now
also holds what only the spike's file had: half a second of silence at each end, a
recorder to use, where to save the takes, and a check with `afinfo` that each is 16 kHz
mono. `RECORD.md` was not copied: it carried a path from the machine it was written on
and told the reader to save into `spike/`. The folder the raw takes go into is now ignored
by git, because a recorder writes `.m4a` and no pattern caught it — a person's voice could
have appeared in `git status`.

## 5. The first run

S1 is a clean clone reaching all-healthy with no manual editing, and PRD §9 puts five
minutes on it, model downloads included. Measured the way #17 measured it: a `git archive`
copy of `main` in a directory of its own, so its compose project had empty volumes, and a
BuildKit builder of its own, so there was no layer cache and the base images were pulled.
The live stack was stopped for the run — the ports are fixed — and started again after it;
everything the copy made was removed by name.

| | 2026-09-10 | 2026-09-12 |
|---|---|---|
| `make setup` returned | 432 s | **153 s** |
| Whisper loaded | 538 s | **163 s** |
| The API's `pip install` | 346 s | 88 s |
| First spoken turn, heard verbatim, answered with audio | 2.2 s | 3.5 s |
| Five containers after that turn | 1.94 GiB | 1.74 GiB |

Nothing in the build changed between the two. The API image built alone, cold, took
114 s, `pip install` 98.6 s of it, and all 153 downloads were wheels — nothing is compiled.
**The build is network-bound, and what missed on 2026-09-10 was the connection.**

**Decided: no change to the build.** A parallel installer would shorten a slow connection's
build, and it would add a tool fetched from another registry to every build of every image;
moving the test tools out of the API image would save seconds. Neither changes the answer
on the connection that met the bar, and both runs are in the README. Revisit if a cold run
on an ordinary connection misses again.

**Not settled:** two runs, one machine. `postgres:16` was already on it both times, and
Ollama's model is a prerequisite pulled once, outside both figures.

## 6. S2 on a busy machine

`make turn-latency` on 2026-09-12: **p95 5356 ms against 3000 ms, missed**, at a load
average of 16.7 when it started and 18.0 when it ended. Recognition took 2524 ms at the
median, against 1146 ms on the quiet run of 2026-08-30 that met the budget at 2684 ms;
generation took 706 ms against 872. The recogniser's code has not changed since that run
beyond its comments, while the turn's own path has — each turn now queues its analysis,
and the speaker's words reach the model as quoted speech — and it is the recogniser that
slowed, by more than twice. A minute after the run Docker's virtual machine was at 254 %
CPU while every SpeakLab container sat below 2 %. So this is recorded as what a busy
machine does, beside the 7283 ms measured on one before; only a quiet re-run can rule a
regression out.

## 7. The walkthrough

`demo/record.cjs` drives the running stack in a headless Chromium and films it: a
scenario and its brief, two spoken turns, the report with its corrections marked on the
transcript, the grammar page, a reading scored sound by sound, one spoken answer to a work
question, the progress page and the home page. It was written before the grammar page and
*Make your point* existed, and it said "eight scenarios" when there were eleven. Its
captions now count the scenarios and passages off the page on the day of the take, and it
films both new sections.

**The learner is the project's own `tts` voice, at the owner's choice** (D116). The
alternatives were the owner's recorded turns, which would put a person's voice in a public
video, and no video this milestone. `demo/voices.sh` synthesises four lines written for
the take: two turns of the apartment viewing, with a wrong tense, a malformed question and a
comparative built the long way; the passage; and an answer to *Explain a missed deadline*
with a filler, a word said twice, a reason, an example and a summing up. The captions say
the voice is synthetic, and that the reading's scores show the pipeline rather than an
accent — the acoustic model is out of its domain on synthetic speech (D13).

**Measured in the take, 2026-09-12, 1280×720:** each spoken turn answered, with audio, in
4.0 s, from release to the reply on the page; the report in 1.8 s; the reading scored in
12.3 s; the answer counted, with the model's feedback beside it, 3.8 s after the press that
stopped it. One take on a machine running other work, not a benchmark. The stopwatch stays
on screen, so an edit that speeds the video up shows as a jump rather than a count.

**Found while filming, and fixed.** The answer scene waited for the text *How you built
it*, and Playwright's text match is partial and ignores case, so it matched the line shown
while the answer is still being counted — *Counting how you said it and how you built it* —
and the first take's clock stopped at 0.0 s over a spinner. It now waits for the result's
heading, by role and exact name. And the clips were first written inside `out/`, which the
recorder empties as a take starts; they are kept beside it now.

**The still on the README's first screen is from this take, and it is committed**
(D117): `docs/walkthrough.png`, 1280×720, 99 KB. A picture on the first screen has to
render on a fork and be reviewed in the PR, and a hundred kilobytes is not what the ignore
rules guard against. The video — 199.8 s, 10.4 MB of H.264 with that still as its cover —
stays in `demo/out/`, ignored. **It was not picked for looking good.** The frame is the
report as it came out: the model corrected *How much it cost every month?* to *how much it
costs every month*, which fixes the verb and not the question, and filed it under word
order. The README's caption says so, because that is the measured state of the detector.

## 8. What is not settled

- **The social-preview image and the repository's topics** are set by hand on GitHub, and
  have not been.
- **The video is attached nowhere.** The README shows a still; an upload of the `.mp4` is
  the owner's to make.
- **S2 has not been re-measured on a quiet machine** since the turn's path changed.
- **A person's microphone has never been through the interface** in Chrome or Safari; the
  take and m15's end-to-end check replay a synthetic voice.
- **The export has no import**, and an account still cannot be deleted.
