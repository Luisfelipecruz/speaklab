/**
 * The Notebook's own way in: a typed text or a recording goes to the panel's endpoint
 * with the switch and the saving choice the person made, and what comes back is shown.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { WriteInEnglish } from "@/components/WriteInEnglish";
import { ApiError } from "@/lib/api";
import { makeCapture } from "@/test/fixtures";

const refresh = jest.fn();
jest.mock("next/navigation", () => ({ useRouter: () => ({ push: jest.fn(), refresh }) }));

const clip = { blob: new Blob(["audio"]), mimeType: "audio/webm", durationMs: 4200, filename: "turn.webm" };
const recorder = {
  state: "idle" as string,
  error: null,
  mimeType: "audio/webm",
  analyser: null,
  elapsedMs: 0,
  start: jest.fn(async () => {
    recorder.state = "recording";
  }),
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
  return { ...actual, postCapture: jest.fn() };
});

// eslint-disable-next-line @typescript-eslint/no-require-imports
const api = require("@/lib/api") as { postCapture: jest.Mock };

beforeEach(() => {
  jest.clearAllMocks();
  recorder.state = "idle";
});

async function type(text: string) {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Write it in English, or check your English"), text);
  return user;
}

test("a typed text is sent to be decided, kept, and its English shown", async () => {
  api.postCapture.mockResolvedValue(makeCapture({ via: "typed" }));
  render(<WriteInEnglish />);

  const user = await type("Laura, te escribo");
  await user.click(screen.getByRole("button", { name: "Get the English" }));

  await waitFor(() => expect(screen.getByTestId("english-organized")).toBeInTheDocument());
  expect(api.postCapture).toHaveBeenCalledWith({ text: "Laura, te escribo", via: "typed", mode: "auto", save: true });
  expect(refresh).toHaveBeenCalled();
});

test("the switch and the saving choice go with the text", async () => {
  api.postCapture.mockResolvedValue(makeCapture({ id: null, saved: false }));
  render(<WriteInEnglish />);

  const user = await type("I recieved it");
  await user.click(screen.getByLabelText("It is English: check it"));
  await user.click(screen.getByLabelText("Keep it in the Notebook"));
  await user.click(screen.getByRole("button", { name: "Get the English" }));

  await waitFor(() => expect(api.postCapture).toHaveBeenCalled());
  expect(api.postCapture).toHaveBeenCalledWith({ text: "I recieved it", via: "typed", mode: "check", save: false });
  expect(refresh).not.toHaveBeenCalled();
});

test("nothing typed sends nothing", () => {
  render(<WriteInEnglish />);

  expect(screen.getByRole("button", { name: "Get the English" })).toBeDisabled();
});

test("a recording is sent as audio when the button is released", async () => {
  api.postCapture.mockResolvedValue(makeCapture());
  recorder.state = "recording";
  const user = userEvent.setup();
  render(<WriteInEnglish />);

  const button = screen.getByRole("button", { name: /Recording/ });
  await user.pointer({ keys: "[MouseLeft>]", target: button });
  await user.pointer({ keys: "[/MouseLeft]", target: button });

  await waitFor(() => expect(api.postCapture).toHaveBeenCalled());
  expect(api.postCapture.mock.calls[0][0].audio).toEqual({ blob: clip.blob, filename: "turn.webm" });
});

test("a failure is said in the API's words", async () => {
  api.postCapture.mockRejectedValue(new ApiError("The recogniser for your own language is not answering. Nothing was saved.", 503));
  render(<WriteInEnglish />);

  const user = await type("hola");
  await user.click(screen.getByRole("button", { name: "Get the English" }));

  expect(await screen.findByText(/Nothing was saved/)).toBeInTheDocument();
});
