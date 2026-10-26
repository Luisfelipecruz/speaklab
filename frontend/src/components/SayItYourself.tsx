"use client";

/**
 * Say the English yourself, and see what the recogniser heard against the version you
 * used. The same button as every recording here; nothing is stored.
 */

import { useState } from "react";

import { RecordButton } from "@/components/RecordButton";
import { WordDiff } from "@/components/WordDiff";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { useRecorder } from "@/hooks/useRecorder";
import { ApiError, postSaidCapture, type SaidResult } from "@/lib/api";
import { VERSION_LABEL } from "@/lib/notebook";

export function SayItYourself({ captureId }: { captureId: number }) {
  const recorder = useRecorder();
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SaidResult | null>(null);

  async function stop() {
    const clip = await recorder.stop();
    if (!clip) return;
    setSending(true);
    setError(null);
    try {
      setResult(await postSaidCapture(captureId, clip.blob, clip.filename));
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Your recording could not be sent.");
    } finally {
      setSending(false);
    }
  }

  const phase =
    recorder.state === "unsupported"
      ? "disabled"
      : sending
        ? "uploading"
        : recorder.state === "recording"
          ? "recording"
          : recorder.state === "requesting"
            ? "requesting"
            : "idle";

  return (
    <div className="flex flex-col gap-4">
      <RecordButton
        phase={phase}
        onStart={() => void recorder.start()}
        onStop={() => void stop()}
        elapsedMs={recorder.elapsedMs}
        labels={{ idle: "Hold to say it", uploading: "Listening to what you said" }}
        className="items-start"
      />
      {recorder.error && (
        <Alert variant="destructive">
          <AlertDescription>{recorder.error.message}</AlertDescription>
        </Alert>
      )}
      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      {result && (
        <section className="flex flex-col gap-2" aria-live="polite" aria-label="What was heard">
          <h3 className="text-sm font-semibold">
            What the recogniser heard, beside {VERSION_LABEL[result.compared_with]}
          </h3>
          <WordDiff
            label="What was heard beside the version you used"
            steps={result.words.map((word) => ({ expected: word.expected, theirs: word.heard }))}
          />
          <p className="text-sm text-muted-foreground" data-testid="said-counts">
            {result.matched} of {result.expected_words} words heard as written.
          </p>
          <p className="text-xs text-muted-foreground">{result.caveat}</p>
        </section>
      )}
    </div>
  );
}
