/**
 * Deleting takes a second click that says what it does, and the page is read again from
 * the API afterwards.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { DeleteAllCaptures, DeleteCaptureButton } from "@/components/DeleteCaptureButton";
import { ApiError } from "@/lib/api";

const push = jest.fn();
const refresh = jest.fn();
jest.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh }) }));

jest.mock("@/lib/api", () => {
  const actual = jest.requireActual("@/lib/api");
  return { ...actual, deleteCapture: jest.fn(), deleteAllCaptures: jest.fn() };
});

// eslint-disable-next-line @typescript-eslint/no-require-imports
const api = require("@/lib/api") as { deleteCapture: jest.Mock; deleteAllCaptures: jest.Mock };

beforeEach(() => jest.clearAllMocks());

test("one click arms it, the second deletes and the list is read again", async () => {
  api.deleteCapture.mockResolvedValue(undefined);
  const user = userEvent.setup();
  render(<DeleteCaptureButton id={12} />);

  await user.click(screen.getByRole("button", { name: "Delete capture 12" }));
  expect(api.deleteCapture).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "Confirm deleting capture 12" }));

  await waitFor(() => expect(refresh).toHaveBeenCalled());
  expect(api.deleteCapture).toHaveBeenCalledWith(12);
});

test("deleted from its own page, it goes back to the Notebook", async () => {
  api.deleteCapture.mockResolvedValue(undefined);
  const user = userEvent.setup();
  render(<DeleteCaptureButton id={12} back />);

  await user.click(screen.getByRole("button", { name: "Delete capture 12" }));
  await user.click(screen.getByRole("button", { name: "Confirm deleting capture 12" }));

  await waitFor(() => expect(push).toHaveBeenCalledWith("/notebook"));
});

test("a failed delete says so and disarms", async () => {
  api.deleteCapture.mockRejectedValue(new ApiError("No capture with id 12", 404));
  const user = userEvent.setup();
  render(<DeleteCaptureButton id={12} />);

  await user.click(screen.getByRole("button", { name: "Delete capture 12" }));
  await user.click(screen.getByRole("button", { name: "Confirm deleting capture 12" }));

  expect(await screen.findByText("No capture with id 12")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Delete capture 12" })).toBeInTheDocument();
});

test("deleting every capture names how many, and is offered only when there are some", async () => {
  api.deleteAllCaptures.mockResolvedValue({ deleted: 3 });
  const user = userEvent.setup();
  const { rerender } = render(<DeleteAllCaptures count={3} />);

  await user.click(screen.getByRole("button", { name: /Delete every capture/ }));
  await user.click(screen.getByRole("button", { name: "Really delete all 3" }));
  await waitFor(() => expect(api.deleteAllCaptures).toHaveBeenCalled());

  rerender(<DeleteAllCaptures count={0} />);
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
});
