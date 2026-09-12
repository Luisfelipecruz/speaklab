import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ErrorPanel } from "@/components/ErrorPanel";

const refresh = jest.fn();

jest.mock("next/navigation", () => ({
  useRouter: () => ({ refresh }),
}));

beforeEach(() => refresh.mockClear());

function failure(message: string, digest?: string): Error & { digest?: string } {
  return Object.assign(new Error(message), digest ? { digest } : {});
}

test("a failure the server withheld is named by its reference", () => {
  render(<ErrorPanel error={failure("hidden", "2481357690")} reset={jest.fn()} />);

  expect(screen.getByRole("heading", { name: "This page could not be shown" })).toBeVisible();
  expect(screen.getByText("2481357690")).toBeVisible();
  expect(screen.queryByText("hidden")).not.toBeInTheDocument();
});

test("a failure in the browser says what it was", () => {
  render(<ErrorPanel error={failure("Cannot read the chart")} reset={jest.fn()} />);

  expect(screen.getByText("Cannot read the chart")).toBeVisible();
});

test("trying again asks the server again, then resets the page", async () => {
  const reset = jest.fn();
  render(<ErrorPanel error={failure("boom")} reset={reset} />);

  await userEvent.click(screen.getByRole("button", { name: "Try again" }));

  expect(refresh).toHaveBeenCalledTimes(1);
  expect(reset).toHaveBeenCalledTimes(1);
});

test("the services page is one click away", () => {
  render(<ErrorPanel error={failure("boom")} reset={jest.fn()} />);

  expect(screen.getByRole("link", { name: "Check the services" })).toHaveAttribute(
    "href",
    "/status",
  );
});
