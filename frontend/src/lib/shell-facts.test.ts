import { makeProgress } from "@/test/fixtures";

jest.mock("@/lib/server-api", () => ({
  serverRequestOrNull: jest.fn(),
}));

import { serverRequestOrNull } from "@/lib/server-api";
import { loadShellFacts } from "@/lib/shell-facts";

const request = serverRequestOrNull as jest.Mock;

beforeEach(() => request.mockReset());

test("the History badge counts the conversations the list holds, not the window's sessions", async () => {
  // Four conversations on the account, one of them inside the trend window. The list
  // says "All 4 conversations"; a badge on the link to it says the same.
  request.mockResolvedValue(
    makeProgress({
      totals: {
        sessions: 1,
        turns: 4,
        words: 90,
        attempts: 3,
        phones: 200,
        periods: 1,
        conversations: 4,
      },
    }),
  );

  const facts = await loadShellFacts();

  expect(facts).toEqual({ conversations: 4, attempts: 3, periods: 1, stale: false });
});

test("a reader nobody has identified gets no facts", async () => {
  request.mockResolvedValue(null);

  expect(await loadShellFacts()).toBeNull();
});

test("an API that cannot be reached leaves the rail without counts rather than without a page", async () => {
  request.mockRejectedValue(new Error("Could not reach the API"));

  expect(await loadShellFacts()).toBeNull();
});
