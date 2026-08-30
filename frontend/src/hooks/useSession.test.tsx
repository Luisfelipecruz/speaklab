/**
 * The conversation state, and the two moments it has to get right.
 *
 * **Reconciliation.** A bubble appears the instant recording stops and is replaced by
 * the real pair when the server answers. The thing worth asserting is not that the
 * bubble appears — it is that it never contains words, because the browser does not know
 * what was said and anything it wrote there would be a fabricated transcript.
 *
 * **A failure mid-turn.** `POST /sessions/{id}/turns` is atomic: on a 503 nothing was
 * written server-side, and the recording is still in memory here. So the recovery is a
 * retry that sends the same bytes — not an apology that makes somebody say it again.
 */

import { act, renderHook, waitFor } from "@testing-library/react";

import { ApiError } from "@/lib/api";
import { useSession } from "@/hooks/useSession";
import type { RecordedClip } from "@/hooks/useRecorder";
import { makeSession, makeTurn } from "@/test/fixtures";

jest.mock("@/lib/api", () => {
  const actual = jest.requireActual("@/lib/api");
  return {
    ...actual,
    postTurn: jest.fn(),
    getSession: jest.fn(),
    endSession: jest.fn(),
  };
});

// eslint-disable-next-line @typescript-eslint/no-require-imports
const api = require("@/lib/api") as {
  postTurn: jest.Mock;
  getSession: jest.Mock;
  endSession: jest.Mock;
};

const CLIP: RecordedClip = {
  blob: new Blob(["pretend audio"], { type: "audio/webm" }),
  mimeType: "audio/webm",
  durationMs: 4200,
  filename: "turn.webm",
};

function turnResponse() {
  return {
    session_id: 12,
    user_turn: makeTurn({ id: 2, idx: 1, role: "user", transcript: "I led the migration." }),
    reply_turn: makeTurn({ id: 3, idx: 2, role: "assistant", transcript: "Over what period?" }),
    speech: {
      status: "ok" as const,
      detail: null,
      voice: "en_US-lessac-medium",
      duration_ms: 2100,
      sample_rate: 22050,
      sentences: 1,
    },
    timing: {
      total_ms: 2353,
      asr_ms: 1146,
      generation_ms: 872,
      synthesis_ms: 235,
      reply_ms: 1132,
      model_load_ms: null,
      prompt_tokens: 1258,
      completion_tokens: 53,
    },
    low_confidence: false,
  };
}

beforeEach(() => jest.clearAllMocks());

test("a bubble appears while the turn is in flight and carries no invented words", async () => {
  let release: (value: ReturnType<typeof turnResponse>) => void = () => {};
  api.postTurn.mockReturnValue(new Promise((resolve) => (release = resolve)));

  const { result } = renderHook(() => useSession(12, makeSession()));

  let sending: Promise<void>;
  act(() => {
    sending = result.current.send(CLIP);
  });

  await waitFor(() => expect(result.current.phase).toBe("sending"));
  const pending = result.current.items.at(-1)!;
  expect(pending.kind).toBe("pending");
  expect(pending).not.toHaveProperty("turn");
  expect(pending.kind === "pending" && pending.durationMs).toBe(4200);

  await act(async () => {
    release(turnResponse());
    await sending!;
  });

  // The optimistic bubble is gone and both halves of the exchange are in its place.
  expect(result.current.items.map((item) => item.kind)).toEqual(["stored", "stored", "stored"]);
  expect(
    result.current.items.map((item) => (item.kind === "stored" ? item.turn.transcript : null)),
  ).toEqual([
    "Good morning. Thanks for coming in — shall we start with your last role?",
    "I led the migration.",
    "Over what period?",
  ]);
  expect(result.current.lastReplyTurnId).toBe(3);
  expect(result.current.lastTiming?.total_ms).toBe(2353);
});

test("only one request is made — the response already carries both turns", async () => {
  api.postTurn.mockResolvedValue(turnResponse());

  const { result } = renderHook(() => useSession(12, makeSession()));
  await act(async () => {
    await result.current.send(CLIP);
  });

  expect(api.postTurn).toHaveBeenCalledTimes(1);
  // Refetching the transcript here would be a second round trip to learn what the first
  // one already said.
  expect(api.getSession).not.toHaveBeenCalled();
});

test("a turn that fails offers to send the same recording again", async () => {
  api.postTurn.mockRejectedValueOnce(
    new ApiError("The conversation model is not responding. Your recording was not lost.", 503),
  );

  const { result } = renderHook(() => useSession(12, makeSession()));
  await act(async () => {
    await result.current.send(CLIP);
  });

  expect(result.current.error).toMatch(/not responding/);
  expect(result.current.canRetry).toBe(true);
  // Nothing half-written on screen: the endpoint is atomic and so is the transcript.
  expect(result.current.items).toHaveLength(1);

  api.postTurn.mockResolvedValueOnce(turnResponse());
  await act(async () => {
    await result.current.retry();
  });

  expect(api.postTurn).toHaveBeenCalledTimes(2);
  expect(api.postTurn.mock.calls[1][1]).toBe(CLIP.blob);
  expect(result.current.error).toBeNull();
  expect(result.current.items).toHaveLength(3);
});

test("an unreachable API is reported as unreachable, not as a model failure", async () => {
  api.postTurn.mockRejectedValue(new ApiError("Could not reach the API. Is the stack running?", 0));

  const { result } = renderHook(() => useSession(12, makeSession()));
  await act(async () => {
    await result.current.send(CLIP);
  });

  expect(result.current.error).toMatch(/Could not reach the API/);
  expect(result.current.canRetry).toBe(true);
});

test("a session ended elsewhere is reloaded rather than retried", async () => {
  // 409 means the session is no longer active. The same bytes cannot succeed, so
  // offering a retry would be an invitation to fail twice.
  api.postTurn.mockRejectedValue(new ApiError("This session is completed.", 409));
  api.getSession.mockResolvedValue(makeSession({ status: "completed" }));

  const { result } = renderHook(() => useSession(12, makeSession()));
  await act(async () => {
    await result.current.send(CLIP);
  });

  expect(result.current.canRetry).toBe(false);
  await waitFor(() => expect(api.getSession).toHaveBeenCalledWith(12));
});

test("a page with no server snapshot fetches the transcript itself", async () => {
  api.getSession.mockResolvedValue(makeSession());

  const { result } = renderHook(() => useSession(12, null));

  expect(result.current.phase).toBe("loading");
  await waitFor(() => expect(result.current.phase).toBe("ready"));
  expect(result.current.items).toHaveLength(1);
});

test("a deleted session is a state, not an error banner over an empty page", async () => {
  api.getSession.mockRejectedValue(new ApiError("No such session", 404));

  const { result } = renderHook(() => useSession(99, null));

  await waitFor(() => expect(result.current.phase).toBe("gone"));
});

test("ending a session stores the report it comes back with", async () => {
  const ended = makeSession({ status: "completed", ended_at: "2026-08-30T10:12:00Z" });
  api.endSession.mockResolvedValue(ended);

  const { result } = renderHook(() => useSession(12, makeSession()));
  await act(async () => {
    await result.current.end();
  });

  expect(result.current.ended).toBe(true);
  expect(result.current.session?.status).toBe("completed");
});
