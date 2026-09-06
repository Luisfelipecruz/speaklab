/**
 * The small table primitive, and the accessibility it exists to keep.
 *
 * It is four columns of markup, so the temptation is to leave it untested. The reason not
 * to is that its whole justification is the part a rewrite loses first: a real `<caption>`
 * and real `<th scope="col">` rather than styled divs. A grid of divs looks identical and
 * is unreadable to anybody not looking at it, and nothing on screen would say so.
 */

import { render, screen } from "@testing-library/react";

import { Table } from "@/components/PhonemeTable.helpers";

test("it is a table, with a caption and column headers a screen reader can use", () => {
  render(
    <Table
      caption="Sounds that scored worst"
      head={["Sound", "Heard instead", "Times"]}
      rows={[
        ["θ", "s", "34"],
        ["ð", "d", "11"],
      ]}
    />,
  );

  const table = screen.getByRole("table", { name: "Sounds that scored worst" });
  expect(table).toBeInTheDocument();

  const headers = screen.getAllByRole("columnheader");
  expect(headers.map((cell) => cell.textContent)).toEqual([
    "Sound",
    "Heard instead",
    "Times",
  ]);
  for (const header of headers) expect(header).toHaveAttribute("scope", "col");
});

test("every row lands in the body, in the order it was given", () => {
  render(
    <Table
      caption="Two readings"
      head={["Sound", "Score"]}
      rows={[
        ["θ", "-9.1"],
        ["s", "-0.4"],
      ]}
    />,
  );

  const rows = screen.getAllByRole("row");
  // The header row plus the two data rows.
  expect(rows).toHaveLength(3);
  expect(screen.getAllByRole("cell").map((cell) => cell.textContent)).toEqual([
    "θ",
    "-9.1",
    "s",
    "-0.4",
  ]);
});

test("no rows still renders a table with its headings", () => {
  // The caller decides what an empty result says; the table's job is not to disappear and
  // take the column names with it.
  render(<Table caption="Nothing scored yet" head={["Sound", "Score"]} rows={[]} />);

  expect(screen.getByRole("table", { name: "Nothing scored yet" })).toBeInTheDocument();
  expect(screen.getAllByRole("columnheader")).toHaveLength(2);
  expect(screen.queryAllByRole("cell")).toHaveLength(0);
});

test("a cell can hold markup, not only text", () => {
  // The phoneme tables put badges and scores in their cells, not strings.
  render(
    <Table
      caption="With a control in a cell"
      head={["Sound", ""]}
      rows={[["θ", <button key="play">Play the segment</button>]]}
    />,
  );

  const cell = screen.getByRole("button", { name: "Play the segment" }).closest("td");
  expect(cell).toBeInTheDocument();
});
