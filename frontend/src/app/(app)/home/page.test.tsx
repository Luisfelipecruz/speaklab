/**
 * Where signing in lands, in the three states it actually has.
 *
 * **The empty one is the one worth testing.** An account that has never practised is the
 * state every account starts in, it is the state a demo is given to somebody in, and it
 * is the state that renders as nothing at all if the page is written for the happy case
 * and left there. Three empty cards say "this is broken"; a page that says what to do
 * says "you have not started yet".
 *
 * The page is an async server component, so it is awaited and its result rendered — the
 * fetches are the only thing it does that a test environment cannot, and those are the
 * seam that is replaced.
 */

import { render, screen } from "@testing-library/react";

import HomePage from "@/app/(app)/home/page";
import { makeProgress, makeRecommendations } from "@/test/fixtures";
import type { Progress, Recommendations, SessionPage } from "@/lib/api";

jest.mock("@/lib/server-api", () => ({
  serverRequestOrNull: jest.fn(),
}));

import { serverRequestOrNull } from "@/lib/server-api";

const request = serverRequestOrNull as jest.MockedFunction<typeof serverRequestOrNull>;

/** Answer each of the page's three requests by path, the way the API would. */
function answer(replies: {
  progress?: Progress | null;
  recommendations?: Recommendations | null;
  sessions?: SessionPage | null;
}) {
  request.mockImplementation(((path: string) => {
    if (path.startsWith("/progress/recommendations")) {
      return Promise.resolve(replies.recommendations ?? null);
    }
    if (path.startsWith("/progress")) return Promise.resolve(replies.progress ?? null);
    if (path.startsWith("/sessions")) return Promise.resolve(replies.sessions ?? null);
    throw new Error(`unexpected request: ${path}`);
  }) as typeof serverRequestOrNull);
}

const NOTHING: Progress = makeProgress({
  totals: { sessions: 0, turns: 0, words: 0, attempts: 0, phones: 0, periods: 0 },
});

beforeEach(() => {
  request.mockReset();
});

test("an account that has never practised is told what to do, not shown empty charts", async () => {
  answer({ progress: NOTHING, recommendations: makeRecommendations({ confidence: "none" }) });

  render(await HomePage());

  expect(screen.getByRole("heading", { name: "Start here" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Choose a scenario" })).toHaveAttribute(
    "href",
    "/scenarios",
  );
  expect(screen.getByRole("link", { name: "Choose a passage" })).toHaveAttribute(
    "href",
    "/read",
  );
  // Both of the things that produce something to measure, and neither of them a chart.
  expect(screen.queryByText("What to practise next")).not.toBeInTheDocument();
});

test("a reader nobody has identified is offered the way in", async () => {
  answer({ progress: null, recommendations: null, sessions: null });

  render(await HomePage());

  expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute(
    "href",
    "/login?next=/home",
  );
});

test("somebody who has practised gets their counts and what to do next", async () => {
  answer({
    progress: makeProgress({
      totals: { sessions: 4, turns: 31, words: 272, attempts: 2, phones: 410, periods: 3 },
    }),
    recommendations: makeRecommendations(),
    sessions: {
      items: [
        {
          id: 12,
          scenario_slug: "job-interview-backend",
          scenario_title: "Backend interview",
          mode: "conversation",
          status: "ended",
          started_at: "2026-09-01T18:20:00Z",
          ended_at: "2026-09-01T18:34:00Z",
          turn_count: 9,
        },
      ],
      total: 4,
      limit: 3,
      offset: 0,
    },
  });

  render(await HomePage());

  expect(screen.getByRole("heading", { name: "Your practice" })).toBeInTheDocument();
  expect(screen.getByText("272")).toBeInTheDocument();
  expect(screen.getByText("What to practise next")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Backend interview" })).toHaveAttribute(
    "href",
    "/sessions/12",
  );
  expect(screen.getByRole("link", { name: "All 4 conversations" })).toBeInTheDocument();
});

test("a history that has not loaded does not claim the account is empty", async () => {
  // Readings are scored without a conversation, so counts above can move while this
  // stays empty — and "nothing here" must not read as "your history is gone".
  answer({
    progress: makeProgress({
      totals: { sessions: 0, turns: 0, words: 0, attempts: 2, phones: 410, periods: 1 },
    }),
    recommendations: makeRecommendations(),
    sessions: { items: [], total: 0, limit: 3, offset: 0 },
  });

  render(await HomePage());

  expect(screen.getByText(/A reading is scored without a conversation/)).toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "Start here" })).not.toBeInTheDocument();
});

test("figures known to be behind the practice say so, with the way to rebuild them", async () => {
  answer({
    progress: makeProgress({
      stale: true,
      totals: { sessions: 1, turns: 8, words: 64, attempts: 0, phones: 0, periods: 1 },
    }),
    recommendations: makeRecommendations(),
    sessions: { items: [], total: 0, limit: 3, offset: 0 },
  });

  render(await HomePage());

  expect(
    screen.getByRole("link", { name: "Rebuild them on the progress page." }),
  ).toHaveAttribute("href", "/progress");
});
