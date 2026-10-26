/**
 * The moment of a capture: where and when, what was said, the English used and the other,
 * what was kept, the phrases, what has been practised — and no more than was kept.
 */

import { render, screen, within } from "@testing-library/react";

import MomentPage from "@/app/(app)/notebook/[id]/page";
import type { Capture } from "@/lib/api";
import { makeCapture, makeCheck } from "@/test/fixtures";

jest.mock("@/lib/server-api", () => ({ serverRequestOrNull: jest.fn() }));
jest.mock("@/lib/server-zone", () => ({ readerZone: jest.fn(async () => "Asia/Dubai") }));
jest.mock("@/components/TimeZoneCookie", () => ({ TimeZoneCookie: () => null }));
jest.mock("@/components/SayItYourself", () => ({ SayItYourself: () => <div data-testid="say-it" /> }));
jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn(), refresh: jest.fn() }),
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

async function open(id = "12") {
  render(await MomentPage({ params: Promise.resolve({ id }) }));
}

beforeEach(() => request.mockReset());

test("a capture that is not there asks to sign in, and an id that is not a number is not found", async () => {
  answer(null);
  await open();
  expect(screen.getByRole("link", { name: "sign in" })).toHaveAttribute("href", "/login?next=/notebook/12");

  await expect(open("x")).rejects.toThrow("NEXT_NOT_FOUND");
});

test("the moment says where, when, how and which version was copied", async () => {
  answer(makeCapture());

  await open();

  expect(screen.getByRole("heading", { name: /Laura, te escribo para avisarte/ })).toBeInTheDocument();
  expect(screen.getByText("Sunday 25 October, 09:12")).toBeInTheDocument();
  expect(screen.getByText("Mail")).toBeInTheDocument();
  expect(screen.getByText("Said, 9 s")).toBeInTheDocument();
  expect(screen.getByText("You copied Organized")).toBeInTheDocument();
  expect(screen.getByTestId("kept")).toHaveTextContent("Laura · 14 · Acme");
  expect(screen.getByTestId("english-organized")).toBeInTheDocument();
  expect(screen.getByText(/The other version · Direct/)).toBeInTheDocument();
});

test("the phrases worth keeping count the other captures that use them", async () => {
  answer(makeCapture());

  await open();

  const row = screen.getByRole("row", { name: /te escribo para avisarte/ });
  expect(within(row).getByText("a quick heads-up")).toBeInTheDocument();
  expect(within(row).getByText("3")).toBeInTheDocument();
});

test("what was practised since is listed, and when it comes back", async () => {
  answer(makeCheck());

  await open();

  expect(screen.getByRole("list", { name: "Written yourself" })).toHaveTextContent("2 counted mistakes in 10 words, box 1");
  expect(screen.getByTestId("due")).toHaveTextContent("Comes back");
});

test("a check said aloud shows its fixes and says they do not count", async () => {
  answer(makeCheck({ via: "voice", attempts: [], state: "to_practise", box: 0, due_at: null }));

  await open();

  expect(screen.getAllByText("shown, not counted: said aloud")).toHaveLength(2);
  expect(screen.getByText("Not written yourself yet.")).toBeInTheDocument();
});

test("it says what it never reads, and the conversation practice is not offered yet", async () => {
  answer(makeCapture());

  await open();

  expect(screen.getByText(/never reads the window/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Practise it as a conversation/ })).toBeDisabled();
  expect(screen.getByRole("link", { name: /Write it yourself/ })).toHaveAttribute("href", "/notebook/12/practise");
});
