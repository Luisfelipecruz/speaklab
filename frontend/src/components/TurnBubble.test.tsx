/**
 * One turn, and the four things it must not get wrong.
 *
 * Three of them are about silence. A turn with no audio has two entirely different
 * causes — the voice failed, or the account has audio retention switched off (FR-26) —
 * and rendering nothing in both cases turns a working privacy setting into what looks
 * like data loss.
 */

import { render, screen } from "@testing-library/react";

import { TurnBubble } from "@/components/TurnBubble";
import { makeTurn } from "@/test/fixtures";

test("a turn in flight says what is happening and invents no words", () => {
  render(<TurnBubble item={{ kind: "pending", localId: "p1", durationMs: 4200 }} />);

  expect(screen.getByText(/Transcribing 4.2s of audio/)).toBeInTheDocument();
  // The recogniser is the only thing that knows what was said. Anything in this bubble
  // that looked like a transcript would be the interface making one up.
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
});

test("a reply with audio mounts a player captioned with its own text", () => {
  render(
    <TurnBubble
      item={{ kind: "stored", turn: makeTurn({ transcript: "Over what period?" }) }}
      speakerLabel="Dana"
    />,
  );

  expect(screen.getByText("Dana")).toBeInTheDocument();
  // PRD §9.2 requires captions on all synthesised speech.
  expect(screen.getAllByText("Over what period?")).toHaveLength(2);
  expect(screen.getByRole("button", { name: /Play Dana's reply/ })).toBeInTheDocument();
});

test("a reply the voice could not speak says so rather than showing nothing", () => {
  render(
    <TurnBubble
      item={{
        kind: "stored",
        turn: makeTurn({ audio_asset_id: null, audio_url: null }),
      }}
      speech={{
        status: "unavailable",
        detail: "the voice service is not responding",
        voice: null,
        duration_ms: null,
        sample_rate: null,
        sentences: 0,
      }}
    />,
  );

  expect(screen.getByText(/could not speak this reply/)).toBeInTheDocument();
  expect(screen.getByText(/not responding/)).toBeInTheDocument();
});

test("a kept transcript with a dropped recording is explained as the setting it is", () => {
  render(
    <TurnBubble
      item={{
        kind: "stored",
        turn: makeTurn({
          role: "user",
          transcript: "I led the migration.",
          audio_asset_id: null,
          audio_url: null,
        }),
      }}
    />,
  );

  expect(screen.getByText(/Audio retention is off/)).toBeInTheDocument();
  expect(screen.getByText(/measurements were/)).toBeInTheDocument();
});

test("a low-confidence turn is marked and the consequence is spelled out", () => {
  render(
    <TurnBubble
      item={{
        kind: "stored",
        turn: makeTurn({ role: "user", asr_confidence: 0.21, low_confidence: true }),
      }}
    />,
  );

  expect(screen.getByText(/heard with low confidence/)).toBeInTheDocument();
  // R2: a mishearing scored as a grammar error is a correction nobody can act on, so
  // the user is told the turn is excluded rather than left to wonder.
  expect(screen.getByText(/will not count towards your\s+accuracy/)).toBeInTheDocument();
});

test("a confident turn carries no warning at all", () => {
  render(
    <TurnBubble
      item={{ kind: "stored", turn: makeTurn({ role: "user", asr_confidence: 0.94 }) }}
    />,
  );

  expect(screen.queryByText(/low confidence/)).not.toBeInTheDocument();
});

test("a turn with nothing transcribed says that, instead of rendering an empty bubble", () => {
  render(
    <TurnBubble item={{ kind: "stored", turn: makeTurn({ role: "user", transcript: null }) }} />,
  );

  expect(screen.getByText(/Nothing was transcribed/)).toBeInTheDocument();
});
