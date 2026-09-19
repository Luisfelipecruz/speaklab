/**
 * The words that came out differently, grouped by what kind of difference each is.
 *
 * The fixture is the speaker's own first section: six words that differed, of three
 * different kinds. What is tested is that the three are counted apart, that the number
 * the recogniser wrote as a digit is kept out of the count and says so, and that a take
 * with nothing to group shows nothing rather than three empty boxes.
 */

import { render, screen } from "@testing-library/react";

import { DifferenceGroups } from "@/components/DifferenceGroups";
import type { AlignedWord } from "@/lib/api";

function said(
  expected: string,
  heard: string,
  kind_of_difference: AlignedWord["kind_of_difference"],
): AlignedWord {
  return { kind: "substitution", expected, heard, unsure: false, kind_of_difference };
}

const FIRST_SECTION: AlignedWord[] = [
  { kind: "match", expected: "the", heard: "the", unsure: false },
  said("calls", "call", "ending"),
  said("pile", "peels", "different-word"),
  said("up", "out", "different-word"),
  said("cost", "caused", "different-word"),
  said("eleven", "11", "figure"),
  { kind: "insertion", expected: null, heard: "check", unsure: false },
];

test("the kinds are counted apart instead of as one number", () => {
  render(<DifferenceGroups words={FIRST_SECTION} />);

  expect(screen.getByText("4 words came out differently — 1 ending and 3 other words.")).toBeInTheDocument();
  expect(screen.getByText("Endings · 1")).toBeInTheDocument();
  expect(screen.getByText("Other words · 3")).toBeInTheDocument();
});

test("a number the recogniser wrote as a figure is shown apart and said not to count", () => {
  render(<DifferenceGroups words={FIRST_SECTION} />);

  expect(screen.getByText("Numbers written as figures · 1")).toBeInTheDocument();
  expect(screen.getByText(/Not counted against you/)).toBeInTheDocument();
  expect(screen.getByText("eleven")).toBeInTheDocument();
  expect(screen.getByText("11")).toBeInTheDocument();
});

test("every pair is listed under its own group, both words of it", () => {
  render(<DifferenceGroups words={FIRST_SECTION} />);

  expect(screen.getByText("calls")).toBeInTheDocument();
  expect(screen.getByText("call")).toBeInTheDocument();
  expect(screen.getByText("peels")).toBeInTheDocument();
});

test("a group with nothing in it is not drawn", () => {
  render(<DifferenceGroups words={[said("calls", "call", "ending")]} />);

  expect(screen.getByText("Endings · 1")).toBeInTheDocument();
  expect(screen.queryByText(/Other words/)).not.toBeInTheDocument();
  expect(screen.queryByText(/Numbers written as figures/)).not.toBeInTheDocument();
});

test("a take said exactly as written shows nothing at all", () => {
  const { container } = render(
    <DifferenceGroups
      words={[{ kind: "match", expected: "the", heard: "the", unsure: false }]}
    />,
  );

  expect(container).toBeEmptyDOMElement();
});

test("a take from before differences were sorted is not grouped as anything", () => {
  const { container } = render(
    <DifferenceGroups
      words={[{ kind: "substitution", expected: "calls", heard: "call", unsure: false }]}
    />,
  );

  expect(container).toBeEmptyDOMElement();
});

test("one of a kind is named in the singular", () => {
  render(<DifferenceGroups words={[said("calls", "call", "ending"), said("up", "out", "different-word")]} />);

  expect(
    screen.getByText("2 words came out differently — 1 ending and 1 other word."),
  ).toBeInTheDocument();
});
