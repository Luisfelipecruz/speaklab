"use client";

/**
 * Say it in English, in the browser: the panel the app opens with fn, as a box on the
 * Notebook page, so the feature works without the key.
 *
 * Type in your own language to have it written in English, paste English to have it
 * checked, or hold the button and say it. Spanish or English is decided by the words, or
 * by the recogniser for speech; the switch says which when the guess would be wrong.
 */

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Languages, Loader2 } from "lucide-react";

import { CaptureResult } from "@/components/CaptureResult";
import { RecordButton } from "@/components/RecordButton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useRecorder } from "@/hooks/useRecorder";
import { ApiError, type Capture, type CaptureRequest, postCapture } from "@/lib/api";

type Mode = NonNullable<CaptureRequest["mode"]>;

const MODES: { value: Mode; label: string }[] = [
  { value: "auto", label: "Decide for me" },
  { value: "translate", label: "It is in my language" },
  { value: "check", label: "It is English: check it" },
];

export function WriteInEnglish() {
  const router = useRouter();
  const recorder = useRecorder();
  const [text, setText] = useState("");
  const [mode, setMode] = useState<Mode>("auto");
  const [keep, setKeep] = useState(true);
  const [sending, setSending] = useState<"text" | "voice" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<Capture | null>(null);

  async function send(payload: CaptureRequest) {
    setSending(payload.audio ? "voice" : "text");
    setError(null);
    try {
      const made = await postCapture({ ...payload, mode, save: keep });
      setResult(made);
      if (made.saved) router.refresh();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "It could not be sent.");
    } finally {
      setSending(null);
    }
  }

  async function stop() {
    const clip = await recorder.stop();
    if (clip) await send({ audio: { blob: clip.blob, filename: clip.filename } });
  }

  const phase =
    recorder.state === "unsupported"
      ? "disabled"
      : sending !== null
        ? "uploading"
        : recorder.state === "recording"
          ? "recording"
          : recorder.state === "requesting"
            ? "requesting"
            : "idle";

  return (
    <div className="flex flex-col gap-4">
      <form
        className="flex flex-col gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          if (text.trim()) void send({ text, via: "typed" });
        }}
      >
        <Label htmlFor="say-it">Write it in English, or check your English</Label>
        <Textarea
          id="say-it"
          value={text}
          onChange={(event) => setText(event.target.value)}
          rows={4}
          className="text-base leading-relaxed"
          placeholder="Escribe en tu idioma, or paste English to check it…"
        />
        <fieldset className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
          <legend className="sr-only">Which language it is in</legend>
          {MODES.map((option) => (
            <label key={option.value} className="flex items-center gap-1.5">
              <input
                type="radio"
                name="mode"
                value={option.value}
                checked={mode === option.value}
                onChange={() => setMode(option.value)}
              />
              {option.label}
            </label>
          ))}
          <label className="ml-auto flex items-center gap-1.5">
            <input type="checkbox" checked={keep} onChange={(event) => setKeep(event.target.checked)} />
            Keep it in the Notebook
          </label>
        </fieldset>
        <div className="flex flex-wrap items-center gap-4">
          <Button type="submit" disabled={sending !== null || !text.trim()}>
            {sending === "text" ? <Loader2 className="animate-spin" /> : <Languages />}
            Get the English
          </Button>
          <span className="text-sm text-muted-foreground">or</span>
          <RecordButton
            phase={phase}
            onStart={() => void recorder.start()}
            onStop={() => void stop()}
            elapsedMs={recorder.elapsedMs}
            labels={{ idle: "Hold to speak", uploading: "Writing the English" }}
            className="items-start"
          />
        </div>
      </form>

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
      {result && <CaptureResult key={`${result.id}-${result.created_at}`} capture={result} />}
    </div>
  );
}
