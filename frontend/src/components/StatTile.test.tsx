import { render, screen } from "@testing-library/react";

import { StatTile } from "@/components/StatTile";

test("the figure and its label are both on the tile", () => {
  render(<StatTile label="scored readings" value={7} />);

  expect(screen.getByText("7")).toBeInTheDocument();
  expect(screen.getByText("scored readings")).toBeInTheDocument();
});

test("a figure that is already formatted is shown as given", () => {
  render(<StatTile label="words" value="1,204" />);

  expect(screen.getByText("1,204")).toBeInTheDocument();
});

test("the figure is set larger than its label", () => {
  render(<StatTile label="conversations" value={3} />);

  const figure = screen.getByText("3");
  const label = screen.getByText("conversations");
  expect(figure.className).toMatch(/text-3xl/);
  expect(label.className).toMatch(/text-xs/);
});
