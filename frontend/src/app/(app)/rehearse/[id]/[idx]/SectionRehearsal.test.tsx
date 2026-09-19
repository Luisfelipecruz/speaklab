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

test("a target is saved as it is typed and the recording stops at twice it", async () => {
  api.setSectionTarget.mockResolvedValue(makeSection({ target_seconds: 40 }));
  recorder.state = "idle";
  render(<SectionRehearsal presentationId={3} section={makeSection()} earlier={[]} />);

  await userEvent.setup().type(screen.getByLabelText(/How long should it take/), "40");

  await waitFor(() => expect(api.setSectionTarget).toHaveBeenLastCalledWith(3, 0, 40));
  expect(screen.getByText("Press to start, press again to stop. It stops by itself after 1:20.")).toBeInTheDocument();
});
