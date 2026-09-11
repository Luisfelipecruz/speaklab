/**
 * The grammar page, in the three states it has: signed out, nothing analysed, and
 * corrections to show.
 *
 * **The empty states are the ones worth testing.** An account with nothing analysed is
 * where every account starts, and an account whose turns were analysed and flagged
 * nothing is not an account with no mistakes — the page must say both plainly.
 */

import { render, screen } from "@testing-library/react";

import GrammarPage from "@/app/(app)/grammar/page";
import type { GrammarPage as GrammarPageShape } from "@/lib/api";
import { makeGrammarPage } from "@/test/fixtures";

jest.mock("@/lib/server-api", () => ({
  serverRequestOrNull: jest.fn(),
}));

import { serverRequestOrNull } from "@/lib/server-api";

const request = serverRequestOrNull as jest.MockedFunction<typeof serverRequestOrNull>;

function answer(page: GrammarPageShape | null) {
  request.mockImplementation(((path: string) => {
    if (path.startsWith("/grammar")) return Promise.resolve(page);
    throw new Error(`unexpected request: ${path}`);
  }) as typeof serverRequestOrNull);
}

beforeEach(() => request.mockReset());

test("a signed-out reader is asked to sign in and brought back here", async () => {
  answer(null);

  render(await GrammarPage());

  expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute(
    "href",
    "/login?next=/grammar",
  );
});

test("an account with nothing analysed is told where corrections come from", async () => {
  answer(
    makeGrammarPage({
      totals: { sessions: 0, turns: 0, words: 0, corrections: 0, counted: 0 },
      categories: [],
      forms: [],
      caveat: null,
    }),
  );

  render(await GrammarPage());

  expect(screen.getByText(/Nothing you have said has been analysed yet/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Choose a scenario" })).toHaveAttribute(
    "href",
    "/scenarios",
  );
  expect(screen.queryByText("Your corrections, by kind")).not.toBeInTheDocument();
});

test("analysed speech with nothing flagged is not called mistake-free", async () => {
  answer(
    makeGrammarPage({
      totals: { sessions: 1, turns: 3, words: 120, corrections: 0, counted: 0 },
      categories: [],
      caveat: null,
    }),
  );

  render(await GrammarPage());

  expect(
    screen.getByText(/Nothing was flagged in 120 words. That is not the same as no mistakes/),
  ).toBeInTheDocument();
});

test("corrections come with the caveat, the form to practise and the forms", async () => {
  answer(makeGrammarPage());

  render(await GrammarPage());

  expect(screen.getByTestId("grammar-caveat")).toHaveTextContent(/none|language model/);
  expect(screen.getByText("No form to practise named yet")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Your corrections, by kind" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "The verb forms you used" })).toBeInTheDocument();
  expect(screen.getByText("needed 1, never said")).toBeInTheDocument();
  expect(screen.getByText(/1 correction in 272 words, across 7 turns in 2 conversations/)).toBeInTheDocument();
});
