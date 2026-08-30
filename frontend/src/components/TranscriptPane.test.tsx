/**
 * The transcript: order, announcement, and which turn is allowed to speak on its own.
 *
 * `role="log"` is the assertion that matters most here. A plain `aria-live` region on a
 * growing transcript re-announces what changed inside it, which for a screen reader
 * means hearing the conversation restart every time a turn arrives; `log` means new
 * entries are appended and only the new one is read.
 */

import { render, screen, within } from "@testing-library/react";

import { TranscriptPane } from "@/components/TranscriptPane";
import { makeTurn } from "@/test/fixtures";

beforeEach(() => jest.clearAllMocks());

const HISTORY = [
  { kind: "stored" as const, turn: makeTurn({ id: 1, idx: 0, transcript: "Shall we start?" }) },
  {
    kind: "stored" as const,
    turn: makeTurn({ id: 2, idx: 1, role: "user" as const, transcript: "I led the migration." }),
  },
  { kind: "stored" as const, turn: makeTurn({ id: 3, idx: 2, transcript: "Over what period?" }) },
];

test("the transcript is a log, so a screen reader hears additions and not repeats", () => {
  render(<TranscriptPane items={HISTORY} />);

  const log = screen.getByRole("log", { name: "Conversation transcript" });
  expect(log).toHaveAttribute("aria-live", "polite");
});

test("turns render in the order they were spoken, with the pending one last", () => {
  render(
    <TranscriptPane
      items={[...HISTORY, { kind: "pending", localId: "p1", durationMs: 3000 }]}
      speakerLabel="Dana"
    />,
  );

  const log = screen.getByRole("log");
  const spoken = within(log)
    .getAllByText(/Shall we start\?|I led the migration\.|Over what period\?|Transcribing/)
    .map((node) => node.textContent);

  expect(spoken[0]).toMatch(/Shall we start/);
  expect(spoken.at(-1)).toMatch(/Transcribing/);
});

test("an empty conversation says so rather than rendering a blank panel", () => {
  render(<TranscriptPane items={[]} />);

  expect(screen.getByText(/no turns yet/)).toBeInTheDocument();
});

test("a reloaded transcript does not start talking on its own", () => {
  // The rule is "this turn", not "the last turn". After a reload the last turn is an old
  // reply, and a page that starts speaking when you open it is one nobody opens twice.
  render(<TranscriptPane items={HISTORY} autoPlayTurnId={null} />);

  expect(window.HTMLMediaElement.prototype.play).not.toHaveBeenCalled();
});

test("a reply that has just arrived speaks once, and not again on every re-render", () => {
  const { rerender } = render(
    <TranscriptPane items={HISTORY.slice(0, 2)} autoPlayTurnId={null} />,
  );

  rerender(<TranscriptPane items={HISTORY} autoPlayTurnId={3} />);
  expect(window.HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(1);

  // The conversation screen re-renders roughly ten times a second while recording (the
  // elapsed clock). If the autoplay effect watched the flag rather than the source, the
  // reply would restart on every one of those.
  rerender(<TranscriptPane items={HISTORY} autoPlayTurnId={3} />);
  rerender(<TranscriptPane items={HISTORY} autoPlayTurnId={3} />);
  expect(window.HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(1);
});
