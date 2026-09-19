/**
 * One section: recording a take, following it while its sounds are scored, and what each
 * state says.
 *
 * The microphone is replaced, as everywhere else: no test environment has one. What is
 * tested is the round trip to this section, the poll that ends when the sounds arrive, the
 * two states where there are no sounds and why, and the line an account that keeps no
 * recordings is shown before it records rather than after.
 */

import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { SectionRehearsal } from "@/app/(app)/rehearse/[id]/[idx]/SectionRehearsal";
import { makeProfile, makeSection, makeTake } from "@/test/fixtures";

const clip = {
  blob: new Blob(["audio"]),
  mimeType: "audio/webm",
  durationMs: 40_000,
  filename: "turn.webm",
};

const recorder = {
  state: "recording" as string,
  error: null,
  mimeType: "audio/webm",
  analyser: null,
  elapsedMs: 40_000,
  start: jest.fn(),
  stop: jest.fn(async () => {
    recorder.state = "idle";
    return clip;
  }),
  cancel: jest.fn(),
  clearError: jest.fn(),
};

jest.mock("@/hooks/useRecorder", () => ({ useRecorder: () => recorder }));

let profile: ReturnType<typeof makeProfile> | null = makeProfile();
jest.mock("@/hooks/useAuth", () => ({
  useAuth: () => ({ user: profile, status: "authenticated" }),
}));

jest.mock("@/lib/api", () => {
  const actual = jest.requireActual("@/lib/api");
  return { ...actual, postTake: jest.fn(), getTake: jest.fn(), setSectionTarget: jest.fn() };
});

// eslint-disable-next-line @typescript-eslint/no-require-imports
const api = require("@/lib/api") as {
  postTake: jest.Mock;
  getTake: jest.Mock;
  setSectionTarget: jest.Mock;
};

beforeEach(() => {
  jest.clearAllMocks();
  recorder.state = "recording";
  recorder.elapsedMs = 40_000;
  profile = makeProfile();
});

test("a stopped recording goes to this section and comes back compared", async () => {
  api.postTake.mockResolvedValue(makeTake({ pronunciation: "ok" }));
  render(<SectionRehearsal presentationId={3} section={makeSection()} earlier={[]} />);

  await userEvent.setup().click(screen.getByRole("button", { name: /Stop/ }));

  await waitFor(() =>
    expect(api.postTake).toHaveBeenCalledWith(3, 0, clip.blob, "turn.webm"),
  );
  expect(await screen.findByRole("heading", { name: "What was heard" })).toBeInTheDocument();
  expect(screen.getByText("of 7 words missed or changed")).toBeInTheDocument();
});

test("a take still being scored says so, and stops saying it when the sounds arrive", async () => {
  jest.useFakeTimers();
  try {
    api.postTake.mockResolvedValue(makeTake({ pronunciation: "pending", phonemes: [] }));
    api.getTake.mockResolvedValue(
      makeTake({
        pronunciation: "ok",
        phonemes: [
          {
            word: "good",
            word_idx: 0,
            phone_idx: 0,
            canonical_phone: "G",
            recognized_phone: "k",
            start_ms: 0,
            end_ms: 80,
            gop: -7.4,
            posterior: 0.1,
          },
        ],
      }),
    );

    render(<SectionRehearsal presentationId={3} section={makeSection()} earlier={[]} />);
    const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
    await user.click(screen.getByRole("button", { name: /Stop/ }));

    expect(await screen.findByText("Scoring the sounds…")).toBeInTheDocument();

    // Inside `act`, because the poll's answer sets state from a timer rather than
    // from anything the test did.
    await act(async () => {
      await jest.advanceTimersByTimeAsync(1600);
    });

    await waitFor(() => expect(api.getTake).toHaveBeenCalledWith(7));
    await waitFor(() => expect(screen.queryByText("Scoring the sounds…")).not.toBeInTheDocument());
  } finally {
    jest.useRealTimers();
  }
});

test("a section whose words cannot be turned into sounds says which, before recording", () => {
  render(
    <SectionRehearsal
      presentationId={3}
      section={makeSection({ scorable: false, unscorable_words: ["12%", "2026"] })}
      earlier={[]}
    />,
  );

  expect(screen.getByText("12%, 2026")).toBeInTheDocument();
  expect(screen.getByText(/makes the sounds countable too/)).toBeInTheDocument();
});

test("an account that keeps no recordings is told before it records, not after", () => {
  profile = makeProfile({ retain_audio: false });

  render(<SectionRehearsal presentationId={3} section={makeSection()} earlier={[]} />);

  expect(screen.getByText(/the recording discarded/)).toBeInTheDocument();
});

test("an account that keeps recordings is not told anything about it", () => {
  render(<SectionRehearsal presentationId={3} section={makeSection()} earlier={[]} />);

  expect(screen.queryByText(/the recording discarded/)).not.toBeInTheDocument();
});

test("earlier takes are listed newest first, each with what it was worth", () => {
  render(
    <SectionRehearsal
      presentationId={3}
      section={makeSection({ takes: 2 })}
      earlier={[
        makeTake({ id: 9, created_at: "2026-09-20T10:05:00Z", missed: 1 }),
        makeTake({ id: 8, created_at: "2026-09-20T09:40:00Z", missed: 4 }),
      ]}
    />,
  );

  const rows = screen.getAllByRole("row").slice(1);
  expect(rows[0]).toHaveTextContent("10:05");
  expect(rows[0]).toHaveTextContent("1 of 7");
  expect(rows[1]).toHaveTextContent("09:40");
  expect(rows[1]).toHaveTextContent("4 of 7");
});

test("a finished take offers the next section rather than ending there", async () => {
  render(
    <SectionRehearsal
      presentationId={3}
      section={makeSection()}
      earlier={[makeTake()]}
      nextIdx={2}
    />,
  );

  expect(screen.getByRole("link", { name: /Rehearse the next section/ })).toHaveAttribute(
    "href",
    "/rehearse/3/2",
  );
});

test("the last section's take offers the whole script instead", async () => {
  render(
    <SectionRehearsal
      presentationId={3}
      section={makeSection()}
      earlier={[makeTake()]}
      nextIdx={null}
    />,
  );

  expect(screen.getByRole("link", { name: /Back to the whole script/ })).toHaveAttribute(
    "href",
    "/rehearse/3",
  );
  expect(
    screen.queryByRole("link", { name: /Rehearse the next section/ }),
  ).not.toBeInTheDocument();
});

test("nothing to go on to is offered before there is a take", () => {
  render(<SectionRehearsal presentationId={3} section={makeSection()} earlier={[]} nextIdx={2} />);

  expect(
    screen.queryByRole("link", { name: /Rehearse the next section/ }),
  ).not.toBeInTheDocument();
});

test("a target is saved as it is typed and the recording stops at twice it", async () => {
  api.setSectionTarget.mockResolvedValue(makeSection({ target_seconds: 40 }));
  recorder.state = "idle";
  render(<SectionRehearsal presentationId={3} section={makeSection()} earlier={[]} />);

  await userEvent.setup().type(screen.getByLabelText(/How long should it take/), "40");

  await waitFor(() => expect(api.setSectionTarget).toHaveBeenLastCalledWith(3, 0, 40));
  expect(screen.getByText("Press to start, press again to stop. It stops by itself after 1:20.")).toBeInTheDocument();
});

test("a take with no target says what the duration is rather than calling it long", () => {
  render(
    <SectionRehearsal
      presentationId={3}
      section={makeSection()}
      earlier={[makeTake({ target_seconds: null, pace: null })]}
    />,
  );

  expect(screen.getByText("how long it took")).toBeInTheDocument();
  expect(screen.queryByText("long")).not.toBeInTheDocument();
});

test("each measure is shown beside the speaker's own previous take", () => {
  render(
    <SectionRehearsal
      presentationId={3}
      section={makeSection({ takes: 2 })}
      earlier={[
        makeTake({ id: 9, missed: 2, speech_rate_wpm: 85, duration_ms: 30_000, fillers: 1 }),
        makeTake({ id: 8, missed: 5, speech_rate_wpm: 91, duration_ms: 25_000, fillers: 3 }),
      ]}
    />,
  );

  expect(screen.getByText("was 5 last take")).toBeInTheDocument();
  expect(screen.getByText("was 91 last take")).toBeInTheDocument();
  expect(screen.getByText("was 0:25 last take")).toBeInTheDocument();
  expect(screen.getByText("was 3 last take")).toBeInTheDocument();
});

test("the first take of a section is compared with nothing", () => {
  render(
    <SectionRehearsal presentationId={3} section={makeSection()} earlier={[makeTake()]} />,
  );

  expect(screen.queryByText(/last take/)).not.toBeInTheDocument();
});

test("a target can be taken from the take itself, and is not offered once one is set", async () => {
  api.setSectionTarget.mockResolvedValue(makeSection({ target_seconds: 42 }));
  render(
    <SectionRehearsal
      presentationId={3}
      section={makeSection()}
      earlier={[makeTake({ duration_ms: 42_000, target_seconds: null, pace: null })]}
    />,
  );

  await userEvent.setup().click(
    screen.getByRole("button", { name: /Set this section.s target to 0:42/ }),
  );

  await waitFor(() => expect(api.setSectionTarget).toHaveBeenLastCalledWith(3, 0, 42));
});

test("a section that already has a target is not asked to set one again", () => {
  render(
    <SectionRehearsal
      presentationId={3}
      section={makeSection({ target_seconds: 40 })}
      earlier={[makeTake({ target_seconds: 40, pace: "on" })]}
    />,
  );

  expect(screen.queryByRole("button", { name: /Set this section's target/ })).not.toBeInTheDocument();
});

test("a take says in one sentence what it was, before any of the tiles", () => {
  render(
    <SectionRehearsal
      presentationId={3}
      section={makeSection({ takes: 2 })}
      earlier={[
        makeTake({ id: 9, wer: 0.1, speech_rate_wpm: 85 }),
        makeTake({ id: 8, wer: 0.3, speech_rate_wpm: 91 }),
      ]}
    />,
  );

  expect(
    screen.getByText(
      "Closest yet to your script; most of the differences are other words; " +
        "slower than your last take by 6 words a minute.",
    ),
  ).toBeInTheDocument();
});

test("what is not measured is said, rather than left as silence", () => {
  render(
    <SectionRehearsal presentationId={3} section={makeSection()} earlier={[makeTake()]} />,
  );

  expect(screen.getByText(/Tone, intonation and stress are not measured here/)).toBeInTheDocument();
});
