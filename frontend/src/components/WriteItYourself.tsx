"use client";

/**
 * Write it in English yourself, and get the correction a conversation gets.
 *
 * The box keeps what was written after the check, so the person can fix their own words
 * and check again; each check is an attempt, and the page shows the last one.
 */

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Loader2, SpellCheck } from "lucide-react";

import { AttemptResult } from "@/components/AttemptResult";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, type CaptureAttempt, postCaptureAttempt } from "@/lib/api";

export function WriteItYourself({ captureId, zone }: { captureId: number; zone?: string }) {
  const router = useRouter();
  const [text, setText] = useState("");
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState<CaptureAttempt | null>(null);

  async function check() {
    setChecking(true);
    setError(null);
    try {
      setAttempt(await postCaptureAttempt(captureId, text));
      router.refresh();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "It could not be checked.");
    } finally {
      setChecking(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <form
        className="flex flex-col gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          if (text.trim()) void check();
        }}
      >
        <Label htmlFor="write-it">Write it in English, your way</Label>
        <Textarea
          id="write-it"
          value={text}
          onChange={(event) => setText(event.target.value)}
          rows={5}
          className="text-base leading-relaxed"
          placeholder="Without looking at the versions: say it as you would."
        />
        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit" disabled={checking || !text.trim()}>
            {checking ? <Loader2 className="animate-spin" /> : <SpellCheck />}
            {checking ? "Checking" : attempt ? "Check again" : "Check"}
          </Button>
          {checking && (
            <span aria-live="polite" className="text-sm text-muted-foreground">
              Spelling, then the grammar rules and the model&hellip;
            </span>
          )}
        </div>
      </form>

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {attempt && <AttemptResult attempt={attempt} zone={zone} />}
    </div>
  );
}
