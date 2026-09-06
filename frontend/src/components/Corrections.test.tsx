/**
 * The marks and the rows that explain them.
 *
 * What matters is that a mark lands on the quoted words and nowhere else, and that a
 * correction the system does not trust looks different and says why.
 */

import { render, screen, within } from "@testing-library/react";

import { CorrectionList, MarkedText } from "@/components/Corrections";
import { markTranscript } from "@/lib/corrections";
import type { LanguageErrorItem } from "@/lib/api";
import { makeAnalysis } from "@/test/fixtures";

const TRANSCRIPT = "Yesterday I complete the user story and then I look department twice.";

/** The fixture's corrections, with offsets that hold their words in this transcript. */
const ITEMS: LanguageErrorItem[] = makeAnalysis().errors.items.map((item) => {
  const span_start = TRANSCRIPT.indexOf(item.original);
  return { ...item, turn_id: 6, span_start, span_end: span_start + item.original.length };
});

test("a mark covers the quoted words and carries its number for a screen reader", () => {
  const marked = markTranscript(TRANSCRIPT, [ITEMS[0]]);
  const { container } = render(<MarkedText marked={marked} />);

  const marks = container.querySelectorAll("mark");
  expect(marks).toHaveLength(1);
  expect(marks[0]).toHaveTextContent(/^I complete the user story\s*1/);
  expect(within(marks[0]).getByText(/correction 1/)).toHaveClass("sr-only");
  // The rest of the sentence is still there, unmarked.
  expect(container).toHaveTextContent("and then I look department twice.");
});

test("a doubtful correction is drawn differently and its row says why", () => {
  const marked = markTranscript(TRANSCRIPT, [ITEMS[0], ITEMS[1]]);
  const { container } = render(
    <>
      <MarkedText marked={marked} />
      <CorrectionList corrections={marked.corrections} />
    </>,
  );

  const [trusted, doubtful] = Array.from(container.querySelectorAll("mark"));
  expect(trusted.className).not.toContain("decoration-dotted");
  expect(doubtful.className).toContain("decoration-dotted");

  const rows = within(screen.getByRole("list", { name: "Proposed corrections" })).getAllByRole(
    "listitem",
  );
  expect(rows).toHaveLength(2);
  expect(rows[0]).toHaveTextContent("I completed the user story");
  expect(rows[0]).toHaveTextContent("verb tense · missing past marker");
  expect(rows[1]).toHaveTextContent("may be a mishearing");
});

test("a correction whose words could not be placed is listed and says it is unmarked", () => {
  const marked = markTranscript(TRANSCRIPT, [{ ...ITEMS[0], span_start: null, span_end: null }]);
  const { container } = render(
    <>
      <MarkedText marked={marked} />
      <CorrectionList corrections={marked.corrections} />
    </>,
  );

  expect(container.querySelector("mark")).toBeNull();
  expect(screen.getByText(/not marked above/)).toBeInTheDocument();
  expect(screen.getByText("I completed the user story")).toBeInTheDocument();
});

test("nothing is rendered for a turn with no corrections", () => {
  const { container } = render(<CorrectionList corrections={[]} />);
  expect(container).toBeEmptyDOMElement();
});
