# 0024 — Every recording's length, and a built frontend

Status: accepted

Two things the product did wrongly on screen or served in the wrong shape: the players on a
transcript read `0:00 / 0:00` for recordings that have a length, and the default stack
served the frontend from the development server. This records how each is fixed and what
was measured before and after.

## What was decided

1. **The player takes a recording's length from the element whenever the element has
   one.** A length went missing in two ways. A WebM as Chrome's MediaRecorder writes it
   declares no length, and the browser reports it as infinite. A player rendered on the
   server with the transcript reads its file's header before React attaches a handler, so
   the one event that carries the length has already fired when the component could hear
   it. The player now reads the element's length when it mounts, listens to
   `durationchange` as well as `loadedmetadata`, and resolves an infinite length by
   seeking past the end: the browser reads to the end to answer, the length arrives in a
   `durationchange`, and the player returns to the start without showing the seek. A
   length passed in as a prop stands until the element has one.
2. **The turn does not carry the stored length.** `audio_assets.duration_ms` is measured
   and never null, and a turn could return it; the player alone gives every page a length,
   so the wire shape stays as it is.
3. **The default stack serves a built frontend.** The frontend's image is built in stages
   from one install: `next build` with `output: "standalone"`, then a final stage holding
   only the traced `server.js`, the modules it imports and the static assets, running as
   `node`, with no package manager. The browser's address for the API is compiled into the
   bundle by `next build`, so it is a build argument; the server's is read at runtime.
4. **The development server stays, behind a profile.** `frontend-dev`, in the `dev`
   profile, is the same install with the source bind-mounted and `next dev` running, on
   the same port. `make dev` swaps it in and `make up` swaps it back. The frontend's tests,
   types and lint run in its image, because the built one carries no test tools.

## Measured

The players, on one conversation turn through the recorder's synthetic voice in headless
Chromium — each player's text on the page as the client rendered it, and after a reload,
as the server rendered it:

| Player | Before | After |
|---|---|---|
| The persona's opening, a WAV | `0:00 / 0:00`, the element at 15.17 s | `0:00 / 0:15` |
| The learner's turn, a MediaRecorder WebM | `0:00 / 0:00`, the element at `Infinity` | `0:00 / 0:06` |
| The persona's reply, a WAV, after a reload | `0:00 / 0:00`, the element at 16.07 s | `0:00 / 0:18` |

The same run against the built frontend gives every player its length, before and after a
reload. The stored files agree: every WAV declares its length in its header, and none of
the four learner WebMs read carries a Duration element.

The frontend, before and after:

| | The development server | The built frontend |
|---|---|---|
| Image | 1.06 GB | **299 MB** |
| Memory, idle | 339 MiB, 695 MiB once two routes had compiled | **93 MiB** |
| A route's first visit | 0.63 s, compiling | **0.03–0.21 s** |
| HIGH or CRITICAL in the image, Trivy 0.74.0 | 0 | 0 |

Jest 319 across 49 suites, `tsc` and ESLint are clean in the development image. The five
default containers use 1.02 GiB after a conversation, a reading and an answer.

The narrated portrait cuts are re-recorded on the built frontend, each started on a quiet
machine, and every player on both posters shows its length. The short cut runs 77.1 s, its
turn answered in 2.6 s and its report in 1.3 s; the full one runs 286.3 s, its turns
answered in 2.4 and 2.8 s, the reading scored in 7.3 s and the answer counted in 4.3 s.

## Revisit if

- A browser shows a length that differs from the stored one by more than rounding: the
  stored length then joins the turn.
- Anything in the default stack comes to need the development server's behaviour.
