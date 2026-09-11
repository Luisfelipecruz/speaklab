"use client";

/**
 * One conversation, as the screen sees it.
 *
 * It owns three things the transcript cannot render without: the stored turns, the one
 * turn that is currently in flight, and the clip belonging to a turn that failed.
 *
 * **The optimistic bubble is not decoration.** `POST /sessions/{id}/turns` runs a
 * recogniser, a language model and a voice inside one request — measured at 2353 ms
 * median on a quiet machine and over 6 s on a busy one — and three
 * seconds of an unchanged screen after you stop speaking reads as a broken button. So a
 * bubble appears the moment recording stops, saying it is being transcribed, and is
 * replaced by the real pair when the server answers. It never shows invented text: the
 * browser does not know what was said, and writing a guess there would be the interface
 * fabricating a transcript.
 *
 * **A failed turn keeps its recording.** The endpoint is atomic — on a 503 nothing was
 * written and there is no half-turn on the server — and the blob is still in memory
 * here, so the honest recovery is a retry button that sends the same bytes rather than
 * an apology that makes somebody say it all again. `api/routers/turns.py` says this in
 * as many words; this is the half that makes it true.
 *
 * **An unfinished report is finished by ending the session again.** Ending is idempotent:
 * on an ended session whose report was written before all its turns were analysed, it
 * waits for them and rebuilds the counted sections, keeping the written summary.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import {
  ApiError,
  endSession as postEnd,
  getSession,
  postTurn,
  type SessionDetail,
  type SessionReportShape,
  type Speech,
  type Turn,
  type TurnTiming,
} from "@/lib/api";
import type { RecordedClip } from "@/hooks/useRecorder";

/** A turn on the screen: either stored, or the one being transcribed right now. */
export type TranscriptItem =
  | { kind: "stored"; turn: Turn }
  | { kind: "pending"; localId: string; durationMs: number };

export type SessionPhase = "loading" | "ready" | "sending" | "ending" | "finishing" | "gone";

/**
 * Whether a stored report was written before its session's analysis had finished — the
 * same test the server applies before it rebuilds one. A report with no analysis at all
 * predates the analysers, and rebuilding it adds what they found.
 */
export function reportIsIncomplete(report: SessionReportShape | null | undefined): boolean {
  if (!report) return false;
  return !report.analysis || !report.analysis.complete;
}

export interface UseSession {
  session: SessionDetail | null;
  items: TranscriptItem[];
  phase: SessionPhase;
  /** The last failure, in words. Cleared when a retry starts. */
  error: string | null;
  /** True when `error` came with a recording that can be sent again unchanged. */
  canRetry: boolean;
  /** Timing and voice status for the most recent completed turn, or null. */
  lastTiming: TurnTiming | null;
  lastSpeech: Speech | null;
  /**
   * The reply that has just arrived, by turn id, or null on a freshly loaded page.
   * It is what decides which bubble speaks on its own: "the last turn" would be the
   * wrong rule, because after a reload the last turn is an old reply and a transcript
   * that starts talking when you open it is one nobody opens twice.
   */
  lastReplyTurnId: number | null;
  /** True once the session is completed; the report is on `session.report`. */
  ended: boolean;
  send: (clip: RecordedClip) => Promise<void>;
  retry: () => Promise<void>;
  end: () => Promise<void>;
  /** Rebuild an ended session's unfinished report with the turns it was written without. */
  finish: () => Promise<void>;
  reload: () => Promise<void>;
}

export function useSession(
  sessionId: number,
  initial: SessionDetail | null = null,
): UseSession {
  const [session, setSession] = useState<SessionDetail | null>(initial);
  const [phase, setPhase] = useState<SessionPhase>(initial ? "ready" : "loading");
  const [pending, setPending] = useState<TranscriptItem | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastTiming, setLastTiming] = useState<TurnTiming | null>(null);
  const [lastSpeech, setLastSpeech] = useState<Speech | null>(null);
  const [lastReplyTurnId, setLastReplyTurnId] = useState<number | null>(null);

  // The clip belonging to the failed turn. A ref rather than state because nothing
  // renders it — only `canRetry` is derived from whether one is held — and re-rendering
  // the transcript because a Blob changed identity is work for nothing.
  const unsentRef = useRef<RecordedClip | null>(null);
  const [canRetry, setCanRetry] = useState(false);

  const reload = useCallback(async () => {
    try {
      setSession(await getSession(sessionId));
      setPhase("ready");
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 404) {
        setPhase("gone");
        setError("This conversation no longer exists.");
        return;
      }
      setPhase("ready");
      setError(cause instanceof ApiError ? cause.message : "Could not load this conversation.");
    }
  }, [sessionId]);

  useEffect(() => {
    if (initial) return;
    void reload();
    // `initial` is the server-rendered snapshot and never changes for a mounted page;
    // depending on it would refetch on every render that produced a new object.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reload]);

  const deliver = useCallback(
    async (clip: RecordedClip) => {
      const localId = `pending-${Date.now()}`;
      setError(null);
      setCanRetry(false);
      setPending({ kind: "pending", localId, durationMs: clip.durationMs });
      setPhase("sending");

      try {
        const response = await postTurn(sessionId, clip.blob, clip.filename);

        // Append rather than refetch. The response carries both halves of the exchange
        // — that is why it returns both — and a GET here would be a second round trip
        // to learn what the first one already said.
        setSession((current) =>
          current
            ? {
                ...current,
                turns: [...current.turns, response.user_turn, response.reply_turn],
                turn_count: current.turn_count + 2,
              }
            : current,
        );
        setLastTiming(response.timing);
        setLastSpeech(response.speech);
        setLastReplyTurnId(response.reply_turn.id);
        unsentRef.current = null;
      } catch (cause) {
        const failure =
          cause instanceof ApiError ? cause : new ApiError("Something went wrong", 500);

        // 409 means the session is no longer active — ended in another tab, most
        // likely. Retrying the same bytes cannot help, so it is not offered.
        const retryable = failure.status !== 409 && failure.status !== 404;
        unsentRef.current = retryable ? clip : null;
        setCanRetry(retryable);
        setError(failure.message);

        if (failure.status === 409 || failure.status === 404) void reload();
      } finally {
        setPending(null);
        setPhase("ready");
      }
    },
    [sessionId, reload],
  );

  const send = useCallback((clip: RecordedClip) => deliver(clip), [deliver]);

  const retry = useCallback(async () => {
    const clip = unsentRef.current;
    if (!clip) return;
    await deliver(clip);
  }, [deliver]);

  const end = useCallback(async () => {
    setError(null);
    setPhase("ending");
    try {
      setSession(await postEnd(sessionId));
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not end this conversation.");
    } finally {
      setPhase((current) => (current === "ending" ? "ready" : current));
    }
  }, [sessionId]);

  const finish = useCallback(async () => {
    setError(null);
    setPhase("finishing");
    try {
      setSession(await postEnd(sessionId));
    } catch (cause) {
      setError(
        cause instanceof ApiError
          ? `Could not finish the report: ${cause.message}`
          : "Could not finish the report.",
      );
    } finally {
      setPhase((current) => (current === "finishing" ? "ready" : current));
    }
  }, [sessionId]);

  const stored: TranscriptItem[] = (session?.turns ?? []).map((turn) => ({
    kind: "stored" as const,
    turn,
  }));

  return {
    session,
    items: pending ? [...stored, pending] : stored,
    phase,
    error,
    canRetry,
    lastTiming,
    lastSpeech,
    lastReplyTurnId,
    ended: session?.status === "completed",
    send,
    retry,
    end,
    finish,
    reload,
  };
}
