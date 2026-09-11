/**
 * One kind of correction, in the learner's own sentences.
 *
 * The assertions are about the evidence being there and being honest about itself: the
 * mark covers the transcript's words and nothing else, a doubtful correction says why it
 * is doubtful, a correction that could not be placed is not marked on anything, and every
 * one links back to the conversation it came from.
 */

import { render, screen, within } from "@testing-library/react";

import { GrammarCategory } from "@/components/GrammarCategory";
import { makeCategory, makeCorrectionExample } from "@/test/fixtures";

test("a correction is shown in the sentence it was made in, marked on its own words", () => {
  const { container } = render(<GrammarCategory category={makeCategory()} />);

  const mark = container.querySelector("mark");
  expect(mark).toHaveTextContent(/^I complete the user story$/);
  expect(screen.getByText("I completed the user story")).toBeInTheDocument();
  expect(screen.getByTestId("correction")).toHaveTextContent(
    "Yesterday I complete the user story and we request a review.",
  );
});

test("it links to the conversation it came from", () => {
  render(<GrammarCategory category={makeCategory()} />);

  expect(screen.getByRole("link", { name: /Daily standup/ })).toHaveAttribute(
    "href",
    "/sessions/12",
  );
});

test("the heading carries what was counted, and what was shown and not counted", () => {
  render(
    <GrammarCategory category={makeCategory({ counted: 3, not_counted: 1, per_100_words: 1.1 })} />,
  );

  expect(screen.getByText(/3 counted · 1.1 per 100 words · 1 not counted/)).toBeInTheDocument();
  expect(screen.getByText(/went\/gone/)).toBeInTheDocument();
});

test("a correction on words the recogniser was unsure of says so and is drawn apart", () => {
  const { container } = render(
    <GrammarCategory
      category={makeCategory({
        counted: 0,
        not_counted: 1,
        examples: [makeCorrectionExample({ counted: false, asr_suspect: true })],
      })}
    />,
  );

  expect(screen.getByText("may be a mishearing")).toBeInTheDocument();
  expect(container.querySelector("mark")).toHaveClass("decoration-dotted");
});

test("a rule's correction says a grammar rule found it", () => {
  render(
    <GrammarCategory
      category={makeCategory({ examples: [makeCorrectionExample({ detector: "rule" })] })}
    />,
  );

  expect(screen.getByText("grammar rule")).toBeInTheDocument();
});

test("a correction that could not be placed is shown on its own and marks nothing", () => {
  const { container } = render(
    <GrammarCategory
      category={makeCategory({
        examples: [makeCorrectionExample({ before: "", quote: null, after: "" })],
      })}
    />,
  );

  expect(container.querySelector("mark")).toBeNull();
  const row = screen.getByTestId("correction");
  expect(within(row).getAllByText("I complete the user story")).toHaveLength(1);
});

test("when only the newest are quoted, it says how many there are and where the rest are", () => {
  render(<GrammarCategory category={makeCategory({ counted: 7 })} />);

  expect(screen.getByText(/The newest 1 of 7/)).toBeInTheDocument();
});

test("a correction placed in its sentence can be said again; one that is not, cannot", () => {
  render(
    <GrammarCategory
      category={makeCategory({
        counted: 2,
        examples: [
          makeCorrectionExample(),
          makeCorrectionExample({ id: 42, quote: null, before: "", after: "" }),
        ],
      })}
    />,
  );

  const links = screen.getAllByRole("link", { name: "Say it again" });
  expect(links).toHaveLength(1);
  expect(links[0]).toHaveAttribute("href", "/grammar/drill/41");
});
