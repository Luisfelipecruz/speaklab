/**
 * The writing lines on the progress page: the totals they rest on, drawn as a family is,
 * with how they are counted beside them.
 */

import { render, screen } from "@testing-library/react";

import { asFamily, WritingPanel } from "@/components/WritingPanel";
import { familyStatus } from "@/app/(app)/progress/summary";
import { makeWriting } from "@/test/fixtures";

test("the totals, the lines and how they are counted are all on the panel", () => {
  render(<WritingPanel writing={makeWriting()} />);

  // The tile's label; the chart below carries the same words as its title.
  expect(screen.getAllByText("asked for English")[0]!.previousSibling).toHaveTextContent("9");
  expect(screen.getByText("counted mistakes").previousSibling).toHaveTextContent("6");
  expect(screen.getByText("Writing on your own")).toBeInTheDocument();
  expect(screen.getByTestId("caveat")).toHaveTextContent("one release of fn");
});

test("the overview's line for writing is counted the way every family's is", () => {
  expect(familyStatus(asFamily(makeWriting()))).toBe("2 measurements across 3 weeks, 2 with a direction");
});
