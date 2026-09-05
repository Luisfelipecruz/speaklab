/**
 * The read-aloud screen: record, upload, poll, show.
 *
 * The behaviour worth testing here is the *sequence*, because it is where a plausible
 * implementation goes wrong invisibly. `POST /attempts` returns before the phones exist,
 * so a screen that rendered the response as final would show every reading as having no
 * pronunciation scores — and would look, to a user, exactly like `pron` being down.
 *
 * The recorder is mocked rather than driven: `useRecorder` has its own suite, jsdom has
 * no microphone, and what this component does with a clip is independent of how the clip
 * was produced.
 */

import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { PassageReader } from "@/components/PassageReader";
import { ApiError } from "@/lib/api";
import { makeAttempt, makePassage, makePhoneme } from "@/test/fixtures";

jest.mock("@/lib/api", () => ({
  ...jest.requireActual("@/lib/api"),
  postAttempt: jest.fn(),
  getAttempt: jest.fn(),
  rescoreAttempt: jest.fn(),
}));

const CLIP = {
  blob: new Blob(["x"]),
  filename: "reading.webm",
  durationMs: 30_000,
  mimeType: "audio/webm",
};

/**
 * A stateful stand-in for `useRecorder`.
 *
 * It has to hold real state and re-render, not return a frozen object: `RecordButton`
 * only fires `onStop` while the phase is `recording`, so a mock whose `state` never
 * changes turns every release into a no-op and every test into a silent false pass. The
 * hook's own behaviour — permissions, containers, the minimum clip length — is covered by
 * `useRecorder.test.tsx`; what is stood in for here is only the state machine's shape.
 */
jest.mock("@/hooks/useRecorder", () => {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const React = require("react");
  return {
    useRecorder: () => {
      const [state, setState] = React.useState("idle");
      return {
        state,
        error: null,
        mimeType: "audio/webm",
        analyser: null,
        elapsedMs: 0,
        start: async () => setState("recording"),
        stop: async () => {
          setState("idle");
          return CLIP;
        },
        cancel: () => setState("idle"),
        clearError: () => {},
      };
    },
  };
});

// eslint-disable-next-line @typescript-eslint/no-require-imports
const api = require("@/lib/api");

beforeEach(() => {
  jest.clearAllMocks();
  jest.useFakeTimers();
});

afterEach(() => {
  jest.useRealTimers();
});

/** Advance past one poll interval and let the promise it started settle. */
async function tick() {
  await act(async () => {
    jest.advanceTimersByTime(1500);
  });
}

/** Hold the button, then release — the whole gesture, as a person performs it. */
async function record() {
  const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
  const button = screen.getByRole("button", { name: /hold to speak/i });
  await act(async () => {
    await user.pointer({ keys: "[MouseLeft>]", target: button });
  });
  await act(async () => {
    await user.pointer({ keys: "[/MouseLeft]", target: button });
  });
}

test("the passage is readable before anything is recorded", () => {
  // Server-rendered and legible with no JavaScript having run — which matters more here
  // than anywhere else in the app, because the text is what the user is about to perform.
  render(<PassageReader passage={makePassage()} />);

  expect(screen.getByText(/The theatre on Third Street is worth the trip/)).toBeInTheDocument();
});

test("a reading shows its transcript before the phones have arrived", async () => {
  api.postAttempt.mockResolvedValue(makeAttempt({ status: "pending", phonemes: [] }));
  api.getAttempt.mockResolvedValue(
    makeAttempt({
      status: "scored",
      phonemes: [makePhoneme({ word_idx: 1, canonical_phone: "TH", recognized_phone: "s", gop: -9.4 })],
      summary: { phones: 1, mean_gop: -9.4, median_gop: -9.4, percentile_5: -9.4, r_composites: 0, blank_dominated: 0 },
    }),
  );

  render(<PassageReader passage={makePassage()} />);
  await record();

  await waitFor(() => expect(api.postAttempt).toHaveBeenCalledTimes(1));
  expect(screen.getByText(/Aligning the sounds/)).toBeInTheDocument();

  await tick();
  await waitFor(() => expect(screen.getByText(/i sanked the usher/)).toBeInTheDocument());
});

test("polling stops as soon as the attempt reaches a terminal state", async () => {
  api.postAttempt.mockResolvedValue(makeAttempt({ status: "pending" }));
  api.getAttempt.mockResolvedValue(makeAttempt({ status: "scored" }));

  render(<PassageReader passage={makePassage()} />);
  await record();
  await waitFor(() => expect(api.postAttempt).toHaveBeenCalled());

  await tick();
  const afterFirst = api.getAttempt.mock.calls.length;
  await tick();
  await tick();

  expect(api.getAttempt.mock.calls.length).toBe(afterFirst);
});

test("the passage is sent with the reading, not guessed at by the server", async () => {
  api.postAttempt.mockResolvedValue(makeAttempt({ status: "scored" }));

  render(<PassageReader passage={makePassage({ slug: "the-ship-and-the-sheep" })} />);
  await record();

  await waitFor(() =>
    expect(api.postAttempt).toHaveBeenCalledWith(
      "the-ship-and-the-sheep",
      CLIP.blob,
      "reading.webm",
    ),
  );
});

test("with the scorer off the reading is kept and the fix is offered", async () => {
  // PRD R6, and the default state of a fresh clone. This must not read as a failure:
  // nothing was lost, and the reading can be scored later without being read again.
  api.postAttempt.mockResolvedValue(makeAttempt({ status: "pending" }));
  api.getAttempt.mockResolvedValue(
    makeAttempt({
      status: "scored",
      pronunciation: "unavailable",
      pronunciation_detail: "The pronunciation scorer is not running, so this reading has a transcript but no phoneme scores.",
      phonemes: [],
    }),
  );

  render(<PassageReader passage={makePassage()} />);
  await record();
  await waitFor(() => expect(api.postAttempt).toHaveBeenCalled());
  await tick();

  await waitFor(() =>
    expect(screen.getByText(/The pronunciation scorer is not running/)).toBeInTheDocument(),
  );
  expect(screen.getByText(/make pron-up/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /score it again/i })).toBeInTheDocument();
  // The transcript is still there. That is the requirement.
  expect(screen.getByText(/i sanked the usher/)).toBeInTheDocument();
});

test("a failed upload keeps the recording so nobody reads it twice", async () => {
  // Seventy-nine words. Asking for them again because a request timed out is the one
  // thing this screen must not do — the same bargain useSession makes for a turn.
  api.postAttempt.mockRejectedValueOnce(new ApiError("The recogniser is not responding.", 503));

  render(<PassageReader passage={makePassage()} />);
  await record();

  await waitFor(() =>
    expect(screen.getByText("The recogniser is not responding.")).toBeInTheDocument(),
  );

  const retry = screen.getByRole("button", { name: /send it again/i });
  api.postAttempt.mockResolvedValue(makeAttempt({ status: "scored" }));

  const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
  await act(async () => {
    await user.click(retry);
  });

  expect(api.postAttempt).toHaveBeenCalledTimes(2);
  expect(api.postAttempt.mock.calls[1][1]).toBe(CLIP.blob);
});

test("a reading of some other text says the scores are not worth much", async () => {
  api.postAttempt.mockResolvedValue(makeAttempt({ status: "scored", wer: 0.92 }));

  render(<PassageReader passage={makePassage()} />);
  await record();

  await waitFor(() => expect(screen.getByText(/92%/)).toBeInTheDocument());
  expect(screen.getByText(/unlikely to mean much/)).toBeInTheDocument();
});

test("a good reading does not get the warning", async () => {
  api.postAttempt.mockResolvedValue(makeAttempt({ status: "scored", wer: 0.04 }));

  render(<PassageReader passage={makePassage()} />);
  await record();

  await waitFor(() => expect(screen.getByText(/4%/)).toBeInTheDocument());
  expect(screen.queryByText(/unlikely to mean much/)).not.toBeInTheDocument();
});

test("polling gives up rather than hammering an attempt stuck in scoring", async () => {
  // The job runs in the API process, so a restart mid-alignment leaves an attempt in
  // `scoring` forever. Without a ceiling this poller would run until the tab closed.
  api.postAttempt.mockResolvedValue(makeAttempt({ status: "pending" }));
  api.getAttempt.mockResolvedValue(makeAttempt({ status: "scoring" }));

  render(<PassageReader passage={makePassage()} />);
  await record();
  await waitFor(() => expect(api.postAttempt).toHaveBeenCalled());

  for (let i = 0; i < 41; i += 1) await tick();

  await waitFor(() =>
    expect(screen.getByText(/taking longer than expected/)).toBeInTheDocument(),
  );
  expect(api.getAttempt.mock.calls.length).toBeLessThanOrEqual(40);
});
