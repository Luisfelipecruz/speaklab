/**
 * The answers pages in the states they have: signed out, nothing answered, answered — and
 * one question, with its earlier answers and an answer opened to be said again.
 */

import { render, screen, within } from "@testing-library/react";

import AnswerPromptPage from "@/app/(app)/answers/[slug]/page";
import AnswersPage from "@/app/(app)/answers/page";
import type { AnswersPage as AnswersPageShape } from "@/lib/api";
import { makeAnswer, makeAnswersPage, makePrompt } from "@/test/fixtures";

jest.mock("@/lib/server-api", () => ({ serverRequestOrNull: jest.fn() }));

jest.mock("@/components/AnswerRecorder", () => ({
  AnswerRecorder: ({ basis }: { basis: { id: number } | null }) => (
    <div data-testid="recorder">{basis ? `saying ${basis.id} again` : "new answer"}</div>
  ),
}));

jest.mock("next/navigation", () => ({
  notFound: () => {
    throw new Error("NEXT_NOT_FOUND");
  },
}));

import { serverRequestOrNull } from "@/lib/server-api";

const request = serverRequestOrNull as jest.MockedFunction<typeof serverRequestOrNull>;

function answer(page: AnswersPageShape | null) {
  request.mockImplementation(((path: string) => {
    if (path.startsWith("/answers")) return Promise.resolve(page);
    throw new Error(`unexpected request: ${path}`);
  }) as typeof serverRequestOrNull);
}

beforeEach(() => request.mockReset());

test("a signed-out reader is asked to sign in and brought back here", async () => {
  answer(null);

  render(await AnswersPage());

  expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login?next=/answers");
});

test("nothing answered yet lists the questions by kind and draws nothing", async () => {
  answer(
    makeAnswersPage({
      answers: [],
      answered: 0,
      prompts: makeAnswersPage().prompts.map((prompt) => ({ ...prompt, answers: 0 })),
    }),
  );

  render(await AnswersPage());

  expect(screen.getByRole("heading", { name: "Explain what happened" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Recommend something" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /Explain a failed release/ })).toHaveAttribute(
    "href",
    "/answers/explain-a-failed-release",
  );
  expect(screen.getByText(/Nothing answered yet/)).toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "Your latest answers" })).not.toBeInTheDocument();
});

test("answers draw the history, say why a series is not drawn, and list the latest", async () => {
  answer(makeAnswersPage());

  render(await AnswersPage());

  expect(screen.getByText("One point per answer, whichever prompt it answered.")).toBeInTheDocument();
  expect(screen.getByText("fillers")).toBeInTheDocument();
  expect(screen.getByText("words said twice: No answer yet has 50 words in it.")).toBeInTheDocument();
  const latest = screen.getByRole("heading", { name: "Your latest answers" }).parentElement!;
  expect(within(latest).getByText(/18 words in 0:09/)).toBeInTheDocument();
  expect(screen.getByText("answered once")).toBeInTheDocument();
});

const oneQuestion = makeAnswersPage({
  prompt: makePrompt(),
  answers: [makeAnswer({ id: 12, again_of: 7 }), makeAnswer({ id: 7 })],
});

test("one question shows the prompt, the recorder and the earlier answers", async () => {
  answer(oneQuestion);

  render(
    await AnswerPromptPage({
      params: Promise.resolve({ slug: "explain-a-failed-release" }),
      searchParams: Promise.resolve({}),
    }),
  );

  expect(screen.getByRole("heading", { name: "Explain a failed release" })).toBeInTheDocument();
  expect(screen.getByText(/up to 1:30/)).toBeInTheDocument();
  expect(screen.getByTestId("recorder")).toHaveTextContent("new answer");
  expect(within(screen.getByTestId("earlier-12")).getByText("said again")).toBeInTheDocument();
  expect(
    within(screen.getByTestId("earlier-7")).getByRole("link", { name: "Say this one again" }),
  ).toHaveAttribute("href", "/answers/explain-a-failed-release?again=7");
  expect(request).toHaveBeenCalledWith("/answers?prompt=explain-a-failed-release");
});

test("an answer opened to be said again is handed to the recorder", async () => {
  answer(oneQuestion);

  render(
    await AnswerPromptPage({
      params: Promise.resolve({ slug: "explain-a-failed-release" }),
      searchParams: Promise.resolve({ again: "7" }),
    }),
  );

  expect(screen.getByTestId("recorder")).toHaveTextContent("saying 7 again");
});

test("a question that is not there says so", async () => {
  answer(null);

  render(
    await AnswerPromptPage({
      params: Promise.resolve({ slug: "no-such-question" }),
      searchParams: Promise.resolve({}),
    }),
  );

  expect(screen.getByText(/That question is not available/)).toBeInTheDocument();
});
