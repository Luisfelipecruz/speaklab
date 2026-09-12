import { render, screen } from "@testing-library/react";

import { NotFoundPanel } from "@/components/NotFoundPanel";

test("an address that leads nowhere says so and offers a way back", () => {
  render(<NotFoundPanel />);

  expect(screen.getByRole("heading", { name: "Nothing here" })).toBeVisible();
  expect(screen.getByRole("link", { name: "Go to your practice" })).toHaveAttribute(
    "href",
    "/home",
  );
  expect(screen.getByRole("link", { name: "Choose a scenario" })).toHaveAttribute(
    "href",
    "/scenarios",
  );
});
