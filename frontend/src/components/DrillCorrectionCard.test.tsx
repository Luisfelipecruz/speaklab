/**
 * The correction, read before it is said.
 *
 * What must be on it: the sentence as it was said, what was proposed and why, where it came
 * from, every other correction the sentence to say carries, and the invitation to skip it.
 */

import { render, screen } from "@testing-library/react";

import { DrillCorrectionCard } from "@/components/DrillCorrectionCard";
import { makeDrill } from "@/test/fixtures";

test("the correction is shown in the sentence it was made in, with why and from where", () => {
  render(<DrillCorrectionCard drill={makeDrill()} />);

  expect(screen.getByTestId("drill-said")).toHaveTextContent("Yesterday I complete the user story.");
  expect(screen.getByText("I completed")).toBeInTheDocument();
  expect(screen.getByText(/Yesterday needs the past simple/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /Daily standup/ })).toHaveAttribute("href", "/sessions/12");
  expect(screen.getByText(/if you think it is wrong, skip it/)).toBeInTheDocument();
});

test("other corrections the sentence carries are listed, since they are in it too", () => {
  const drill = makeDrill({
    corrections: [
      ...makeDrill().corrections,
      {
        ...makeDrill().corrections[0],
        id: 42,
        original: "she say",
        correction: "she said",
        detector: "rule",
      },
    ],
  });

  render(<DrillCorrectionCard drill={drill} />);

  expect(screen.getByText(/one other correction, and it is in the sentence to say too/)).toBeInTheDocument();
  expect(screen.getByText("she say")).toBeInTheDocument();
  expect(screen.getByText("grammar rule")).toBeInTheDocument();
});

test("a correction that cannot be placed is shown on its own", () => {
  render(<DrillCorrectionCard drill={makeDrill({ pieces: [], unavailable: "Not placed." })} />);

  expect(screen.queryByTestId("drill-said")).not.toBeInTheDocument();
  expect(screen.getByText("I complete")).toHaveClass("line-through");
});
