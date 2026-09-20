/**
 * The rehearse pages in the states they have: signed out, nothing pasted yet, and a list
 * of scripts with what has been rehearsed of each.
 */

import { render, screen } from "@testing-library/react";

import RehearsePage from "@/app/(app)/rehearse/page";
import PresentationDetailPage from "@/app/(app)/rehearse/[id]/page";
import SectionPage from "@/app/(app)/rehearse/[id]/[idx]/page";
import {
  makePresentation,
  makePresentationPage,
  makePresentationSummary,
  makeSection,
  makeTake,
} from "@/test/fixtures";

jest.mock("@/lib/server-api", () => ({ serverRequestOrNull: jest.fn() }));

jest.mock("@/app/(app)/rehearse/[id]/[idx]/SectionRehearsal", () => ({
  SectionRehearsal: ({ sounds }: { sounds?: { name: string }[] }) => (
    <div>{`the recorder, with ${sounds?.length ?? 0} sounds`}</div>
  ),
}));

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

/** The section page asks for two things, so its answers go by path. */
function answerByPath(bodies: Record<string, unknown>) {
  request.mockImplementation(((path: string) =>
    Promise.resolve(path in bodies ? bodies[path] : null)) as typeof serverRequestOrNull);
}

function fourSections() {
  return makePresentation({
    sections: [0, 1, 2, 3].map((idx) =>
      makeSection({ id: idx + 1, idx, body: `Part ${idx + 1}.`, word_count: 2 }),
    ),
  });
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

test("a section in the middle of a script can be moved through in either direction", async () => {
  answerByPath({
    "/presentations/3": makePresentationPage({ presentation: fourSections() }),
    "/presentations/3/sections/1/takes": { items: [] },
  });

  render(await SectionPage({ params: Promise.resolve({ id: "3", idx: "1" }) }));

  expect(screen.getByRole("link", { name: "Previous section" })).toHaveAttribute(
    "href",
    "/rehearse/3/0",
  );
  expect(screen.getByRole("link", { name: "Next section" })).toHaveAttribute(
    "href",
    "/rehearse/3/2",
  );
});

test("the last section offers nothing after it", async () => {
  answerByPath({
    "/presentations/3": makePresentationPage({ presentation: fourSections() }),
    "/presentations/3/sections/3/takes": { items: [] },
  });

  render(await SectionPage({ params: Promise.resolve({ id: "3", idx: "3" }) }));

  expect(screen.getByRole("link", { name: "Previous section" })).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Next section" })).not.toBeInTheDocument();
});

test("the first section offers nothing before it", async () => {
  answerByPath({
    "/presentations/3": makePresentationPage({ presentation: fourSections() }),
    "/presentations/3/sections/0/takes": { items: [] },
  });

  render(await SectionPage({ params: Promise.resolve({ id: "3", idx: "0" }) }));

  expect(screen.getByRole("link", { name: "Next section" })).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Previous section" })).not.toBeInTheDocument();
});

test("the script's weakest sounds are named on it, in words and with a measurement", async () => {
  answerWith(
    makePresentationPage({
      sounds: [
        {
          phone: "IY",
          name: 'the vowel in "see"',
          instances: 15,
          takes: 4,
          mean_gop: -3.79,
          words: ["peels", "these"],
        },
      ],
      sounds_caveat: "Scored from your takes of this script.",
    }),
  );

  render(await PresentationDetailPage({ params: Promise.resolve({ id: "3" }) }));

  expect(screen.getByText('the vowel in "see"')).toBeInTheDocument();
  expect(screen.getByText("in your peels, these")).toBeInTheDocument();
  expect(screen.getByText("15 times across 4 takes, mean score -3.8")).toBeInTheDocument();
});

test("a sound is named where the take is, not only a page away", async () => {
  answerByPath({
    "/presentations/3": makePresentationPage({
      presentation: fourSections(),
      sounds: [
        {
          phone: "DH",
          name: 'the "th" in "this"',
          instances: 16,
          takes: 4,
          mean_gop: -3.43,
          words: ["the"],
        },
      ],
      sounds_caveat: "Scored from your takes of this script.",
    }),
    "/presentations/3/sections/0/takes": { items: [makeTake()] },
  });

  render(await SectionPage({ params: Promise.resolve({ id: "3", idx: "0" }) }));

  expect(screen.getByText("the recorder, with 1 sounds")).toBeInTheDocument();
});
