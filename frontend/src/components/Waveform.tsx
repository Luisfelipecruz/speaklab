"use client";

/**
 * The live signal from the microphone, while it is recording.
 *
 * **A spinner would be a lie here.** A spinner says "something is happening"; the thing
 * a person actually needs to know is whether the microphone is picking *them* up, and
 * the only honest answer to that is the waveform itself. Muted hardware, the wrong input
 * device selected in the OS, and a browser that granted permission to a dead track all
 * produce a flat line — and a flat line is a diagnosis, where a spinner is reassurance
 * about nothing.
 *
 * It goes further and says so in words. After {@link SILENT_AFTER_MS} of near-silence
 * while recording, it prints a line telling the user their microphone may be muted,
 * because a person who does not know what a waveform looks like cannot read a flat one.
 *
 * Drawing happens on a canvas at frame rate and is invisible to assistive technology on
 * purpose — a canvas that announced 60 changes a second would make a screen reader
 * useless. The state it represents is announced once, as text, in the live region below
 * it.
 */

import * as React from "react";

import { cn } from "@/lib/utils";

/** Amplitude below this, either side of the 128 midpoint, counts as silence. */
const SILENCE_THRESHOLD = 4;

/** How long a flat line has to last before it is worth saying something about. */
export const SILENT_AFTER_MS = 1800;

export interface WaveformProps {
  /** The live node from `useRecorder`, or null when nothing is being recorded. */
  analyser: AnalyserNode | null;
  active: boolean;
  className?: string;
}

export function Waveform({ analyser, active, className }: WaveformProps) {
  const canvasRef = React.useRef<HTMLCanvasElement>(null);
  const [silent, setSilent] = React.useState(false);

  React.useEffect(() => {
    if (!active || !analyser) {
      setSilent(false);
      return;
    }

    const canvas = canvasRef.current;
    // jsdom returns null, and so does a real browser that has run out of contexts. The
    // component still renders and the text below it still works, which is the reason
    // the message is text and not a shape.
    const context = canvas?.getContext("2d") ?? null;

    const samples = new Uint8Array(analyser.fftSize);
    let frame = 0;
    let quietSince: number | null = performance.now();

    const draw = () => {
      frame = requestAnimationFrame(draw);
      analyser.getByteTimeDomainData(samples);

      let peak = 0;
      for (const sample of samples) peak = Math.max(peak, Math.abs(sample - 128));

      const now = performance.now();
      if (peak > SILENCE_THRESHOLD) {
        quietSince = null;
        setSilent(false);
      } else {
        quietSince ??= now;
        if (now - quietSince > SILENT_AFTER_MS) setSilent(true);
      }

      if (!context || !canvas) return;

      const { width, height } = canvas;
      context.clearRect(0, 0, width, height);
      context.lineWidth = 2;
      context.strokeStyle = getComputedStyle(canvas).color;
      context.beginPath();

      const step = width / samples.length;
      for (let index = 0; index < samples.length; index += 1) {
        const y = (samples[index] / 128) * (height / 2);
        const x = index * step;
        if (index === 0) context.moveTo(x, y);
        else context.lineTo(x, y);
      }
      context.stroke();
    };

    frame = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(frame);
  }, [analyser, active]);

  return (
    <div className={cn("flex flex-col gap-1", className)}>
      <canvas
        ref={canvasRef}
        width={480}
        height={56}
        aria-hidden="true"
        className={cn(
          "h-14 w-full rounded-md border border-border bg-muted/40 text-primary transition-opacity",
          active ? "opacity-100" : "opacity-40",
        )}
      />
      {/* One live region, one sentence at a time. The canvas above changes every frame
          and announces nothing; this is what a screen reader hears. */}
      <p role="status" aria-live="polite" className="min-h-5 text-xs text-muted-foreground">
        {!active
          ? ""
          : silent
            ? "No sound is reaching the microphone. Check that it is not muted, and that the right input device is selected."
            : "Listening."}
      </p>
    </div>
  );
}
