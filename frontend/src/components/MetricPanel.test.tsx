/**
 * A family of measurements, and the caveat that has to travel with one of them.
 *
 * The accuracy family is the only one whose numbers rest on a language model's labelling,
 * and the measured quality of that labelling belongs beside the chart rather than in a
 * document nobody opens. The test is here because a caveat is exactly the kind of thing
 * that gets moved to a tooltip during a tidy-up.
 */

import { render, screen } from "@testing-library/react";

import { MetricPanel } from "@/components/MetricPanel";
import { makeFamily, makeSeries } from "@/test/fixtures";

test("the accuracy family carries its caveat on the panel itself", () => {
  render(
    <MetricPanel
      family={makeFamily({
        caveat:
          "The rate is counted from stored corrections and is exact. The categories measured 0.50 precision.",
      })}
    />,
  );

  expect(screen.getByTestId("caveat")).toHaveTextContent("0.50 precision");
});

test("a family with nothing to qualify shows no caveat", () => {
  render(<MetricPanel family={makeFamily({ name: "fluency", caveat: null })} />);
  expect(screen.queryByTestId("caveat")).not.toBeInTheDocument();
});

test("a family whose every series is suppressed still appears, with its reasons", () => {
  // Hiding it would leave a user with nothing to see and no way to find out what would
  // make something appear.
  render(
    <MetricPanel
      family={makeFamily({
        series: [
          makeSeries({
            gate: { shown: false, reason: "No period yet has 50 words in it.", have: 0, need: 50 },
          }),
        ],
      })}
    />,
  );

  expect(screen.getByText("What you get wrong")).toBeInTheDocument();
  expect(screen.getByTestId("gate-reason")).toHaveTextContent("50 words");
  expect(screen.getByText(/each line below says what it is waiting for/i)).toBeInTheDocument();
});

test("every series in the family is rendered", () => {
  render(
    <MetricPanel
      family={makeFamily({
        series: [
          makeSeries({ metric: "a", label: "first" }),
          makeSeries({ metric: "b", label: "second" }),
        ],
      })}
    />,
  );

  expect(screen.getByText("first")).toBeInTheDocument();
  expect(screen.getByText("second")).toBeInTheDocument();
});
