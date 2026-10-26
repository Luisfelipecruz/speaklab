/**
 * The Notebook page, in the states it has: signed out, empty, filtered to nothing, and a
 * list grouped by the reader's day with what is due above it.
 */

import { render, screen, within } from "@testing-library/react";

import NotebookPage from "@/app/(app)/notebook/page";
import type { CaptureList } from "@/lib/api";
import { makeCaptureList, makeCaptureSummary } from "@/test/fixtures";

jest.mock("@/lib/server-api", () => ({ serverRequestOrNull: jest.fn() }));
jest.mock("@/lib/server-zone", () => ({ readerZone: jest.fn(async () => "Asia/Dubai") }));
jest.mock("@/components/WriteInEnglish", () => ({ WriteInEnglish: () => <div data-testid="write-in-english" /> }));
jest.mock("@/components/TimeZoneCookie", () => ({ TimeZoneCookie: () => null }));
jest.mock("next/navigation", () => ({ useRouter: () => ({ push: jest.fn(), refresh: jest.fn() }) }));

import { serverRequestOrNull } from "@/lib/server-api";

const request = serverRequestOrNull as jest.MockedFunction<typeof serverRequestOrNull>;

function answer(list: CaptureList | null, due: CaptureList | null = makeCaptureList({ items: [] })) {
  request.mockImplementation(((path: string) => {
    if (path.startsWith("/captures?state=due&limit=3")) return Promise.resolve(due);
    if (path.startsWith("/captures?")) return Promise.resolve(list);
    throw new Error(`unexpected request: ${path}`);
  }) as typeof serverRequestOrNull);
}

async function open(params: Record<string, string> = {}) {
  render(await NotebookPage({ searchParams: Promise.resolve(params) }));
}

beforeEach(() => request.mockReset());

test("signed out, it asks to sign in and come back here", async () => {
  answer(null);

  await open();

  expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login?next=/notebook");
});

test("empty, it says how captures arrive and that only text is kept", async () => {
  answer(makeCaptureList({ items: [], matching: 0, counts: { total: 0, this_week: 0, practised_this_week: 0, clean_this_week: 0, due: 0, to_practise: 0 }, apps: [] }));

  await open();

  expect(screen.getByTestId("write-in-english")).toBeInTheDocument();
  expect(screen.getByText(/hold fn in any app/)).toBeInTheDocument();
  expect(screen.getByText(/never the recording/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Delete every capture/ })).not.toBeInTheDocument();
});

test("captures are grouped by the reader's day, with the time on their clock", async () => {
  answer(
    makeCaptureList({
      items: [
        makeCaptureSummary({ id: 2, created_at: "2026-10-24T21:30:00Z", app: "Slack" }),
        makeCaptureSummary({ id: 1, created_at: "2026-10-24T05:12:00Z" }),
      ],
      matching: 2,
    }),
  );

  await open();

  const sunday = screen.getByRole("region", { name: "Sunday 25 October" });
  expect(within(sunday).getByText("01:30")).toBeInTheDocument();
  const saturday = screen.getByRole("region", { name: "Saturday 24 October" });
  expect(within(saturday).getByText("09:12")).toBeInTheDocument();
  expect(within(saturday).getByRole("link", { name: "Practise" })).toHaveAttribute("href", "/notebook/1/practise");
});

test("what is due again is above the list, one step from writing it", async () => {
  answer(
    makeCaptureList({ counts: { ...makeCaptureList().counts, due: 1 } }),
    makeCaptureList({ items: [makeCaptureSummary({ id: 9, state: "due", source_text: "Necesito que me confirmes antes del martes" })] }),
  );

  await open();

  const due = screen.getByRole("region", { name: "Due again" });
  expect(within(due).getByRole("link", { name: /Necesito que me confirmes/ })).toHaveAttribute("href", "/notebook/9/practise");
});

test("a filter that matches nothing offers everything back, and asks for no strip", async () => {
  answer(makeCaptureList({ items: [], matching: 0 }));

  await open({ view: "due" });

  expect(screen.getByText(/Nothing here matches/)).toBeInTheDocument();
  expect(request).not.toHaveBeenCalledWith("/captures?state=due&limit=3");
  expect(request.mock.calls[0]![0]).toContain("state=due");
});

test("the counts over the list are the API's", async () => {
  answer(makeCaptureList({ counts: { total: 9, this_week: 9, practised_this_week: 4, clean_this_week: 2, due: 1, to_practise: 5 } }));

  await open();

  expect(screen.getByText("captures this week").previousSibling).toHaveTextContent("9");
  expect(screen.getByText("with no counted mistake").previousSibling).toHaveTextContent("2");
  expect(screen.getByRole("button", { name: /Delete every capture/ })).toBeInTheDocument();
});
