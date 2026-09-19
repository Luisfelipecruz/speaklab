/**
 * Pasting a script: the split shown before anything is saved, a boundary moved, and what
 * is sent when it is saved.
 *
 * The one assertion that matters most is the last: what is saved is the split on screen,
 * not the split the server first suggested. A page that showed one thing and saved another
 * would be rehearsing a talk cut somewhere nobody chose.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { NewPresentation } from "@/app/(app)/rehearse/new/NewPresentation";

const push = jest.fn();
jest.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh: jest.fn() }) }));

jest.mock("@/lib/api", () => {
  const actual = jest.requireActual("@/lib/api");
  return { ...actual, previewPresentation: jest.fn(), createPresentation: jest.fn() };
});

// eslint-disable-next-line @typescript-eslint/no-require-imports
const api = require("@/lib/api") as {
  previewPresentation: jest.Mock;
  createPresentation: jest.Mock;
};

const SPLIT = {
  sections: ["Good morning everyone.", "We shipped it in 2026."],
  word_counts: [3, 5],
  unscorable: [[], ["2026"]],
  pron: "ok",
};

beforeEach(() => jest.clearAllMocks());

async function paste(text = "Good morning everyone.\n\nWe shipped it in 2026.") {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("What is the talk called?"), "A talk");
  await user.click(screen.getByLabelText("The script"));
  await user.paste(text);
  await user.click(screen.getByRole("button", { name: "See the split" }));
  return user;
}

test("the split is shown with a word count per section before anything is saved", async () => {
  api.previewPresentation.mockResolvedValue(SPLIT);
  render(<NewPresentation />);

  await paste();

  expect(await screen.findByRole("heading", { name: "2 sections" })).toBeInTheDocument();
  expect(screen.getByText("Section 1 · 3 words")).toBeInTheDocument();
  expect(api.createPresentation).not.toHaveBeenCalled();
});

test("the words that cannot be scored are named under the section they are in", async () => {
  api.previewPresentation.mockResolvedValue(SPLIT);
  render(<NewPresentation />);

  await paste();

  expect(await screen.findByText("2026")).toBeInTheDocument();
  expect(screen.getByText(/write them the way you say them/)).toBeInTheDocument();
});

test("a section joined to the one above it is saved joined, with both sets of words", async () => {
  api.previewPresentation.mockResolvedValue(SPLIT);
  api.createPresentation.mockResolvedValue({ id: 11 });
  render(<NewPresentation />);

  const user = await paste();
  await user.click(
    await screen.findByRole("button", { name: "Join section 2 to the one before it" }),
  );

  expect(screen.getByRole("heading", { name: "One section" })).toBeInTheDocument();
  expect(screen.getByText("2026")).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "Save the script" }));

  await waitFor(() =>
    expect(api.createPresentation).toHaveBeenCalledWith({
      title: "A talk",
      script: "Good morning everyone.\n\nWe shipped it in 2026.",
      sections: ["Good morning everyone. We shipped it in 2026."],
    }),
  );
  expect(push).toHaveBeenCalledWith("/rehearse/11");
});

test("a scorer that is not running is said, rather than every word looking fine", async () => {
  api.previewPresentation.mockResolvedValue({ ...SPLIT, unscorable: [[], []], pron: "unavailable" });
  render(<NewPresentation />);

  await paste();

  expect(
    await screen.findByText(/which words can be scored sound by sound has not been checked/),
  ).toBeInTheDocument();
});
