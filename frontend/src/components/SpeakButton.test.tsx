/**
 * The button that plays one word.
 *
 * Two of these tests are about wording rather than behaviour, and they are the ones most
 * worth keeping. The button must say it plays a word and must not say the word is being
 * said correctly: one is a description of a file, the other is a claim about English
 * that nothing in this system has measured.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { SpeakButton } from "@/components/SpeakButton";

jest.mock("@/lib/api", () => {
  const actual = jest.requireActual("@/lib/api");
  return { ...actual, speakWord: jest.fn() };
});

// eslint-disable-next-line @typescript-eslint/no-require-imports
const api = require("@/lib/api") as {
  speakWord: jest.Mock;
  ApiError: new (message: string, status: number) => Error;
};

const play = jest.fn().mockResolvedValue(undefined);

beforeEach(() => {
  api.speakWord.mockReset();
  play.mockClear();
  global.URL.createObjectURL = jest.fn(() => "blob:word");
  global.URL.revokeObjectURL = jest.fn();
  // jsdom has no media stack at all: HTMLMediaElement.play is not implemented, and left
  // alone it throws rather than resolving.
  window.HTMLMediaElement.prototype.play = play;
});

function speaks(blob = new Blob(["riff"], { type: "audio/wav" })) {
  api.speakWord.mockResolvedValue(blob);
  return api.speakWord;
}

test("the button says which word it plays", () => {
  speaks();
  render(<SpeakButton word="is" />);

  expect(screen.getByRole("button", { name: 'Hear "is"' })).toBeInTheDocument();
});

test("it never claims the recording is how the word should be said", () => {
  speaks();
  render(<SpeakButton word="is" />);

  const button = screen.getByRole("button");
  const wording = `${button.getAttribute("aria-label")} ${button.getAttribute("title")}`;

  for (const claim of ["correct", "proper", "right way", "should", "model"]) {
    expect(wording.toLowerCase()).not.toContain(claim);
  }
});

test("pressing it asks for that word and plays what comes back", async () => {
  const spoken = speaks();
  render(<SpeakButton word="calls" />);

  await userEvent.click(screen.getByRole("button"));

  await waitFor(() => expect(play).toHaveBeenCalled());
  expect(spoken).toHaveBeenCalledWith("calls");
});

test("a second press does not fetch the word twice", async () => {
  const spoken = speaks();
  render(<SpeakButton word="see" />);

  const button = screen.getByRole("button");
  await userEvent.click(button);
  await waitFor(() => expect(play).toHaveBeenCalledTimes(1));
  await userEvent.click(button);
  await waitFor(() => expect(play).toHaveBeenCalledTimes(2));

  expect(spoken).toHaveBeenCalledTimes(1);
});

test("a word that cannot be played costs the reader that word and not the screen", async () => {
  api.speakWord.mockRejectedValue(new api.ApiError("no", 404));
  render(<SpeakButton word="peregrine" />);

  await userEvent.click(screen.getByRole("button"));

  await waitFor(() =>
    expect(screen.getByRole("button")).toHaveAttribute(
      "title",
      '"peregrine" could not be played',
    ),
  );
  expect(screen.getByRole("button")).toBeInTheDocument();
});
