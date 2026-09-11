/**
 * Say the sentence, see what was heard.
 *
 * The microphone is replaced: no test environment has one, and the recorder's own states
 * are tested with it. What is tested here is the round trip — the clip goes to this
 * correction's drill, and what comes back is shown — and that a recording that fails to
 * send is kept and sent again as it was.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { DrillRecorder } from "@/components/DrillRecorder";
import { ApiError } from "@/lib/api";
import { makeDrill, makeDrillResult } from "@/test/fixtures";

const clip = { blob: new Blob(["audio"]), mimeType: "audio/webm", durationMs: 1800, filename: "turn.webm" };
const recorder = {
  state: "recording" as string,
  error: null,
  mimeType: "audio/webm",
  analyser: null,
  elapsedMs: 1800,
  start: jest.fn(),
  stop: jest.fn(async () => {
    recorder.state = "idle";
    return clip;
  }),
  cancel: jest.fn(),
  clearError: jest.fn(),
};

jest.mock("@/hooks/useRecorder", () => ({ useRecorder: () => recorder }));

jest.mock("@/lib/api", () => {
  const actual = jest.requireActual("@/lib/api");
  return { ...actual, postDrill: jest.fn() };
});

// eslint-disable-next-line @typescript-eslint/no-require-imports
const api = require("@/lib/api") as { postDrill: jest.Mock };

beforeEach(() => {
  jest.clearAllMocks();
  recorder.state = "recording";
});

async function release() {
  const user = userEvent.setup();
  const button = screen.getByRole("button", { name: /Recording/ });
  await user.pointer({ keys: "[MouseLeft>]", target: button });
  await user.pointer({ keys: "[/MouseLeft]", target: button });
}

test("the recording goes to this correction's drill and what was heard is shown", async () => {
  api.postDrill.mockResolvedValue(makeDrillResult());
  render(<DrillRecorder drill={makeDrill()} />);

  await release();

  await waitFor(() => expect(api.postDrill).toHaveBeenCalledWith(41, clip.blob, "turn.webm"));
  expect(await screen.findByText("What the recogniser heard")).toBeInTheDocument();
  expect(screen.getByTestId("verdict-41")).toHaveTextContent("Heard as corrected");
});

test("a recording that fails to send is kept and sent again as it was", async () => {
  api.postDrill
    .mockRejectedValueOnce(new ApiError("The speech recogniser is not responding.", 503))
    .mockResolvedValueOnce(makeDrillResult());
  render(<DrillRecorder drill={makeDrill()} />);

  await release();
  expect(await screen.findByText("The speech recogniser is not responding.")).toBeInTheDocument();

  await userEvent.setup().click(screen.getByRole("button", { name: "Send it again" }));

  await waitFor(() => expect(api.postDrill).toHaveBeenCalledTimes(2));
  expect(api.postDrill.mock.calls[1][1]).toBe(clip.blob);
  expect(await screen.findByText("What the recogniser heard")).toBeInTheDocument();
});
