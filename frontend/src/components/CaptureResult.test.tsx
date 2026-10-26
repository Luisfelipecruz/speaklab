/**
 * What comes back from the panel: the English to paste, the other version a click away —
 * written on the server for a kept capture, sent again for a paused one — the notes, and
 * the way to its moment.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { CaptureResult } from "@/components/CaptureResult";
import { ApiError } from "@/lib/api";
import { CAPTURE_DIRECT, CAPTURE_ORGANIZED, makeCapture, makeCheck } from "@/test/fixtures";

jest.mock("@/lib/api", () => {
  const actual = jest.requireActual("@/lib/api");
  return { ...actual, postCapture: jest.fn(), writeCaptureVersion: jest.fn() };
});

// eslint-disable-next-line @typescript-eslint/no-require-imports
const api = require("@/lib/api") as { postCapture: jest.Mock; writeCaptureVersion: jest.Mock };

beforeEach(() => jest.clearAllMocks());

test("the English copied by default is shown large, with the way to its moment", () => {
  render(<CaptureResult capture={makeCapture()} />);

  expect(screen.getByTestId("english-organized")).toHaveTextContent("A quick heads-up");
  expect(screen.getByRole("button", { name: "Copy" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /open its moment/ })).toHaveAttribute("href", "/notebook/12");
});

test("a version already written is shown at once, and the first is one click back", async () => {
  const user = userEvent.setup();
  render(<CaptureResult capture={makeCapture()} />);

  await user.click(screen.getByRole("button", { name: "Show Direct" }));

  expect(screen.getByTestId("english-direct")).toHaveTextContent(CAPTURE_DIRECT.slice(0, 30));
  await user.click(screen.getByRole("button", { name: "Back to Organized" }));
  expect(screen.getByTestId("english-organized")).toBeInTheDocument();
  expect(api.writeCaptureVersion).not.toHaveBeenCalled();
});

test("a kept capture's missing version is written on the server", async () => {
  const user = userEvent.setup();
  const capture = makeCapture({ versions: { organized: CAPTURE_ORGANIZED, direct: null } });
  api.writeCaptureVersion.mockResolvedValue(makeCapture());
  render(<CaptureResult capture={capture} />);

  await user.click(screen.getByRole("button", { name: "Show Direct" }));

  await waitFor(() => expect(screen.getByTestId("english-direct")).toBeInTheDocument());
  expect(api.writeCaptureVersion).toHaveBeenCalledWith(12, "direct");
});

test("with saving paused the other version is asked for with the same words, paused too", async () => {
  const user = userEvent.setup();
  const capture = makeCapture({
    id: null,
    saved: false,
    via: "typed",
    versions: { organized: CAPTURE_ORGANIZED, direct: null },
  });
  api.postCapture.mockResolvedValue(makeCapture({ id: null, saved: false, chosen: "direct", versions: { direct: CAPTURE_DIRECT, organized: null } }));
  render(<CaptureResult capture={capture} />);

  await user.click(screen.getByRole("button", { name: "Show Direct" }));

  await waitFor(() => expect(screen.getByTestId("english-direct")).toBeInTheDocument());
  expect(api.postCapture).toHaveBeenCalledWith({
    text: capture.source_text,
    mode: "translate",
    version: "direct",
    save: false,
  });
  expect(screen.getByText("Not kept: saving is paused.")).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: /open its moment/ })).not.toBeInTheDocument();
});

test("a version that cannot be written says why", async () => {
  const user = userEvent.setup();
  api.writeCaptureVersion.mockRejectedValue(new ApiError("Direct needs the language model, which is not answering.", 503));
  render(<CaptureResult capture={makeCapture({ versions: { organized: CAPTURE_ORGANIZED, direct: null } })} />);

  await user.click(screen.getByRole("button", { name: "Show Direct" }));

  expect(await screen.findByText(/not answering/)).toBeInTheDocument();
});

test("a check shows its fixes, and a paused one says none of them counts", () => {
  render(<CaptureResult capture={makeCheck({ id: null, saved: false })} />);

  expect(screen.getByRole("list", { name: "Fixes" })).toBeInTheDocument();
  expect(screen.getAllByText("not counted: saving is paused")).toHaveLength(2);
});

test("a note about how it was made is said", () => {
  render(
    <CaptureResult
      capture={makeCapture({ chosen: "rough", text: "Laura, I write you.", versions: { rough: "Laura, I write you.", organized: null, direct: null }, notes: ["The language model did not answer, so this is the recogniser's own English, rough and literal."] })}
    />,
  );

  expect(screen.getByText(/rough and literal/)).toBeInTheDocument();
  expect(screen.getByTestId("english-rough")).toHaveTextContent("Laura, I write you.");
});
