"use client";

/**
 * Push and hold to speak. Space does the same thing.
 *
 * **Held, not toggled.** The alternative designs both guess: voice-activity detection
 * decides for itself when you have finished a sentence and is wrong on a pause for
 * thought, and click-to-start/click-to-stop leaves the microphone open when somebody
 * forgets the second click. Holding a button is the one gesture where the person and the
 * machine agree about when speech ended, and this product is for learners who pause
 * mid-sentence more than most.
 *
 * **The keyboard is not a fallback here, it is the same control.** PRD §9.2 requires
 * keyboard-operable recording, so Space is bound to keydown and keyup — press and hold,
 * exactly like the pointer — rather than to a click that would have no held state at
 * all. The browser's own "Space activates a button on keyup" behaviour is suppressed,
 * because it would fire a second, empty gesture at the end of every recording.
 *
 * Pointer capture matters more than it looks: without it, dragging off the button
 * mid-sentence sends the `pointerup` somewhere else and the recording never stops.
 */

import * as React from "react";
import { Loader2, Mic, Square, Volume2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export type RecordPhase =
  | "idle"
  | "requesting"
  | "recording"
  | "uploading"
  | "playing"
  | "disabled";

export interface RecordButtonProps {
  phase: RecordPhase;
  onStart: () => void;
  onStop: () => void;
  /** Shown while recording, so a held button has a visible clock. */
  elapsedMs?: number;
  className?: string;
}

const LABEL: Record<RecordPhase, string> = {
  idle: "Hold to speak",
  requesting: "Waiting for the microphone",
  recording: "Recording — release to send",
  uploading: "Sending your turn",
  playing: "Playing the reply",
  disabled: "Recording is unavailable",
};

function seconds(ms: number): string {
  return `${(ms / 1000).toFixed(1)}s`;
}

export function RecordButton({
  phase,
  onStart,
  onStop,
  elapsedMs = 0,
  className,
}: RecordButtonProps) {
  const recording = phase === "recording";
  // Everything except idle and recording is a state where a new gesture must not start
  // one: the microphone is being granted, the last turn is still in flight, or recording
  // is not possible at all.
  const blocked = phase === "uploading" || phase === "requesting" || phase === "disabled" || phase === "playing";

  const press = React.useCallback(() => {
    if (!blocked && !recording) onStart();
  }, [blocked, recording, onStart]);

  const release = React.useCallback(() => {
    if (recording) onStop();
  }, [recording, onStop]);

  return (
    <div className={cn("flex flex-col items-center gap-2", className)}>
      <Button
        type="button"
        size="lg"
        variant={recording ? "destructive" : "default"}
        disabled={phase === "disabled"}
        aria-pressed={recording}
        aria-label={LABEL[phase]}
        className={cn(
          "h-16 w-64 select-none text-base font-medium",
          recording && "animate-pulse",
        )}
        onPointerDown={(event) => {
          // Without capture, a pointerup that happens after the pointer has left the
          // button is delivered to whatever is under it, and the recording runs on.
          event.currentTarget.setPointerCapture?.(event.pointerId);
          press();
        }}
        onPointerUp={release}
        onPointerCancel={release}
        onKeyDown={(event) => {
          if (event.key !== " " && event.key !== "Enter") return;
          // Suppress the browser's own activation on keyup, which would arrive after
          // the recording has already stopped and start an empty second one.
          event.preventDefault();
          if (event.repeat) return;
          press();
        }}
        onKeyUp={(event) => {
          if (event.key !== " " && event.key !== "Enter") return;
          event.preventDefault();
          release();
        }}
        // Tabbing away, or the window losing focus, must not leave the microphone open.
        onBlur={release}
      >
        {phase === "uploading" || phase === "requesting" ? (
          <Loader2 className="animate-spin" />
        ) : phase === "playing" ? (
          <Volume2 />
        ) : recording ? (
          <Square />
        ) : (
          <Mic />
        )}
        <span>{recording ? `Recording ${seconds(elapsedMs)}` : LABEL[phase]}</span>
      </Button>

      <p className="text-xs text-muted-foreground">
        Hold the button, or hold <kbd className="rounded border border-border px-1">Space</kbd>,
        while you speak.
      </p>
    </div>
  );
}
