/**
 * The rehearse pages in the states they have: signed out, nothing pasted yet, and a list
 * of scripts with what has been rehearsed of each.
 */

import { render, screen } from "@testing-library/react";

import RehearsePage from "@/app/(app)/rehearse/page";
import PresentationDetailPage from "@/app/(app)/rehearse/[id]/page";
import {
  makePresentationPage,
  makePresentationSummary,
  makeSection,
  makeTake,
} from "@/test/fixtures";

jest.mock("@/lib/server-api", () => ({ serverRequestOrNull: jest.fn() }));

jest.mock("@/app/(app)/rehearse/[id]/DeletePresentationButton", () => ({
  DeletePresentationButton: ({ title }: { title: string }) => (
    <button type="button">{`Delete ${title}`}</button>
  ),
}));

jest.mock("next/navigation", () => ({
  notFound: () => {
    throw new Error("NEXT_NOT_FOUND");
  },
}));

import { serverRequestOrNull } from "@/lib/server-api";

const request = serverRequestOrNull as jest.MockedFunction<typeof serverRequestOrNull>;

beforeEach(() => request.mockReset());

function answerWith(body: unknown) {
  request.mockImplementation((() => Promise.resolve(body)) as typeof serverRequestOrNull);
}

test("a signed-out reader is asked to sign in and brought back here", async () => {
  answerWith(null);

  render(await RehearsePage());

  expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute(
    "href",
    "/login?next=/rehearse",
  );
});

test("nothing pasted yet says what to paste rather than showing an empty grid", async () => {
  answerWith({ items: [], total: 0, limit: 20, offset: 0 });

  render(await RehearsePage());

  expect(screen.getByText(/Paste a talk/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /New script/ })).toHaveAttribute(
    "href",
    "/rehearse/new",
  );
});

test("each script lists its sections, its takes and its length", async () => {
  answerWith({
    items: [
      makePresentationSummary(),
      makePresentationSummary({ id: 4, title: "All-hands", sections: 1, takes: 0, word_count: 90 }),
    ],
    total: 2,
    limit: 20,
    offset: 0,
  });

  render(await RehearsePage());

  expect(screen.getByText("2 sections · 5 takes · 60 words")).toBeInTheDocument();
  expect(screen.getByText("1 section · 0 takes · 90 words")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /Quarterly update/ })).toHaveAttribute(
    "href",
    "/rehearse/3",
  );
});

test("the script's own page lists its sections and says which have no takes", async () => {
  answerWith(makePresentationPage());

  render(await PresentationDetailPage({ params: Promise.resolve({ id: "3" }) }));

  expect(screen.getByRole("heading", { name: "Quarterly update", level: 1 })).toBeInTheDocument();
  expect(screen.getAllByText("No takes yet")).toHaveLength(2);
  expect(screen.getAllByRole("link", { name: "Rehearse" })[0]).toHaveAttribute(
    "href",
    "/rehearse/3/0",
  );
});

test("a section that has been rehearsed says how far the last take was from the script", async () => {
  answerWith(
    makePresentationPage({
      presentation: {
        ...makePresentationPage().presentation,
        sections: [
          makeSection({
            takes: 3,
            word_count: 7,
            latest: { ...makeTake({ missed: 2 }) },
          }),
        ],
      },
    }),
  );

  render(await PresentationDetailPage({ params: Promise.resolve({ id: "3" }) }));

  expect(
    screen.getByText("3 takes · last one missed or changed 2 of 7 words"),
  ).toBeInTheDocument();
});

test("what to rehearse next prints the measurement that chose it", async () => {
  answerWith(
    makePresentationPage({
      next_up: [
        {
          kind: "fidelity",
          title: "Section 1",
          reason: "12 of 26 words missed or changed in the last take",
          measured: 0.46,
          samples: 1,
          section_id: 1,
        },
        {
          kind: "sound",
          title: "the /TH/ sound",
          reason: "12 instances across 3 takes, mean score -8.2",
          measured: -8.2,
          samples: 12,
          section_id: null,
        },
      ],
    }),
  );

  render(await PresentationDetailPage({ params: Promise.resolve({ id: "3" }) }));

  expect(
    screen.getByText("12 of 26 words missed or changed in the last take"),
  ).toBeInTheDocument();
  expect(screen.getByText("12 instances across 3 takes, mean score -8.2")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /Furthest from the script/ })).toHaveAttribute(
    "href",
    "/rehearse/3/0",
  );
});
