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

test("a verb form's accuracy is a count, and never a percentage", () => {
  // The API sends a proportion above its floor. A floor on the sample does nothing about
  // the corrections underneath, which are the larger error, so the page does not show it.
  render(
    <RepertoireChart
      repertoire={makeRepertoire({
        forms: { present_simple: 12, past_simple: 2 },
        accuracy: {
          present_simple: { used: 12, right: 9, wrong: 3, missed: 1, accuracy: 0.6923 },
          past_simple: { used: 2, right: 1, wrong: 1, missed: 0, accuracy: null },
        },
      })}
    />,
  );

  expect(screen.getByTestId("form-accuracy-present_simple")).toHaveTextContent(
    /^right 9 of 13$/,
  );
  expect(screen.getByTestId("form-accuracy-past_simple")).toHaveTextContent(/^right 1 of 2$/);
  expect(screen.queryByText(/%/)).not.toBeInTheDocument();
});

test("a form that was needed and never said is listed, because avoiding it is the finding", () => {
  render(
    <RepertoireChart
      repertoire={makeRepertoire({
        forms: { present_simple: 5, past_simple: 3 },
        accuracy: {
          present_perfect: { used: 0, right: 0, wrong: 0, missed: 2, accuracy: null },
        },
      })}
    />,
  );

  const listed = screen.getAllByRole("listitem").map((node) => node.textContent);
  expect(listed[listed.length - 1]).toContain("present perfect");
  expect(screen.getByTestId("form-accuracy-present_perfect")).toHaveTextContent(
    "needed 2, never said",
  );
});

test("a form with no accuracy, such as a clause count, shows only its count", () => {
  render(
    <RepertoireChart
      repertoire={makeRepertoire({ forms: { main_clause: 4 }, accuracy: {} })}
    />,
  );

  expect(screen.queryByTestId("form-accuracy-main_clause")).not.toBeInTheDocument();
});

test("the detail behind a verb form's accuracy is in its tooltip", () => {
  render(
    <RepertoireChart
      repertoire={makeRepertoire({
        forms: { present_simple: 12 },
        accuracy: {
          present_simple: { used: 12, right: 9, wrong: 3, missed: 1, accuracy: 0.6923 },
        },
      })}
    />,
  );

  expect(screen.getByTestId("form-accuracy-present_simple")).toHaveAttribute(
    "title",
    "said 12 times, 3 of them corrected; needed 1 time more where another form was said",
  );
});

test("the caveat the API sends with accuracy per form is shown beside it", () => {
  render(
    <RepertoireChart
      repertoire={makeRepertoire({
        accuracy: {
          present_simple: { used: 9, right: 8, wrong: 1, missed: 0, accuracy: null },
        },
        caveat: "A wrong correction counts against a form you used correctly.",
      })}
    />,
  );

  expect(screen.getByTestId("form-accuracy-caveat")).toHaveTextContent(
    "a form you used correctly",
  );
});

test("no caveat is shown when there is no accuracy to qualify", () => {
  render(<RepertoireChart repertoire={makeRepertoire({ caveat: null })} />);
  expect(screen.queryByTestId("form-accuracy-caveat")).not.toBeInTheDocument();
});
