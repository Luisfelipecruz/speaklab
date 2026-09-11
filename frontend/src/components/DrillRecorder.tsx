"use client";

/**
 * Hold the button, say the sentence, see what was heard.
 *
 * The same microphone and button as a conversation turn and a reading, so the gesture is
 * one the learner already knows. The recording goes to the recogniser and the comparison
 * comes back in the same request — there is no job to poll, because nothing is aligned
 * sound by sound and nothing is stored.
 *
 * A recording that fails to send is kept, so "Send it again" sends the same bytes rather
 * than asking for the sentence twice. A new recording replaces the last result: the drill
 * is for saying it again as often as it takes.
 */

import { useRef, useState } from "react";

import { DrillResultView } from "@/components/DrillResultView";
import { RecordButton } from "@/components/RecordButton";
import { Waveform } from "@/components/Waveform";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { useRecorder } from "@/hooks/useRecorder";
import { ApiError, type Drill, type DrillResult, postDrill } from "@/lib/api";

export function DrillRecorder({ drill }: { drill: Drill }) {
  const recorder = useRecorder();
  const [result, setResult] = useState<DrillResult | null>(null);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const unsentRef = useRef<{ blob: Blob; filename: string } | null>(null);

  async function send(blob: Blob, filename: string) {
    setError(null);
    setSending(true);
    try {
      const heard = await postDrill(drill.id, blob, filename);
      unsentRef.current = null;
      setResult(heard);
    } catch (cause) {
      unsentRef.current = { blob, filename };
      setError(cause instanceof ApiError ? cause.message : "Your recording could not be sent.");
    } finally {
      setSending(false);
    }
  }

  async function stop() {
    const clip = await recorder.stop();
    if (clip) await send(clip.blob, clip.filename);
  }

  async function retry() {
    const unsent = unsentRef.current;
    if (unsent) await send(unsent.blob, unsent.filename);
  }

  const recording = recorder.state === "recording";
  const phase =
    recorder.state === "unsupported"
      ? "disabled"
      : sending
        ? "uploading"
        : recording
          ? "recording"
          : recorder.state === "requesting"
            ? "requesting"
            : "idle";

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col items-center gap-4">
        <Waveform analyser={recorder.analyser} active={recording} />
        <RecordButton
          phase={phase}
          onStart={() => void recorder.start()}
          onStop={() => void stop()}
          elapsedMs={recorder.elapsedMs}
          labels={{ uploading: "Sending what you said" }}
        />
        {sending && (
          <p aria-live="polite" className="text-sm text-muted-foreground">
            Listening to what you said&hellip;
          </p>
        )}
      </div>

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

      {result && <DrillResultView drill={drill} result={result} />}
    </div>
  );
}
