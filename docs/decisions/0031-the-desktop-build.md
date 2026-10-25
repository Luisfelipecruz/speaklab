# 0031 — The app for this Mac

Status: accepted

SpeakLab runs as a Compose stack: six containers and a language model on the host. Opening
Docker and a terminal to practise for ten minutes is a cost paid every time, and an app on
the Mac removes it — provided the app runs the same services, unchanged, and earns the same
figures. This records what the app is made of, why each piece is that piece, and what was
measured on the app itself before any of it was claimed.

## What was decided

1. **The window is Electron, and the services run unchanged as processes beside it.** The
   main process is a supervisor that runs Compose's graph — Postgres, the migration, the
   seed, the API and the three model services — as processes, and Next's standalone server
   in Electron's own utility process, with one window on it. Nothing in the API, the model
   services or the frontend knows it is in an app: each process is given Compose's
   environment, with the addresses moved to `127.0.0.1` and the paths to the app's folders.
   The frontend is a Next server with server components, and Electron runs it on its own
   Node; a shell without a Node of its own would need a second runtime beside it, and a
   rewrite of any service would be a second product to measure.

2. **Postgres 16 is the theseus-rs build, private to the app.** Not SQLite: the schema,
   the migrations and the suite are Postgres's, and a second dialect would be a second
   system to verify. Not an embedded build that ships the server without its client tools:
   theseus-rs's 16.15 is a thin arm64 build with every one of them, and `pg_dump` and
   `pg_restore` are what make a backup and a restore possible. The cluster lives in the person's data folder,
   listens on `127.0.0.1` with no socket, and is started and stopped by the supervisor.

3. **Text sorts by macOS's collation, and the difference is accepted.** The build carries
   no ICU, and macOS's libc orders a space before any letter where glibc skips spaces, so
   two passage titles change places against Compose. One ordering everywhere would need
   ICU on both sides, at two different ICU versions, or `COLLATE "C"` on the ordered
   columns — a migration for an order nothing depends on. No figure is computed from an
   order.

4. **Ollama stays on the host.** The app does not carry a 9.6 GB model or the runtime that
   serves it on the GPU. It asks the API what Ollama's state is and says, in words, what to
   do when it does not answer or holds a different build.

5. **Sign-in stays.** The app is a local server with a database of accounts, as the stack
   is; a local profile would be a second way in to build and maintain. The first launch
   opens on registration.

6. **The weights are fetched on the first launch, not shipped.** 1.75 GB at pinned
   revisions, each file checked against its SHA-256 before it is used, into Hugging Face's
   own cache layout, so that the services load them offline exactly as they load the
   containers' downloads. The app stays at 2.1 GB, and a download that stops resumes.

7. **The build brings its own tools, and the app is signed ad hoc.** CPython, uv, Node,
   pnpm and Postgres are downloaded into the build folder and checked against their
   publishers' checksums; the Mac's own tools take no part. The app is signed ad hoc with
   the hardened runtime, which runs it on the Mac that built it and nowhere else. A
   Developer ID, notarisation and updates are a separate step.

8. **The API picks up owed work when it starts — in Compose too.** A desktop app is quit,
   slept and killed far more often than a container is restarted, and every background job
   is a task of the process that took the request. Claims left by a process that is gone
   are released before the first request; then the owed scoring waits for `pron`'s model,
   one batch of owed analysis waits for the labelling model, and stale progress is rolled
   up. Waiting matters: a reading scored while `pron` loads, or a turn analysed while
   Ollama is down, would be closed for good without what it waited for.

9. **A recording is found by its account and its digest.** The stored path names the root
   a file was first written under, and in the app that root is a folder in the person's
   Library: a backup restored somewhere new, or Compose's history moved in, would have
   served every recording as an error. The path is rebuilt under the root the API runs
   with; the stored one is kept as a record.

10. **A backup is `pg_dump` and a copy of the recordings.** File → Back Up… writes both, and
    restoring is a few documented commands into an app that has been quit. Copying a
    running cluster's files is not a backup.

## Measured

On the built app, against the Compose stack on the same machine at the same commit:

- **Every golden figure is the same.** WER 4 of 232 words, **1.72 %**; a mistake heard as its
  correction 2 of 89; fillers heard 21 of 24; GOP threshold −3.119, mean drop +8.138,
  9 of 10 detected and 10 of 10 named.
- **The API suite passes on the app's Postgres** with the counts it has on Compose's:
  1 235 pass, 42 skip. The collation difference moves no test.
- **A whole turn keeps its budget.** p95 over four runs of twenty turns each, alternating
  with Docker's recogniser and voice: the app **1 908–2 598 ms**, Docker 1 944–2 631 ms;
  every run of both inside 3 000 ms.
- **The window shows in 1.66–2.06 s** from the process starting, warm, and every model is
  loaded by 4.9 s. A quit leaves no process in under half a second. After a hard kill the
  next launch stops what was left and opens the window at 1.9 s; with every process killed
  at once, Postgres replays its log in 155 ms and nobody touches anything.
- **About 3.6 GB resident with every model loaded**, pron 1.8 GB of it — 1.1 GB of that its
  weights, mapped from disk — and Ollama's runner 6.9 GB beside it.
- **A backup restored into a fresh install** gives every table its row count back, and every
  recording its SHA-256, and the restored app serves them. The Compose history, moved in
  the same way, comes out the same, every recording found under the app's own folder.

## Costs

- **This Mac only**, until the app is signed with a Developer ID.
- **Two systems.** The app's database is its own; the history on the Compose stack is moved
  across by hand, once.
- **A memory floor near 16 GB** with Ollama's model loaded.
- **Two orderings of text**, one per collation.

## Revisit if

- A Developer ID is available: notarisation and an update channel follow.
- theseus-rs stops publishing the 16.x line, or lags a security release.
- A list's order starts to carry meaning, so that the collation matters.
- A second machine needs the app, which is the step this record does not take.
