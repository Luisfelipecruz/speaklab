"use client";

/**
 * Answer out loud, in one go, and see it counted.
 *
 * **Start and stop, not hold.** A conversation turn is held because it is a sentence or
 * two and holding is the one gesture where the person and the machine agree when speech
 * ended. An answer runs up to two minutes, and holding a button that long is a test of
 * the thumb. So this one is pressed to start and pressed to stop, and the worry that makes
 * a toggle a bad idea elsewhere — a microphone left open by a forgotten second press — is
 * answered by the prompt's time limit: the recording stops itself when it runs out.
 *
 * **Say it again, tighter.** After an answer, the same prompt can be answered again, and
 * the second is stored as saying the first again and shown beside it on the same counts.
 *
 * A recording that fails to send is kept, so "Send it again" sends the same bytes rather
 * than asking for the answer twice.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { Loader2, Mic, Repeat2, Square } from "lucide-react";

import { AnswerCompare } from "@/components/AnswerCompare";
import { AnswerResult } from "@/components/AnswerResult";
import { Waveform } from "@/components/Waveform";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { useRecorder } from "@/hooks/useRecorder";
import { ApiError, type AnswerPrompt, type SpokenAnswer, postAnswer } from "@/lib/api";
import { clock } from "@/lib/answers";

export function AnswerRecorder({
  prompt,
  basis = null,
}: {
  prompt: AnswerPrompt;
  /** An earlier answer to say again, when the page was opened to say one again. */
  basis?: SpokenAnswer | null;
}) {
  const recorder = useRecorder();
  const [result, setResult] = useState<SpokenAnswer | null>(null);
  const [previous, setPrevious] = useState<SpokenAnswer | null>(basis);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const unsentRef = useRef<{ blob: Blob; filename: string } | null>(null);
  const stoppingRef = useRef(false);
  // Read when a recording is sent, which can be from a callback made on an earlier
  // render — the time limit's — so the answer being said again is kept in a ref too.
  const previousRef = useRef(previous);
  previousRef.current = previous;

  const limitMs = prompt.time_limit_s * 1000;
  const recording = recorder.state === "recording";

  async function send(blob: Blob, filename: string) {
    setError(null);
    setSending(true);
    try {
      const againOf = previousRef.current?.id ?? null;
      const answer = await postAnswer(prompt.slug, blob, filename, againOf);
      unsentRef.current = null;
      setResult(answer);
    } catch (cause) {
      unsentRef.current = { blob, filename };
      setError(cause instanceof ApiError ? cause.message : "Your recording could not be sent.");
    } finally {
      setSending(false);
    }
  }

  const stop = useCallback(async () => {
    if (stoppingRef.current) return;
    stoppingRef.current = true;
    try {
      const clip = await recorder.stop();
      if (clip) await send(clip.blob, clip.filename);
    } finally {
      stoppingRef.current = false;
    }
    // `send` reads the latest state on each render; the recorder is the only dependency
    // whose identity matters here.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recorder]);

  // The time limit stops the recording, so a forgotten second press cannot leave the
  // microphone open.
  useEffect(() => {
    if (recording && recorder.elapsedMs >= limitMs) void stop();
  }, [recording, recorder.elapsedMs, limitMs, stop]);

  function sayAgain() {
    if (!result) return;
    setPrevious(result);
    setResult(null);
  }

  async function retry() {
    const unsent = unsentRef.current;
    if (unsent) await send(unsent.blob, unsent.filename);
  }

  const unsupported = recorder.state === "unsupported";
  const busy = sending || recorder.state === "requesting";

  return (
    <div className="flex flex-col gap-8">
      {!result && (
        <div className="flex flex-col items-center gap-4">
          {previous && (
            <p className="text-sm text-muted-foreground" data-testid="saying-again">
              Saying your answer again, tighter. It will be shown beside the first.
            </p>
          )}
          <Waveform analyser={recorder.analyser} active={recording} />
          <Button
            type="button"
            size="lg"
            variant={recording ? "destructive" : "default"}
            className="h-16 w-72 text-base font-medium"
            disabled={unsupported || busy}
            aria-pressed={recording}
            onClick={() => (recording ? void stop() : void recorder.start())}
          >
            {busy ? (
              <Loader2 className="animate-spin" aria-hidden="true" />
            ) : recording ? (
              <Square aria-hidden="true" />
            ) : (
              <Mic aria-hidden="true" />
            )}
            <span>
              {sending
                ? "Counting what you said"
                : recording
                  ? `Stop — ${clock(Math.max(0, limitMs - recorder.elapsedMs))} left`
                  : previous
                    ? "Start saying it again"
                    : "Start answering"}
            </span>
          </Button>
          <p className="text-xs text-muted-foreground">
            Press to start, press again to stop. It stops by itself after{" "}
            {clock(limitMs)}.
          </p>
          {sending && (
            <p aria-live="polite" className="text-sm text-muted-foreground">
              Counting how you said it and how you built it, then asking for feedback&hellip;
            </p>
          )}
        </div>
      )}

      {recorder.error && (
        <Alert variant="destructive">
          <AlertDescription>{recorder.error.message}</AlertDescription>
        </Alert>
      )}

      {error && (
        <Alert variant="destructive">
          <AlertDescription className="flex flex-wrap items-center gap-3">
            <span>{error}</span>
            {unsentRef.current && (
              <Button size="sm" variant="outline" onClick={() => void retry()}>
                Send it again
              </Button>
            )}
          </AlertDescription>
        </Alert>
      )}

      {result && (
        <>
          {previous && result.again_of === previous.id && (
            <AnswerCompare first={previous} second={result} />
          )}
          <AnswerResult answer={result} />
          <div>
            <Button type="button" variant="outline" onClick={sayAgain}>
              <Repeat2 aria-hidden="true" />
              Say it again, tighter
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
