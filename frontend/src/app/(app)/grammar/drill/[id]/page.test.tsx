/**
 * The drill page, in the states it has: signed out or not yours, a correction that cannot
 * be said, and one that can.
 *
 * **Skipping is tested as a feature.** A wrong correction practised aloud practises the
 * mistake, so the way on to the next one must be on the page before anything is recorded.
 */

import { render, screen } from "@testing-library/react";

import DrillPage from "@/app/(app)/grammar/drill/[id]/page";
import type { Drill } from "@/lib/api";
import { makeDrill } from "@/test/fixtures";

jest.mock("@/lib/server-api", () => ({ serverRequestOrNull: jest.fn() }));
jest.mock("@/components/DrillRecorder", () => ({
  DrillRecorder: () => <div data-testid="recorder" />,
}));
jest.mock("next/navigation", () => ({
  notFound: () => {
    throw new Error("NEXT_NOT_FOUND");
  },
}));

import { serverRequestOrNull } from "@/lib/server-api";

const request = serverRequestOrNull as jest.MockedFunction<typeof serverRequestOrNull>;

function answer(drill: Drill | null) {
  request.mockImplementation(((path: string) => {
    if (path === "/corrections/41/drill") return Promise.resolve(drill);
    throw new Error(`unexpected request: ${path}`);
  }) as typeof serverRequestOrNull);
}

async function open(id = "41") {
  render(await DrillPage({ params: Promise.resolve({ id }) }));
}

beforeEach(() => request.mockReset());

test("a correction that is not available asks to sign in and comes back here", async () => {
  answer(null);

  await open();

  expect(screen.getByRole("link", { name: "sign in" })).toHaveAttribute(
    "href",
    "/login?next=/grammar/drill/41",
  );
});

test("an id that is not a number is not found", async () => {
  await expect(open("abc")).rejects.toThrow("NEXT_NOT_FOUND");
});

test("the correction comes first, then the sentence to say, the button and the caveat", async () => {
  answer(makeDrill());

  await open();

  expect(screen.getByRole("heading", { name: "Say it again" })).toBeInTheDocument();
  expect(screen.getByTestId("drill-said")).toHaveTextContent("Yesterday I complete the user story.");
  expect(screen.getByTestId("drill-say")).toHaveTextContent("Yesterday I completed the user story.");
  expect(screen.getByTestId("recorder")).toBeInTheDocument();
  expect(screen.getByTestId("drill-caveat")).toHaveTextContent(/fluent English/);
});

test("the next correction of the kind is one step away, before anything is recorded", async () => {
  answer(makeDrill());

  await open();

  expect(
    screen.getByRole("link", { name: "Skip to the next verb tense correction" }),
  ).toHaveAttribute("href", "/grammar/drill/44");
  expect(screen.getByRole("link", { name: "Your corrections" })).toHaveAttribute("href", "/grammar");
});

test("after the last correction of the kind there is nowhere to skip to, and it says so", async () => {
  answer(makeDrill({ next_id: null }));

  await open();

  expect(screen.queryByRole("link", { name: /Skip to the next/ })).not.toBeInTheDocument();
  expect(screen.getByText("That is the last verb tense correction to say again.")).toBeInTheDocument();
});

test("a correction that cannot be said says why, and offers no button", async () => {
  answer(
    makeDrill({
      pieces: [],
      unavailable: "This correction changes only capitals or punctuation.",
    }),
  );

  await open();

  expect(screen.getByText("This correction changes only capitals or punctuation.")).toBeInTheDocument();
  expect(screen.queryByTestId("recorder")).not.toBeInTheDocument();
});
