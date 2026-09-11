/**
 * The drill's sentence, both ways round.
 *
 * One set of pieces renders as said and as to be said, so the assertions are that each
 * reads as a whole sentence, that the corrections are marked where they are, and that the
 * one being practised is told apart from others in the same sentence.
 */

import { render, screen } from "@testing-library/react";

import { DrillSentence } from "@/components/DrillSentence";
import { makeDrill } from "@/test/fixtures";

test("as said, the transcript's words are marked where the correction is", () => {
  const { container } = render(<DrillSentence drill={makeDrill()} as="said" />);

  expect(screen.getByTestId("drill-said")).toHaveTextContent(
    "Yesterday I complete the user story.",
  );
  expect(container.querySelector("mark")).toHaveTextContent(/^I complete$/);
});

test("as to be said, the correction is in the sentence", () => {
  const { container } = render(<DrillSentence drill={makeDrill()} as="say" />);

  expect(screen.getByTestId("drill-say")).toHaveTextContent(
    "Yesterday I completed the user story.",
  );
  expect(container.querySelector("strong")).toHaveTextContent(/^I completed$/);
  expect(container.querySelector("mark")).toBeNull();
});

test("the correction practised is drawn stronger than another in the same sentence", () => {
  const drill = makeDrill({
    pieces: [
      { said: "I complete", say: "I completed", correction_id: 41 },
      { said: " and she say", say: " and she said", correction_id: 42 },
    ],
  });
  const { container } = render(<DrillSentence drill={drill} as="say" />);

  const [practised, other] = Array.from(container.querySelectorAll("strong"));
  expect(practised).toHaveClass("decoration-primary");
  expect(other).toHaveClass("decoration-dotted");
});

test("a sentence cut short says so at the cut", () => {
  render(<DrillSentence drill={makeDrill({ cut_before: true, cut_after: true })} as="say" />);

  expect(screen.getByTestId("drill-say")).toHaveTextContent(
    "…Yesterday I completed the user story.…",
  );
});
