"use client";

/**
 * Read a passage aloud, then see it scored sound by sound. FR-12 … FR-16.
 *
 * The second practice mode, and it has a different shape from a conversation: nobody
 * answers, there is a right answer on the screen the whole time, and the interesting part
 * arrives *after* the recording rather than in reply to it.
 *
 * **The two-clock design is visible here, deliberately.** `POST /attempts` returns as soon
 * as the recogniser is done — a transcript and a WER, in about as long as a conversational
 * turn — and the phones are still being aligned. So the screen has something real to show
 * immediately, and then fills in. That is why there is a poll (FR-15) rather than one long
 * request that leaves the button spinning for ten seconds.
 *
 * **Polling stops.** Three ways: the attempt reaches a terminal state, the component
 * unmounts, or `MAX_POLLS` is reached. The third exists because the job runs in the API
 * process and an API restart mid-alignment leaves an attempt in `scoring` forever — a
 * poller with no ceiling would then hammer the endpoint until the tab is closed. When it
 * gives up it says so and offers the retry that actually fixes it.
 *
 * **`pron` being down is the ordinary case, not an error state.** It is a 1.78 GB profiled
 * service; a fresh clone has never started it. So a reading with no phones renders its
 * transcript, its WER, and one line saying what to run — not an error banner suggesting
 * something went wrong with the recording.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { PhonemeHeatmap } from "@/components/PhonemeHeatmap";
import { PhonemeTable } from "@/components/PhonemeTable";
import { RecordButton } from "@/components/RecordButton";
import { Waveform } from "@/components/Waveform";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useRecorder } from "@/hooks/useRecorder";
import {
  ApiError,
  type AttemptDetail,
  type PassageDetail,
  getAttempt,
  postAttempt,
  rescoreAttempt,
} from "@/lib/api";

/** 1.5 s apart; 40 of them is a minute, against a 10 s budget for the alignment. */
const POLL_MS = 1500;
const MAX_POLLS = 40;

type Phase = "idle" | "uploading" | "scoring" | "done" | "error";

export function PassageReader({ passage }: { passage: PassageDetail }) {
  const recorder = useRecorder();
  const [attempt, setAttempt] = useState<AttemptDetail | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState<string | null>(null);

  // The clip of a reading that failed to upload, kept so a retry sends the same bytes
  // rather than asking somebody to read seventy-nine words again. The same bargain
  // `useSession` makes for a failed turn.
  const unsentRef = useRef<Blob | null>(null);
  const unsentNameRef = useRef<string>("reading.webm");

  const pollsRef = useRef(0);
  const liveRef = useRef(true);
  useEffect(() => {
    liveRef.current = true;
    return () => {
      liveRef.current = false;
    };
  }, []);

  const poll = useCallback(async (id: number) => {
    pollsRef.current = 0;
    while (liveRef.current && pollsRef.current < MAX_POLLS) {
      await new Promise((resolve) => setTimeout(resolve, POLL_MS));
      if (!liveRef.current) return;
      pollsRef.current += 1;

      let next: AttemptDetail;
      try {
        next = await getAttempt(id);
      } catch {
        // A poll that fails is not a reading that failed. The attempt exists; keep
        // trying until the ceiling, and let that be what reports a problem.
        continue;
      }
      if (!liveRef.current) return;
      setAttempt(next);

      if (next.status === "scored" || next.status === "failed") {
        setPhase("done");
        return;
      }
    }
    if (!liveRef.current) return;
    setPhase("done");
    setError(
      "Scoring is taking longer than expected. The reading is saved — try scoring it again.",
    );
  }, []);

  const send = useCallback(
    async (audio: Blob, filename: string) => {
      setError(null);
      setPhase("uploading");
      try {
        const created = await postAttempt(passage.slug, audio, filename);
        unsentRef.current = null;
        setAttempt(created);

        // Ordinarily `pending` — the job has not run yet, which is the whole reason
        // there is a poll. But a reading can come back already terminal (a rescore that
        // the job finished first, or a future synchronous path), and polling something
        // that is already done is a wasted round trip and a second and a half of
        // "aligning" over an answer that has arrived.
        if (created.status === "scored" || created.status === "failed") {
          setPhase("done");
          return;
        }
        setPhase("scoring");
        void poll(created.id);
      } catch (cause) {
        unsentRef.current = audio;
        unsentNameRef.current = filename;
        setPhase("error");
        setError(
          cause instanceof ApiError
            ? cause.message
            : "The reading could not be sent.",
        );
      }
    },
    [passage.slug, poll],
  );

  async function stop() {
    const clip = await recorder.stop();
    if (!clip) return;
    await send(clip.blob, clip.filename);
  }

  async function retryUpload() {
    const audio = unsentRef.current;
    if (audio) await send(audio, unsentNameRef.current);
  }

  async function scoreAgain() {
    if (!attempt) return;
    setError(null);
    setPhase("scoring");
    try {
      const updated = await rescoreAttempt(attempt.id);
      setAttempt(updated);
      void poll(updated.id);
    } catch (cause) {
      setPhase("done");
      setError(cause instanceof ApiError ? cause.message : "Could not score it again.");
    }
  }

  const recording = recorder.state === "recording";
  const buttonPhase =
    recorder.state === "unsupported"
      ? "disabled"
      : phase === "uploading" || phase === "scoring"
        ? "uploading"
        : recording
          ? "recording"
          : recorder.state === "requesting"
            ? "requesting"
            : "idle";

  return (
    <div className="flex flex-col gap-8">
      <Card>
        <CardHeader>
          <CardTitle className="text-base font-medium text-muted-foreground">
            Read this aloud
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-6">
          {attempt && attempt.phonemes.length > 0 ? (
            <PhonemeHeatmap
              body={attempt.passage_body ?? passage.body}
              phonemes={attempt.phonemes}
              summary={attempt.summary}
            />
          ) : (
            <p className="text-lg leading-relaxed tracking-[-0.005em]">{passage.body}</p>
          )}
        </CardContent>
      </Card>

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
              <Button size="sm" variant="outline" onClick={retryUpload}>
                Send it again
              </Button>
            )}
            {!unsentRef.current && attempt && (
              <Button size="sm" variant="outline" onClick={scoreAgain}>
                Score it again
              </Button>
            )}
          </AlertDescription>
        </Alert>
      )}

      <div className="flex flex-col items-center gap-4">
        <Waveform analyser={recorder.analyser} active={recording} />
        <RecordButton
          phase={buttonPhase}
          onStart={() => void recorder.start()}
          onStop={() => void stop()}
          elapsedMs={recorder.elapsedMs}
        />
        {phase === "scoring" && (
          <p aria-live="polite" className="text-sm text-muted-foreground">
            Transcribed. Aligning the sounds&hellip;
          </p>
        )}
      </div>

      {attempt && phase === "done" && <Result attempt={attempt} onRescore={scoreAgain} />}
    </div>
  );
}

function Result({
  attempt,
  onRescore,
}: {
  attempt: AttemptDetail;
  onRescore: () => void;
}) {
  const wer = attempt.wer;

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">What was heard</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <p className="text-sm leading-relaxed">{attempt.transcript}</p>

          {wer !== null && (
            <p className="text-xs text-muted-foreground">
              Word error rate against the passage: <strong>{(wer * 100).toFixed(0)}%</strong>.
              {wer > 0.5 && (
                <>
                  {" "}
                  That is high enough that the recogniser probably heard something other
                  than this passage — the sound scores below are unlikely to mean much.
                </>
              )}
            </p>
          )}
        </CardContent>
      </Card>

      {attempt.pronunciation === "unavailable" ? (
        <Alert>
          <AlertDescription className="flex flex-col gap-3">
            <span>{attempt.pronunciation_detail}</span>
            <span className="text-xs text-muted-foreground">
              Your reading is saved. Start the scorer with{" "}
              <code className="font-mono">make pron-up</code>, then score this reading
              again — you will not have to read it twice.
            </span>
            <Button size="sm" variant="outline" className="w-fit" onClick={onRescore}>
              Score it again
            </Button>
          </AlertDescription>
        </Alert>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Sounds worth practising</CardTitle>
          </CardHeader>
          <CardContent>
            <PhonemeTable phonemes={attempt.phonemes} summary={attempt.summary} />
          </CardContent>
        </Card>
      )}
    </div>
  );
}
