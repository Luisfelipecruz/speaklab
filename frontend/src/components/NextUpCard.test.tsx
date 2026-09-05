/**
 * The recommendations, and the thing that makes them worth reading.
 *
 * Every entry has to carry the measurement that chose it and, where one exists, somewhere
 * to go and act on it. A suggestion with no traceable reason is indistinguishable from a
 * guess; a reason with nowhere to act on it is not advice.
 *
 * The confidence badge is tested because it is the honest half. It comes from the same
 * sample counts the charts are gated on, and it is what tells a reader whether they are
 * looking at a ranking that is probably right or one that is definitely right.
 */

import { render, screen } from "@testing-library/react";

import { NextUpCard } from "@/components/NextUpCard";
import { makeRecommendations } from "@/test/fixtures";

test("every suggestion shows the measurement behind it", () => {
  render(<NextUpCard recommendations={makeRecommendations()} />);

  expect(screen.getByText(/6 corrections in 272 words/)).toBeInTheDocument();
  expect(screen.getByText(/30 instances scored/)).toBeInTheDocument();
  expect(screen.getByText(/Not once in 272 words/)).toBeInTheDocument();
});

test("a weak sound links to a passage built around it", () => {
  render(<NextUpCard recommendations={makeRecommendations()} />);

  expect(screen.getByRole("link", { name: "Read a passage" })).toHaveAttribute(
    "href",
    "/read/third-street-theatre",
  );
});

test("an unused form links to a scenario that asks for it", () => {
  render(<NextUpCard recommendations={makeRecommendations()} />);

  expect(screen.getByRole("link", { name: "Practise this" })).toHaveAttribute(
    "href",
    "/scenarios/job-interview-backend",
  );
});

test("a suggestion with nowhere to act on it shows no link rather than a dead one", () => {
  render(
    <NextUpCard
      recommendations={makeRecommendations({
        items: [
          {
            kind: "error_category",
            title: "verb tense",
            reason: "6 corrections in 272 words.",
            measured: 2.2,
            samples: 6,
            score: 0.9,
            scenario_slug: null,
            passage_slug: null,
          },
        ],
      })}
    />,
  );

  expect(screen.queryByRole("link")).not.toBeInTheDocument();
});

test("thin evidence is labelled as thin", () => {
  render(<NextUpCard recommendations={makeRecommendations({ confidence: "low" })} />);

  expect(screen.getByTestId("confidence")).toHaveTextContent("thin evidence");
  expect(screen.getByText(/not enough to be sure of one/)).toBeInTheDocument();
});

test("an account with nothing measured is pointed at the thing that would measure it", () => {
  render(
    <NextUpCard
      recommendations={makeRecommendations({
        confidence: "none",
        detail: "Nothing has been analysed for this account yet.",
        items: [
          {
            kind: "practise",
            title: "Have a conversation",
            reason: "There is nothing measured to go on yet.",
            measured: null,
            samples: 0,
            score: 0,
            scenario_slug: null,
            passage_slug: null,
          },
        ],
      })}
    />,
  );

  expect(screen.getByTestId("confidence")).toHaveTextContent("nothing measured yet");
  expect(screen.getByRole("link", { name: "Choose a scenario" })).toHaveAttribute(
    "href",
    "/scenarios",
  );
});
