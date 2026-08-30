# 0004 — Recording in a browser, and what the streaming payoff actually was

**Status:** accepted · **Date:** 2026-08-30 · **Milestone:** m7

Read this before touching the recorder, the turn round trip, or anything that claims a
latency number the user can feel.

---

## What was decided

1. **Push and hold**, with Space bound to keydown and keyup as the *same* held gesture —
   not voice-activity detection, and not click-to-toggle.
2. **The container is negotiated per browser** (Opus/WebM, then MP4/AAC, then whatever
   the browser picks), and normalisation stays where it already was: at the service
   boundary, not in the page.
3. **Four microphone failures are four named states**, each with a sentence saying what
   to do next, and the origin is what tells two of them apart.
4. **The transcript is server-rendered with the cookie forwarded**, then hydrated. FR-10
   is about what is on the screen after a reload, not about what can be fetched after it.
5. **Recording is closed while the reply is speaking.**
6. **Time-to-first-audio in the browser is the whole turn**, and decision 0003 §3's
   expectation that m7 would collect the streaming payoff **is not met by this
   milestone**. §3 below is the correction.

---

## 1. Push and hold, and why the keyboard is not a fallback

The three candidate gestures fail differently.

**Voice-activity detection** decides for itself when a sentence ended. It is wrong on a
pause for thought, and this product is for people who pause mid-sentence more than most —
that is close to the definition of a language learner. Being cut off mid-clause is worse
than any amount of button-holding, because the turn that reaches the recogniser is not the
turn the speaker meant to give.

**Click to start, click to stop** leaves the microphone open when somebody forgets the
second click, and "the microphone was on for six minutes" is a privacy failure in a
product whose main claim is that nothing leaves the machine.

**Hold** is the one gesture where the person and the machine agree about when speech
ended. It costs the ability to record a long turn comfortably, which is a real cost and is
accepted: the seeded rubrics ask for eight to twelve turns, not monologues.

The keyboard binding follows from that and is not an accessibility afterthought. PRD §9.2
requires keyboard-operable recording, so Space is bound to **keydown and keyup**, exactly
like the pointer. A click handler would have no held state at all — it would be a
different interaction wearing the same button.

Two details that are easy to get wrong and are both covered by tests:

- **The browser's own activation must be suppressed.** A `<button>` fires `click` on Space
  *keyup*. Without `preventDefault`, every keyboard recording ends by starting an empty
  second one.
- **A held key auto-repeats.** The browser sends `keydown` over and over with `repeat`
  set, and each one would restart the recording. `user-event` has no notion of
  auto-repeat, so that test uses a raw event — the one place in this suite where that is
  the honest way to reproduce what a finger on the space bar does.

Pointer capture matters as much as either: without it, dragging off the button mid-sentence
delivers `pointerup` somewhere else and the recording never stops.

---

## 2. Containers, and where normalisation belongs

`MediaRecorder` produces Opus in WebM on Chrome and Edge, and AAC in MP4 on Safari. The
list of candidates is tried in order and the empty string is the deliberate last entry —
it tells the browser to choose, which is better than refusing to record on a browser whose
container this project has not heard of.

Being liberal here is free because the decision was already taken one layer down: trap 3
says normalise to 16 kHz mono PCM **at the service boundary**, and `services/audio.py`
does, through PyAV. The browser's job is to produce something ffmpeg reads. Transcoding in
the page would move work onto the weakest machine in the system to save a step on the
strongest.

The filename carries the container (`turn.webm`, `turn.m4a`) as a hint, not as a contract.
The recogniser sniffs the bytes.

---

## 3. Time-to-first-audio: the correction to 0003 §3

Decision 0003 measured PRD §9.1's first fallback — streaming the reply into the voice
sentence by sentence — and found it buys about 140 ms at the median, roughly a twentieth
of a turn. It then said:

> It stays on. It is free, it is bounded-correct, and its real payoff is m7: when the
> browser plays sentence one while sentence two is still being synthesised, the number
> that matters stops being turn latency and becomes time-to-first-audio, where m5
> measured 78 ms against 320 ms.

**m7 does not collect that payoff, and could not have.** The claim assumed a delivery
mechanism that does not exist: `POST /sessions/{id}/turns` concatenates the synthesised
sentences into one WAV (`services/wav.py`) and stores it as a single content-addressed
asset. The browser receives one `audio_url` after the whole turn has completed. So the
first sound a user hears arrives at **turn latency**, not at first-sentence latency, and
the 78 ms figure describes a boundary inside the API that nothing downstream can observe.

The overlap is still worth having — it shortens the turn, which is what the p95 budget is
measured against — but its benefit is entirely server-side, and the sentence above
overstated it. This document is the correction; 0003 is left as written, because a
decision log that gets edited to look right afterwards is not a log.

**What it would actually take**, so this is a decision and not a complaint:

- A streaming turn endpoint — chunked or SSE — emitting each sentence's audio as it is
  synthesised, and a client that queues those into playback.
- A different failure contract. The current endpoint is **atomic**: on a failure nothing
  is written, and the browser still holds the recording, so a retry is the same bytes.
  Once the first sentence has been played, "nothing happened" is no longer available as
  an outcome, and the turn has to become resumable instead.
- A second code path for the same operation, since the atomic one is what a page reload
  reads (FR-10).

That is a milestone's worth of work to recover a fraction of ~2.4 s, on a screen where the
person has just finished speaking and is not yet listening. It is **not** scheduled. The
honest measurement to make first is whether a user notices the difference at all, which
needs users, not another endpoint.

**What m7 does instead** is make the wait legible rather than shorter. The stage
breakdown is on the screen — `heard 1.1s, thought 0.9s, spoke 0.2s` — because
`TurnTiming` is returned on every turn precisely so it can be, and because a latency
regression is felt long before it is noticed (PRD R3). It also makes the honest thing
visible: on a contended machine these figures nearly triple (0003 §3), and a user who can
see that knows the machine is loaded rather than assuming the application is broken.

---

## 3a. The first real conversation, and what it cost

A person held the button and had a seven-turn conversation with the apartment-viewing
persona on 2026-08-30 — the first time this product has run on speech that was not
LibriSpeech. It worked: three user turns transcribed at confidence 0.90, 0.90 and 0.93, the
persona in character throughout, every reply ending on a complete sentence, all seven audio
assets on disk.

**The turns took 16 to 30 seconds each.** Three things were suspected and only one of them
was true.

### It was not the recording length, and that is a new measurement

The obvious hypothesis is that ASR scales with audio, and the real recordings were **14.5 s
to 28.4 s** where the measurement corpus is 4.45–6.82 s. PRD §9.1's budget line even says
so: *"ASR (`small.en`, ~6 s of audio) ≤ 700 ms"*.

Measured directly, interleaved round-robin so that load drift hits every clip equally:

| clip | audio | ASR median | per audio-second |
|---|---|---|---|
| golden, read speech | 11.0 s | 1227 ms | 112 ms |
| real learner turn | 14.5 s | 1268 ms | 88 ms |
| real learner turn | 22.0 s | 1257 ms | 57 ms |
| real learner turn | 28.4 s | 1566 ms | 55 ms |

**ASR is very nearly flat in audio length.** 28 seconds of speech costs 1.6 s, barely more
than 11 seconds costs. faster-whisper batches the whole utterance, so per-audio-second cost
*falls* as clips get longer — the fixed overhead dominates. A 30-second turn is not
expensive to transcribe.

That is worth writing down because the intuition is so strong the other way, and because it
retires a fear about m8: a read-aloud passage is longer than a conversational turn and will
not cost proportionally more.

### It was the machine, and the effect is larger than 0003 measured

`make turn-latency`, same 20 turns, same code:

| | 0003, load 1.74 | now, load 3.1 / 11.4 / 13.0 |
|---|---|---|
| whole turn, median | 2353 ms | 4070 ms |
| **whole turn, p95** | **2684 ms — met** | **5180 ms — missed by 2180 ms** |
| ASR, median | 1146 ms | 1488 ms |
| generation, median | 872 ms | 1580 ms |
| synthesis tail, median | 235 ms | 805 ms |

The stages degrade unevenly: ASR 1.3×, generation 1.8×, **synthesis tail 3.4×**. The voice
is the most load-sensitive component in the turn, which is the opposite of what its 235 ms
median suggests when the machine is idle.

The conversation above ran at load **22–30**, roughly double the "contended" case 0003
recorded, and its 16–30 s turns sit where that curve predicts. **No part of it is an m7
defect and no part of it is the recordings being long.**

### What this actually means

**The 3000 ms budget is a quiet-machine number, and it has now been missed twice.** m6 met
it at load 1.74; a laptop that is also running a Docker build and two other stacks does not.
This is not new information — 0003 §3 recorded 7283 ms at load 10–16 — but it is the first
time it was observed by a person using the product rather than by a test suite, and the
experience of a 25-second turn is qualitatively different from a table row saying 7283.

Nothing is being changed in response, for the reason PRD §9.1's own fallback list implies:
every remaining lever (a smaller recogniser, a shorter reply cap, a smaller model) trades
quality for a latency problem that the target machine does not have when it is doing one
thing at a time. What follows instead is the honest statement, in the README and here:
**this product's latency is dominated by what else is running on the machine**, and a
number quoted without its load average is not a measurement.

---

## 4. Four failures, four sentences

Every one of these is silent by default — an unhandled promise rejection in a console the
user does not have open — and all four look identical from the outside: a button that does
nothing.

| State | What actually happened | What the user is told |
|---|---|---|
| `insecure-context` | The page is not on `https` or `localhost`, so `navigator.mediaDevices` is absent | Open it at `http://localhost:3003` |
| `no-mediarecorder` | The browser has no `MediaRecorder` | Chrome, Edge, or Safari 16+ |
| `permission-denied` | `NotAllowedError` | Allow it in the address bar and try again |
| `no-device` / `device-busy` | `NotFoundError` / `NotReadableError` | Connect a microphone; or close the app holding it |

The first two are told apart **by the origin, and only by the origin** — the missing API
is byte-for-byte the same. Checking `isSecureContext` first would be wrong in both
directions: it says nothing about whether the browser can record, and a browser that
plainly can would be told to change its URL. So the check runs only once something is
actually missing. That branch was confirmed in a real browser during m7, by accident: the
test browser reaches the app on `host.docker.internal:3003`, which is not a secure origin,
and the page correctly refused to record and said why.

A fifth state is not a failure at all. **A tap is refused locally** — under 400 ms is a
mis-click, and sending it costs a round trip through three model services to be told there
was no speech, when the browser can say "hold the button while you speak" immediately.

And a sixth thing is not a state but a picture. The **live waveform** is the only honest
signal that the microphone is working: muted hardware, the wrong input device selected in
the OS, and a granted permission over a dead track all produce a flat line, and a flat
line is a diagnosis where a spinner is reassurance about nothing. Because a person who has
never seen a waveform cannot read a flat one, it also says so in words after 1.8 s of
silence.

---

## 5. Server-rendered, then hydrated

The transcript is fetched on the Next.js server with the incoming `Cookie` header
forwarded explicitly (`lib/server-api.ts`), and handed to the client component as its
initial state.

There is no shared cookie jar between the browser and the Next.js server — m3's
`lib/auth.ts` wrote that down as a warning a milestone before anything needed it — so a
server component fetching `/sessions/12` gets a 401 unless the header is forwarded by
hand.

The alternative, fetching from the client on mount, satisfies the letter of FR-10 and not
its point: a session that survives a page reload is one that is **on the screen** after the
reload, not one that can be retrieved a round trip later. A spinner over a conversation the
server already had is a worse answer than the conversation.

Two consequences worth stating:

- **A 401 and a 404 render the same thing.** The API answers 404 for somebody else's
  session so that guessing an id tells you nothing (D25); a page that said "you are not
  allowed to see session 41" would hand back exactly the fact the server withheld.
- **`GET /audio/{id}` is called from the browser**, with the cookie, so its ownership
  check is the one that matters. The server-rendered transcript carries paths, not audio.

---

## 6. Recording is closed while the reply plays

A microphone open while the speakers play the persona records **the persona**, and the
recogniser then transcribes SpeakLab's own voice as though the learner had said it. It is
trap 3 arriving through the room instead of through a codec, and it would be invisible in
the data: a perfectly confident transcript of a sentence nobody spoke.

So the record button has a `playing` state that blocks the gesture, and the pause control
on the player is the way out for somebody who wants to answer sooner. The alternative —
stopping playback automatically when recording starts — was rejected because it needs the
transcript to reach into a player it does not own, and the failure mode of getting it
wrong is the echo above.

The reply auto-plays through **the visible player**, not a hidden element. A hidden one is
simpler and produces a player sitting at `0:00` while sound comes out of the speakers.

An autoplay the browser refuses is **not** a failure state. Every browser blocks audio
until the page has been interacted with; the player's `failed` state means "this recording
could not be loaded", which is a different and much more alarming claim. A rejected
`play()` leaves the control idle and pressable, exactly as though nobody had tried.

---

## 7. Revisit when

- **A user says the wait after speaking is too long.** Then §3's streaming endpoint has a
  reason to exist, and the first thing to measure is time-to-first-audio against turn
  latency with a person in the room.
- **A browser other than Chrome/Edge/Safari matters.** The container list is the only
  place that would need to know.
- **Q10 is answered and the voice changes.** Nothing here depends on which voice speaks,
  but the auto-play decision assumes the reply is worth listening to.
- **A turn ever needs to be resumable.** That is the same change as §3 and should be made
  once, not twice.
