/**
 * A check's fixes: marked in the person's words, each with its source, and counted only
 * when it is writing that was kept.
 */

import { render, screen, within } from "@testing-library/react";

import { CaptureFixes } from "@/components/CaptureFixes";
import { makeCheck } from "@/test/fixtures";

test("each fix is marked where it is and listed with what found it", () => {
  const check = makeCheck();
  render(<CaptureFixes text={check.source_text} fixes={check.fixes} />);

  const list = screen.getByRole("list", { name: "Fixes" });
  const rows = within(list).getAllByRole("listitem");
  expect(rows).toHaveLength(2);
  expect(rows[0]).toHaveTextContent("recieved→received");
  expect(rows[0]).toHaveTextContent("spelling");
  expect(rows[0]).toHaveTextContent("dictionary");
  expect(screen.getAllByText(/^recieved$|^tomorow$/).length).toBeGreaterThan(0);
  expect(screen.queryByText(/not counted/)).not.toBeInTheDocument();
});

test("English said aloud is shown and said not to count", () => {
  const check = makeCheck({ via: "voice" });
  render(
    <CaptureFixes text={check.source_text} fixes={check.fixes} uncounted="shown, not counted: said aloud" />,
  );

  expect(screen.getAllByText("shown, not counted: said aloud")).toHaveLength(2);
});

test("English with nothing to fix keeps the words and says so, with no empty list", () => {
  render(<CaptureFixes text="I sent it this morning." fixes={[]} />);

  expect(screen.getByText("I sent it this morning.")).toBeInTheDocument();
  expect(screen.getByTestId("no-fixes")).toHaveTextContent("Nothing to fix");
  expect(screen.queryByRole("list")).not.toBeInTheDocument();
});
