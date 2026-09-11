/**
 * What the recogniser heard, shown as evidence rather than as a mark.
 *
 * The one assertion that matters most is the absence of a grade: no percentage and no
 * pass. The rest is that each outcome says what was heard in the correction's place, and
 * that the sentence is laid out word by word so a difference can be found.
 */

import { render, screen } from "@testing-library/react";

import { DrillResultView, wordCounts } from "@/components/DrillResultView";
import { makeDrill, makeDrillResult } from "@/test/fixtures";

test("the corrected words heard in their place are named as that, and nothing is graded", () => {
  render(<DrillResultView drill={makeDrill()} result={makeDrillResult()} />);

  expect(screen.getByTestId("verdict-41")).toHaveTextContent(
    "Heard as corrected: “i completed”.",
  );
  expect(screen.getByText("Yesterday I completed the user story.")).toBeInTheDocument();
  expect(screen.getByText("6 of 6 words heard as written.")).toBeInTheDocument();
  expect(screen.queryByText(/%|pass|score/i)).not.toBeInTheDocument();
});

test("the words as first said are named, with the correction beside them", () => {
  const result = makeDrillResult({
    heard: "Yesterday I complete the user story.",
    verdicts: [
      { id: 41, verdict: "original", expected: "i completed", heard: "i complete", unsure: false },
    ],
    words: [
      { expected: "yesterday", heard: "yesterday" },
      { expected: "i", heard: "i" },
      { expected: "completed", heard: "complete" },
    ],
    expected_words: 3,
    matched: 2,
    substituted: 1,
  });

  render(<DrillResultView drill={makeDrill()} result={result} />);

  expect(screen.getByTestId("verdict-41")).toHaveTextContent(
    "Heard the way you first said it: “i complete” — the correction is “i completed”.",
  );
  expect(screen.getByLabelText("Word by word")).toHaveTextContent(
    "expected completed , heard complete",
  );
  expect(screen.getByText("2 of 3 words heard as written, 1 heard as something else.")).toBeInTheDocument();
});

test("a word the recogniser was unsure of is said to be a possible mishearing", () => {
  const result = makeDrillResult({
    verdicts: [
      { id: 41, verdict: "other", expected: "i completed", heard: "i competed", unsure: true },
    ],
  });

  render(<DrillResultView drill={makeDrill()} result={result} />);

  expect(screen.getByTestId("verdict-41")).toHaveTextContent("Heard something else there");
  expect(screen.getByText(/may be a mishearing/)).toBeInTheDocument();
});

test("nothing heard where the correction belongs", () => {
  const result = makeDrillResult({
    verdicts: [{ id: 41, verdict: "unheard", expected: "i completed", heard: "", unsure: false }],
  });

  render(<DrillResultView drill={makeDrill()} result={result} />);

  expect(screen.getByTestId("verdict-41")).toHaveTextContent(
    "Nothing was heard where it belongs — the correction is “i completed”.",
  );
});

test("with several corrections in the sentence, each outcome names its correction", () => {
  const drill = makeDrill({
    corrections: [
      ...makeDrill().corrections,
      { ...makeDrill().corrections[0], id: 42, original: "she say", correction: "she said" },
    ],
  });
  const result = makeDrillResult({
    verdicts: [
      { id: 41, verdict: "corrected", expected: "i completed", heard: "i completed", unsure: false },
      { id: 42, verdict: "original", expected: "she said", heard: "she say", unsure: false },
    ],
  });

  render(<DrillResultView drill={drill} result={result} />);

  expect(screen.getByTestId("verdict-42")).toHaveTextContent("she say → she said");
});

test("the counts name every kind of difference", () => {
  expect(
    wordCounts(makeDrillResult({ expected_words: 8, matched: 5, substituted: 1, missed: 2, added: 1 })),
  ).toBe(
    "5 of 8 words heard as written, 1 heard as something else, 2 not heard, 1 heard that is not in the sentence.",
  );
});
