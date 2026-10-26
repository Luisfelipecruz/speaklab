/**
 * Writing it yourself: the attempt goes to this capture, the check comes back marked in
 * the person's words with the closer version beside it, and the schedule is said.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { AttemptResult } from "@/components/AttemptResult";
import { WriteItYourself } from "@/components/WriteItYourself";
import { ApiError } from "@/lib/api";
import { makeCaptureAttempt } from "@/test/fixtures";

const refresh = jest.fn();
jest.mock("next/navigation", () => ({ useRouter: () => ({ push: jest.fn(), refresh }) }));

jest.mock("@/lib/api", () => {
  const actual = jest.requireActual("@/lib/api");
  return { ...actual, postCaptureAttempt: jest.fn() };
});

// eslint-disable-next-line @typescript-eslint/no-require-imports
const api = require("@/lib/api") as { postCaptureAttempt: jest.Mock };

beforeEach(() => jest.clearAllMocks());

test("the attempt is checked against this capture and the result is shown", async () => {
  api.postCaptureAttempt.mockResolvedValue(makeCaptureAttempt());
  const user = userEvent.setup();
  render(<WriteItYourself captureId={12} zone="UTC" />);

  await user.type(screen.getByLabelText("Write it in English, your way"), "Laura, the report");
  await user.click(screen.getByRole("button", { name: "Check" }));

  await waitFor(() => expect(screen.getByTestId("attempt-count")).toBeInTheDocument());
  expect(api.postCaptureAttempt).toHaveBeenCalledWith(12, "Laura, the report");
  expect(screen.getByRole("button", { name: "Check again" })).toBeInTheDocument();
  expect(refresh).toHaveBeenCalled();
});

test("a check that fails says why and keeps what was written", async () => {
  api.postCaptureAttempt.mockRejectedValue(new ApiError("Nothing was written.", 422));
  const user = userEvent.setup();
  render(<WriteItYourself captureId={12} />);

  await user.type(screen.getByLabelText("Write it in English, your way"), "...");
  await user.click(screen.getByRole("button", { name: "Check" }));

  expect(await screen.findByText("Nothing was written.")).toBeInTheDocument();
  expect(screen.getByLabelText("Write it in English, your way")).toHaveValue("...");
});

test("a result names the counted mistakes, the forms, the closer version and the schedule", () => {
  render(<AttemptResult attempt={makeCaptureAttempt()} zone="UTC" />);

  expect(screen.getByTestId("attempt-count")).toHaveTextContent("1 counted mistake in 10 words: 10 per 100 words.");
  expect(screen.getByRole("list", { name: "Forms you used" })).toHaveTextContent("future will");
  expect(screen.getByText(/Beside the closer version · Organized/)).toBeInTheDocument();
  expect(screen.getByTestId("word-diff")).toHaveTextContent("untill");
  expect(screen.getByTestId("comes-back")).toHaveTextContent("A counted mistake sends it back to box 1, so it comes back");
});

test("an attempt with no counted mistake moves up a box, and the last box holds", () => {
  const { rerender } = render(
    <AttemptResult attempt={makeCaptureAttempt({ errors: [], counted: 0, per_100_words: 0, box_before: 1, box: 2 })} />,
  );
  expect(screen.getByTestId("attempt-count")).toHaveTextContent("No counted mistake in 10 words.");
  expect(screen.getByTestId("comes-back")).toHaveTextContent("Up a box, to box 2, so it comes back");

  rerender(<AttemptResult attempt={makeCaptureAttempt({ errors: [], counted: 0, box_before: 5, box: 5 })} />);
  expect(screen.getByTestId("comes-back")).toHaveTextContent("Still in the last box, box 5, so it comes back");
});
