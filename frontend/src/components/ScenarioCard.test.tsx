/**
 * The catalogue row.
 *
 * The assertion that earns its place is the last one: the persona's instructions are the
 * other half of the exercise, and a card that leaked them would make the scenario
 * pointless before it started. The API does not serve the field at all — a server test
 * asserts that — so this is the second lock on the same door.
 */

import { render, screen } from "@testing-library/react";

import { ScenarioCard, humanise, mistakeLabel } from "@/components/ScenarioCard";
import { makeScenario } from "@/test/fixtures";

test("the whole card leads to the scenario", () => {
  render(<ScenarioCard scenario={makeScenario()} />);

  expect(screen.getByRole("link", { name: "Job interview — backend engineer" })).toHaveAttribute(
    "href",
    "/scenarios/job-interview-backend",
  );
});

test("the band and setting are legible, not raw column values", () => {
  render(<ScenarioCard scenario={makeScenario({ category: "customer_service" })} />);

  expect(screen.getByText("B2")).toBeInTheDocument();
  expect(screen.getByText("customer service")).toBeInTheDocument();
});

test("the forms a scenario is built to draw out are shown", () => {
  render(<ScenarioCard scenario={makeScenario()} />);

  // A scenario declares the grammar it should elicit, and the eval harness later checks
  // whether it did. Showing it is what makes choosing a scenario a decision.
  expect(screen.getByText("present perfect")).toBeInTheDocument();
  expect(screen.getByText("past simple")).toBeInTheDocument();
});

test("the kinds of mistake it is built to draw out are shown, as the grammar page names them", () => {
  render(
    <ScenarioCard
      scenario={makeScenario({ target_errors: ["PREPOSITION", "LEXICAL_CHOICE"] })}
    />,
  );

  expect(screen.getByText("preposition")).toHaveAttribute(
    "title",
    "A kind of mistake this scenario is built to draw out",
  );
  expect(screen.getByText("lexical choice")).toBeInTheDocument();
  expect(screen.queryByText("PREPOSITION")).not.toBeInTheDocument();
});

test("a long list of forms is trimmed rather than allowed to wrap the card", () => {
  render(
    <ScenarioCard
      scenario={makeScenario({
        target_grammar: ["a_one", "b_two", "c_three", "d_four", "e_five"],
      })}
    />,
  );

  expect(screen.getByText("a one")).toBeInTheDocument();
  expect(screen.queryByText("d four")).not.toBeInTheDocument();
});

test("nothing on the card could carry the persona's instructions", () => {
  const scenario = makeScenario();
  const { container } = render(<ScenarioCard scenario={scenario} />);

  expect(Object.keys(scenario)).not.toContain("persona_prompt");
  expect(container.textContent).not.toMatch(/you are|interviewer should/i);
});

test("humanise leaves an already-readable label alone", () => {
  expect(humanise("workplace")).toBe("workplace");
  expect(humanise("present_perfect")).toBe("present perfect");
  expect(humanise("small-talk")).toBe("small talk");
});

test("an error category reads as the grammar page reads it", () => {
  expect(mistakeLabel("ARTICLE")).toBe("article");
  expect(mistakeLabel("SUBJECT_VERB_AGREEMENT")).toBe("subject verb agreement");
});
