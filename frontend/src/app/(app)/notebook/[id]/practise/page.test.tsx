/**
 * Write it yourself: what was said, the box, the versions folded until wanted, and how it
 * is counted.
 */

import { render, screen } from "@testing-library/react";

import PractisePage from "@/app/(app)/notebook/[id]/practise/page";
import type { Capture } from "@/lib/api";
import { CAPTURE_SAID, makeCapture } from "@/test/fixtures";

jest.mock("@/lib/server-api", () => ({ serverRequestOrNull: jest.fn() }));
jest.mock("@/lib/server-zone", () => ({ readerZone: jest.fn(async () => "Asia/Dubai") }));
jest.mock("@/components/TimeZoneCookie", () => ({ TimeZoneCookie: () => null }));
jest.mock("@/components/WriteItYourself", () => ({ WriteItYourself: () => <div data-testid="write-it" /> }));
jest.mock("next/navigation", () => ({
  notFound: () => {
    throw new Error("NEXT_NOT_FOUND");
  },
}));

import { serverRequestOrNull } from "@/lib/server-api";

const request = serverRequestOrNull as jest.MockedFunction<typeof serverRequestOrNull>;

function answer(capture: Capture | null) {
  request.mockImplementation(((path: string) => {
    if (path === "/captures/12") return Promise.resolve(capture);
    throw new Error(`unexpected request: ${path}`);
  }) as typeof serverRequestOrNull);
}

beforeEach(() => request.mockReset());

test("what was said comes first, then the box, with the versions folded", async () => {
  answer(makeCapture());

  render(await PractisePage({ params: Promise.resolve({ id: "12" }) }));

  expect(screen.getByRole("heading", { name: "Write it yourself" })).toBeInTheDocument();
  expect(screen.getByText(/In Mail, Sunday 25 October, 09:12/)).toBeInTheDocument();
  expect(screen.getByTestId("practise-source")).toHaveTextContent(CAPTURE_SAID);
  expect(screen.getByTestId("write-it")).toBeInTheDocument();
  const folded = screen.getByText("The two versions you could have pasted").closest("details");
  expect(folded).not.toHaveAttribute("open");
  expect(screen.getByText("How this is counted")).toBeInTheDocument();
});

test("a capture that is not there asks to sign in and come back to practise it", async () => {
  answer(null);

  render(await PractisePage({ params: Promise.resolve({ id: "12" }) }));

  expect(screen.getByRole("link", { name: "sign in" })).toHaveAttribute("href", "/login?next=/notebook/12/practise");
});
