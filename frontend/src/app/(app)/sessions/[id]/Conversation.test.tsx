/**
 * The conversation page, and the one thing it does on its own when it is opened.
 *
 * A report written before its last turns were analysed leaves them out, and the page is
 * where that gets finished — ending the session again is what rebuilds it. The tests are
 * about when that happens: once, on opening a finished session whose report is
 * unfinished, and never on a complete report or a conversation still going.
 */

import { render, screen, waitFor } from "@testing-library/react";

import { Conversation } from "@/app/(app)/sessions/[id]/Conversation";
import { makeAnalysis, makeReport, makeSession } from "@/test/fixtures";

jest.mock("@/hooks/useRecorder", () => ({
  useRecorder: () => ({
    state: "idle",
    error: null,
    mimeType: null,
    analyser: null,
    elapsedMs: 0,
    start: jest.fn(),
    stop: jest.fn(),
    cancel: jest.fn(),
    clearError: jest.fn(),
  }),
}));

jest.mock("@/lib/api", () => {
  const actual = jest.requireActual("@/lib/api");
  return { ...actual, endSession: jest.fn(), getSession: jest.fn(), postTurn: jest.fn() };
});

// eslint-disable-next-line @typescript-eslint/no-require-imports
const api = require("@/lib/api") as { endSession: jest.Mock };

const UNFINISHED = makeReport({
  analysis: makeAnalysis({ complete: false, turns_analysed: 5, turns_outstanding: 1 }),
});

beforeEach(() => jest.clearAllMocks());

test("opening an ended session with an unfinished report finishes it", async () => {
  const opened = makeSession({ status: "completed", report: UNFINISHED });
  api.endSession.mockResolvedValue(makeSession({ status: "completed", report: makeReport() }));

  render(<Conversation sessionId={12} initial={opened} />);

  await waitFor(() => expect(api.endSession).toHaveBeenCalledWith(12));
  await waitFor(() =>
    expect(screen.queryByText(/had not been analysed when this report/)).not.toBeInTheDocument(),
  );
  expect(api.endSession).toHaveBeenCalledTimes(1);
});

test("a report that is still unfinished afterwards is not retried on its own", async () => {
  // The end that just came back waited as long as the server allows. The report says
  // what it leaves out and offers to try again; the page does not loop.
  const opened = makeSession({ status: "completed", report: UNFINISHED });
  api.endSession.mockResolvedValue(opened);

  render(<Conversation sessionId={12} initial={opened} />);

  expect(
    await screen.findByRole("button", { name: "Finish the report" }),
  ).toBeInTheDocument();
  expect(api.endSession).toHaveBeenCalledTimes(1);
});

test("a complete report is left as it is", () => {
  render(
    <Conversation
      sessionId={12}
      initial={makeSession({ status: "completed", report: makeReport() })}
    />,
  );

  expect(api.endSession).not.toHaveBeenCalled();
});

test("a conversation still going is not ended by opening it", () => {
  render(<Conversation sessionId={12} initial={makeSession()} />);

  expect(api.endSession).not.toHaveBeenCalled();
  expect(screen.getByRole("button", { name: "End and get a report" })).toBeEnabled();
});
