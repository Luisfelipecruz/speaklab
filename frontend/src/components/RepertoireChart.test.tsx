/**
 * Breadth, and the one warning this product exists to be able to give.
 *
 * A learner who retreats to the present simple makes fewer mistakes, and an accuracy chart
 * alone calls that progress. The warning is the sentence that stops it, so the test that
 * it is rendered — and that it stays out of the way of a genuinely good week — is the
 * point of this file.
 */

import { render, screen } from "@testing-library/react";

import { RepertoireChart } from "@/components/RepertoireChart";
import { makeRepertoire } from "@/test/fixtures";

test("the forms are listed with their counts, most used first", () => {
  render(
    <RepertoireChart
      repertoire={makeRepertoire({
        forms: { past_simple: 4, present_simple: 9, going_to_future: 1 },
      })}
    />,
  );

  const listed = screen.getAllByRole("listitem").map((node) => node.textContent);
  expect(listed[0]).toContain("present simple");
  expect(listed[listed.length - 1]).toContain("going to future");
});

test("underscores are not shown to a learner", () => {
  render(<RepertoireChart repertoire={makeRepertoire({ forms: { going_to_future: 2 } })} />);

  expect(screen.getByText("going to future")).toBeInTheDocument();
  expect(screen.queryByText("going_to_future")).not.toBeInTheDocument();
});

test("a narrowing repertoire with fewer errors is rendered as a warning", () => {
  render(
    <RepertoireChart
      repertoire={makeRepertoire({
        distinct_forms: 1,
        previous_distinct_forms: 3,
        warning:
          "You used 1 different forms, down from 3, and your error rate fell — that is not the same as improving.",
      })}
    />,
  );

  expect(screen.getByTestId("repertoire-warning")).toHaveTextContent(
    "not the same as improving",
  );
});

test("no warning is invented when the API did not send one", () => {
  render(<RepertoireChart repertoire={makeRepertoire({ warning: null })} />);
  expect(screen.queryByTestId("repertoire-warning")).not.toBeInTheDocument();
});

test("the previous period's count is shown beside this one", () => {
  render(
    <RepertoireChart
      repertoire={makeRepertoire({ distinct_forms: 5, previous_distinct_forms: 2 })}
    />,
  );

  expect(screen.getByText("5")).toBeInTheDocument();
  expect(screen.getByText(/2 the period before/)).toBeInTheDocument();
});

test("an account with nothing counted is told what would fill it in", () => {
  render(<RepertoireChart repertoire={makeRepertoire({ forms: {}, distinct_forms: 0 })} />);
  expect(screen.getByText(/a conversation of any length fills this in/i)).toBeInTheDocument();
});
