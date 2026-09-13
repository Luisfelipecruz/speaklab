# 0020 — Polish: the export, the waiting states, the first run and the walkthrough

Status: accepted

Polish is for a stranger who clones the repository, runs it, and understands the
engineering. Most of it is documentation, which needs no decision. These did.

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
4. **The recording protocol is in the pronunciation set's README**, and raw recordings are
   ignored by git.
5. **S1: the build is not changed.** Measured cold twice, the same build missed the five
   minutes once and met them once. The difference is the connection, and both runs are
   reported.
6. **The walkthrough's learner is the project's synthetic voice**, at the owner's choice,
   and the video says so on screen. The still on the README's first screen is in the
   repository; the video is not.
7. **The LinkedIn cuts are narrated, in portrait, over the app's own sound**: a
   third synthetic voice explains, the learner's clips and the persona's replies play when
   they played, and the short cut leaves out what it cannot show in real time rather than
   cutting it.
8. **The recorder is not in the repository**, at the owner's request. It films the
   product and is not part of it: it needs Playwright, ffmpeg and two more voices, and
   nothing in the product or its checks runs it. It stays on the machine that records,
   ignored by git; the README's still stays in `docs/`.
9. **The README takes the shape of a large open-source project's**, at the owner's
   request: badges, the features, the quick start, the architecture, the ten criteria, the
   known limitations, the documentation, development, contributing and acknowledgements.
   The long sections move into `docs/`, and the files a contributor looks for are added.
10. **The reference documents describe the system as it is**, at the owner's request. The
   README, the architecture, how it works, the measurements, the limitations and the data
   model are organised by component, in the present tense, with no milestone ids and no
   stories; a figure that moves from run to run on the same code is one range across the
   runs recorded, with the latest in `docs/evaluation.md`. A changed decision gets a new
   record that supersedes the old one, and dates and chronology go in the changelog only.

## 1. The export

FR-25 — *a user can export their full history as JSON* — is `GET /progress/export`. It
returns the account without its password hash;
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
click on the rail waits for the API, and without a loading state the previous page stays on
screen through that wait: a click that seems to do nothing. Each of the 12 signed-in pages
has its own `loading.tsx`, and the group has one more: a skeleton
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

`/docs` is what a reader opens after the README, and left to itself it titles each
operation after its function — *Read Me*, *Add Turn*, *Health Models*. Each summary is the
first sentence of the operation's docstring, set once in `main.py` after the routers are
registered, so a docstring's first sentence is a summary — not *The chooser.* or *Speak; be
heard; be answered.* — and the ten tags are described in the order a reader meets the
product. `tests/test_openapi.py` fails on an operation without a docstring, a summary that
is still the function's name, or a tag without a description.

## 4. The recording protocol

The pronunciation pairs that would settle S4 are recorded by a person, following the
protocol in the pronunciation set's own README: the lines to say, half a second of silence
at each end, a recorder to use, where to save the takes, the conversion, and a check with
`afinfo` that each is 16 kHz mono. The folder the raw takes go into is ignored by git,
because a recorder writes `.m4a` and no extension pattern catches it — a person's voice
would otherwise appear in `git status`.

## 5. The first run

S1 is a clean clone reaching all-healthy with no manual editing, and PRD §9 puts five
minutes on it, model downloads included. Measured from nothing: a `git archive`
copy of `main` in a directory of its own, so its compose project had empty volumes, and a
BuildKit builder of its own, so there was no layer cache and the base images were pulled.
The live stack was stopped for the run — the ports are fixed — and started again after it;
everything the copy made was removed by name.

| | First run | Second run |
|---|---|---|
| `make setup` returned | 432 s | **153 s** |
| Whisper loaded | 538 s | **163 s** |
| The API's `pip install` | 346 s | 88 s |
| First spoken turn, heard verbatim, answered with audio | 2.2 s | 3.5 s |
| Five containers after that turn | 1.94 GiB | 1.74 GiB |

Nothing in the build changed between the two. The API image built alone, cold, took
114 s, `pip install` 98.6 s of it, and all 153 downloads were wheels — nothing is compiled.
**The build is network-bound, and what missed on the first run was the connection.**

**Decided: no change to the build.** A parallel installer would shorten a slow connection's
build, and it would add a tool fetched from another registry to every build of every image;
moving the test tools out of the API image would save seconds. Neither changes the answer
on the connection that met the bar, and both runs are in the README. Revisit if a cold run
on an ordinary connection misses again.

**Not settled:** two runs, one machine. `postgres:16` was already on it both times, and
Ollama's model is a prerequisite pulled once, outside both figures.

## 6. S2 on a busy machine

`make turn-latency` on a busy machine: **p95 5356 ms against 3000 ms, missed**, at a load
average of 16.7 when it started and 18.0 when it ended. Recognition took 2524 ms at the
median, against 1146 ms on the quiet run that met the budget at 2684 ms; generation took
706 ms against 872. The recogniser's code is the same as in that run beyond its comments,
while the turn's own path is not — each turn queues its analysis, and the speaker's words
reach the model as quoted speech — and it is the recogniser that slowed, by more than twice. A minute after the run Docker's virtual machine was at 254 %
CPU while every SpeakLab container sat below 2 %. So this is recorded as what a busy
machine does, beside the 7283 ms measured on another busy run; only a quiet re-run can rule a
regression out.

## 7. The walkthrough

**The recorder is kept outside the repository** (decision 8), on the machine that
records.

It drives the running stack in a headless Chromium and films it: a scenario and its brief,
two spoken turns, the report with its corrections marked on the transcript, the grammar
page, a reading scored sound by sound, one spoken answer to a work question, the progress
page and the home page. Its captions count the scenarios and passages off the page on the
day of the take.

**The learner is the project's own `tts` voice, at the owner's choice.** The alternatives
were the owner's recorded turns, which would put a person's voice in a public video, and no
video at all. Four lines are synthesised for the take: two turns of the apartment viewing, with a wrong tense, a malformed question and a
comparative built the long way; the passage; and an answer to *Explain a missed deadline*
with a filler, a word said twice, a reason, an example and a summing up. The captions say
the voice is synthetic, and that the reading's scores show the pipeline rather than an
accent — the acoustic model is out of its domain on synthetic speech.

**Measured in the take, at 1280×720:** each spoken turn answered, with audio, in
4.0 s, from release to the reply on the page; the report in 1.8 s; the reading scored in
12.3 s; the answer counted, with the model's feedback beside it, 3.8 s after the press that
stopped it. One take on a machine running other work, not a benchmark. The stopwatch stays
on screen, so an edit that speeds the video up shows as a jump rather than a count.

**Found while filming, and fixed.** Playwright's text match is partial and ignores case,
so waiting for *How you built it* matched the line shown while the answer is still being
counted — *Counting how you said it and how you built it* — and stopped a take's clock at
0.0 s over a spinner. The answer scene waits for the result's heading, by role and exact
name, and the clips are kept outside the folder the recorder empties as a take starts.

**The still on the README's first screen is from this take, and it is committed**:
`docs/walkthrough.png`, 1280×720, 99 KB. A picture on the first screen has to
render on a fork and be reviewed in the PR, and a hundred kilobytes is not what the ignore
rules guard against. The video — 199.8 s, 10.4 MB of H.264 with that still as its cover —
stays on the machine that recorded it. **It was not picked for looking good.** The frame is the
report as it came out: the model corrected *How much it cost every month?* to *how much it
costs every month*, which fixes the verb and not the question, and filed it under word
order. The README's caption says so, because that is the measured state of the detector.

## 8. The narrated cuts

The owner asked for a video in LinkedIn's portrait shape and for a voice that explains it.
The example pointed to — another project's 1080×1350 cut — carries a silent track, flat at
−91 dB. **Chosen by the owner**: a local Piper narrator, a
short cut and the full walkthrough, and the app's own sound under the narration.

**Three roles, three voices.** The learner's clips were in the persona's voice, `lessac`, so
by ear the two sides of the conversation were one speaker. Two other voices spoke the
learner's turns into the stack's recogniser: `en_GB-alba-medium` came back verbatim, every
written mistake kept; `en_GB-northern_english_male-medium` turned *it have not* into *it had
not* and *flat I* into *flat-eye*. The learner is `alba` and the narrator
`en_US-ryan-high`, both run from the stack's own tts image, on ports 8104 and 8113 and a
volume of their own, so the running stack and its model cache are not touched.

**The answer's repeat was rewritten, because the recogniser tidied it.** Whisper wrote *the
the* as *the*, so the word said twice never reached the analyser. A phrase said twice
survives: *I want to, I want to* is transcribed as said, and `analyse()` counts it as one
repeat. *API* became *system*; it was heard as *APV*. In the new voice the reading comes
back at 3.8 % word error against the passage, one miss being *fill* heard as *feel* — the
contrast the passage drills.

**The narration was checked the same way.** Each of the 24 lines was synthesised and
transcribed, and three were reworded where Whisper heard *medium* for *median*, *past* for
*pass* and *set* for *said*. No line quotes a figure from the take: the lines are
synthesised before it starts, because each scene is held for as long as its line lasts,
and the stopwatch carries the measured times.

**The soundtrack is rebuilt from what the take did.** A browser recording is pictures
only. The recorder logs from the page when each clip started and when each `<audio>`
element began and stopped, fetches the replies before the take's sessions are deleted, and
writes every sound with its moment into the take's record. The mixer places them less the
head cut, lets the narration duck the app — a reply at −18.6 dB mean falls to −32.8 dB
under a line — normalises to −16 LUFS, and writes the narration as subtitles, which the
encoder takes with the picture. Frames either side of a reply's logged start show the page
before it arrived and after.

**Found while filming, and fixed.** The persona's opening line does not play by itself —
only a reply produced on the page autoplays — so the caption *The persona opens, out loud*
had been over silence. The full cut presses play, as a person would, and the short one does
not say *out loud*. A pause pressed with the mouse missed a button the transcript had
scrolled, and a reply ran on under the next scene; the press is now a checked click, and
the soundtrack follows what played either way. The poster put the marked words under the
sticky header; it is centred on them now.

**Found, not fixed.** In the report, the players of the learner's recording and of an
opening line nobody played show a length of 0:00, and an opening that was played shows
0:15 / 0:00. Why is not shown.

**The short cut has no reading.** A reading is 23 s of speech and 7–13 s of scoring, and
with its lines it was half the cut. The short cut is one turn, its report and the counted
figures; the reading and the answer are in the full cut. Nothing is edited out of either,
and the stopwatch stays.

**Measured in the final takes, at 1080×1350** — a load average of 3.5 as the short
take started, 5.5 to 10.8 across the full one:

| | short | full |
|---|---|---|
| Length | 77.8 s | 284.8 s |
| File | 9.9 MB | 28.7 MB |
| Narrated lines | 7 | 23 |
| First turn answered, with audio | 2.6 s | 2.4 s |
| Second turn | — | 2.8 s |
| Report | 1.3 s | 1.3 s |
| Reading scored | — | 7.3 s |
| Answer counted, feedback beside it | — | 3.8 s |
| Loudness | −16.2 LUFS, peak −2.2 dBFS | −16.2 LUFS, peak −2.2 dBFS |

Two earlier short takes were thrown away: the first opened on the silent line and ran
136 s with the reading; the second ran at a load average of 14.3 — its turn answered in
4.5 s and its reading scored in 13.3 s — and lost its pause. Each cut's video, poster and
subtitles stay on the machine that recorded them. LinkedIn does not read an embedded cover: the
poster is uploaded in the composer, and the `.srt` as the video's captions.

## 9. What is not settled

- **The videos are attached nowhere.** The README shows a still; the wide take and the two
  portrait cuts are the owner's to upload.
- **S2 has not been re-measured on a quiet machine** since the turn's path changed.
- **A person's microphone has never been through the interface** in Chrome or Safari; the
  take and *Make your point*'s end-to-end check replay a synthetic voice.
- **The export has no import**, and an account cannot be deleted.
