/**
 * The four marks, and the word the recogniser was unsure of.
 *
 * Asserted on the rendered text rather than on class names: what matters is that a reader
 * can see which words were said, which were not, and which were said instead — and that
 * every mark is named in the legend rather than left to be inferred from a colour.
 */

import { render, screen } from "@testing-library/react";

import { FidelityText } from "@/components/FidelityText";
import type { AlignedWord } from "@/lib/api";

const WORDS: AlignedWord[] = [
  { kind: "match", expected: "good", heard: "good", unsure: false },
  { kind: "substitution", expected: "morning", heard: "warning", unsure: false },
  { kind: "deletion", expected: "everyone", heard: null, unsure: false },
  { kind: "insertion", expected: null, heard: "so", unsure: false },
];

test("each kind of difference is on the page", () => {
  render(<FidelityText words={WORDS} />);

  const text = screen.getByTestId("fidelity-text").textContent ?? "";
  expect(text).toContain("good");
  expect(text).toContain("morning");
  expect(text).toContain("warning");
  expect(text).toContain("everyone");
  expect(text).toContain("so");
});

test("the legend names every mark, so no colour has to be guessed at", () => {
  render(<FidelityText words={WORDS} />);

  const legend = screen.getByLabelText("What the marks mean");
  expect(legend).toHaveTextContent("said as written");
  expect(legend).toHaveTextContent("not heard");
  expect(legend).toHaveTextContent("said differently");
  expect(legend).toHaveTextContent("not in the script");
  expect(legend).toHaveTextContent("an ending lost or gained");
  expect(legend).toHaveTextContent("a different word");
  expect(legend).toHaveTextContent("a number written as a figure");
});

test("what kind of difference a word is, is said in words and not only in colour", () => {
  render(
    <FidelityText
      words={[
        {
          kind: "substitution",
          expected: "calls",
          heard: "call",
          unsure: false,
          kind_of_difference: "ending",
        },
        {
          kind: "substitution",
          expected: "eleven",
          heard: "11",
          unsure: false,
          kind_of_difference: "figure",
        },
      ]}
    />,
  );

  expect(screen.getByTitle("The same word with a different ending.")).toHaveTextContent("call");
  expect(
    screen.getByTitle("The same number, written as a figure. Not counted as a difference."),
  ).toHaveTextContent("11");
});

test("a take from before differences were sorted still reads as said differently", () => {
  render(
    <FidelityText
      words={[{ kind: "substitution", expected: "calls", heard: "call", unsure: false }]}
    />,
  );

  expect(screen.getByTitle("Said differently.")).toHaveTextContent("call");
});

test("a word the recogniser doubted says so rather than being dropped", () => {
  render(
    <FidelityText
      words={[{ kind: "match", expected: "deposit", heard: "deposit", unsure: true }]}
    />,
  );

  expect(screen.getByTitle("The recogniser was not sure it heard this word.")).toHaveTextContent(
    "deposit",
  );
});
