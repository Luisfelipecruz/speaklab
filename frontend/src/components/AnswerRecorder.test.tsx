/**
 * Answer, see it counted, say it again and see the two side by side.
 *
 * The microphone is replaced, as for the drill: no test environment has one. What is
 * tested is the round trip to this prompt, the second answer sent as saying the first
 * again, the time limit stopping the recording by itself, and a failed send kept and sent
 * again as it was.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { AnswerRecorder } from "@/components/AnswerRecorder";
import { ApiError } from "@/lib/api";
import { makeAnswer, makePrompt } from "@/test/fixtures";

const clip = { blob: new Blob(["audio"]), mimeType: "audio/webm", durationMs: 30_000, filename: "turn.webm" };
const recorder = {
  state: "recording" as string,
  error: null,
  mimeType: "audio/webm",
  analyser: null,
  elapsedMs: 30_000,
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
  return { ...actual, postAnswer: jest.fn() };
});

// eslint-disable-next-line @typescript-eslint/no-require-imports
const api = require("@/lib/api") as { postAnswer: jest.Mock };

beforeEach(() => {
  jest.clearAllMocks();
  recorder.state = "recording";
  recorder.elapsedMs = 30_000;
});

test("a stopped recording goes to this prompt and the answer is shown counted", async () => {
  api.postAnswer.mockResolvedValue(makeAnswer());
  render(<AnswerRecorder prompt={makePrompt()} />);

  expect(screen.getByRole("button", { name: /Stop — 1:00 left/ })).toBeInTheDocument();
  await userEvent.setup().click(screen.getByRole("button", { name: /Stop/ }));

  await waitFor(() =>
    expect(api.postAnswer).toHaveBeenCalledWith("explain-a-failed-release", clip.blob, "turn.webm", null),
  );
  expect(await screen.findByRole("heading", { name: "Your answer" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Say it again, tighter" })).toBeInTheDocument();
});

test("saying it again sends the second as the first said again, and shows both", async () => {
  const first = makeAnswer();
  const second = makeAnswer({ id: 8, again_of: 7, delivery: { ...first.delivery, words: 12 } });
  api.postAnswer.mockResolvedValueOnce(first).mockResolvedValueOnce(second);
  const user = userEvent.setup();
  render(<AnswerRecorder prompt={makePrompt()} />);

  await user.click(screen.getByRole("button", { name: /Stop/ }));
  await screen.findByRole("heading", { name: "Your answer" });

  recorder.state = "recording";
  await user.click(screen.getByRole("button", { name: "Say it again, tighter" }));
  expect(screen.getByTestId("saying-again")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: /Stop/ }));

  await waitFor(() => expect(api.postAnswer).toHaveBeenLastCalledWith(
    "explain-a-failed-release",
    clip.blob,
    "turn.webm",
    7,
  ));
  expect(await screen.findByRole("heading", { name: "The two side by side" })).toBeInTheDocument();
  expect(screen.getByRole("row", { name: /^words 18 12$/ })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Said again" })).toBeInTheDocument();
});

test("an earlier answer opened to be said again is the one the new answer says again", async () => {
  api.postAnswer.mockResolvedValue(makeAnswer({ id: 9, again_of: 4 }));
  render(<AnswerRecorder prompt={makePrompt()} basis={makeAnswer({ id: 4 })} />);

  expect(screen.getByTestId("saying-again")).toBeInTheDocument();
  await userEvent.setup().click(screen.getByRole("button", { name: /Stop/ }));

  await waitFor(() => expect(api.postAnswer.mock.calls[0][3]).toBe(4));
  expect(await screen.findByRole("heading", { name: "The two side by side" })).toBeInTheDocument();
});

test("the time limit stops the recording by itself", async () => {
  recorder.elapsedMs = 90_000;
  api.postAnswer.mockResolvedValue(makeAnswer());

  render(<AnswerRecorder prompt={makePrompt({ time_limit_s: 90 })} />);

  await waitFor(() => expect(recorder.stop).toHaveBeenCalledTimes(1));
  await waitFor(() => expect(api.postAnswer).toHaveBeenCalledTimes(1));
});

test("an idle recorder offers to start, and starting asks for the microphone", async () => {
  recorder.state = "idle";
  recorder.elapsedMs = 0;
  render(<AnswerRecorder prompt={makePrompt()} />);

  await userEvent.setup().click(screen.getByRole("button", { name: "Start answering" }));

  expect(recorder.start).toHaveBeenCalledTimes(1);
  expect(screen.getByText(/It stops by itself after 1:30/)).toBeInTheDocument();
});

test("a recording that fails to send is kept and sent again as it was", async () => {
  api.postAnswer
    .mockRejectedValueOnce(new ApiError("The speech recogniser is not responding.", 503))
    .mockResolvedValueOnce(makeAnswer());
  const user = userEvent.setup();
  render(<AnswerRecorder prompt={makePrompt()} />);

  await user.click(screen.getByRole("button", { name: /Stop/ }));
  expect(await screen.findByText("The speech recogniser is not responding.")).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "Send it again" }));

  await waitFor(() => expect(api.postAnswer).toHaveBeenCalledTimes(2));
  expect(api.postAnswer.mock.calls[1][1]).toBe(clip.blob);
  expect(await screen.findByRole("heading", { name: "Your answer" })).toBeInTheDocument();
});
