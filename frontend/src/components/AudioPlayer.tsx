"use client";

/**
 * Playback for one stored recording or one synthesised reply.
 *
 * It plays a URL — in practice `GET /audio/{asset_id}`, which is the only endpoint that
 * serves audio and is ownership-checked (m4). It deliberately knows nothing about how
 * the audio was made: the persona's reply from the TTS service and the learner's own
 * recording are the same object to this component, and a session transcript shows both
 * side by side.
 *
 * Three things here are requirements rather than polish:
 *
 * - **Keyboard operable.** PRD §9.2 requires it. Space and Enter toggle playback, the
 *   arrow keys seek. That falls out of using real `<button>` and `<input type=range>`
 *   elements instead of divs with click handlers.
 * - **A caption slot.** PRD §9.2 requires captions on all synthesised speech. The
 *   transcript is passed in rather than fetched, because whoever renders a turn already
 *   has it and a second request for text that is already on the page would be a
 *   fabrication risk as well as a waste.
 * - **A visible error state.** A failed load has to say so. The default behaviour of an
 *   `<audio>` element that cannot fetch its source is to sit there looking idle, which
 *   is indistinguishable from audio that has not been pressed yet.
 *
 * There is no unit test beside this file, and that is a gap with a date on it rather
 * than an oversight: the Jest and React Testing Library harness arrives with m7, which
 * is also the milestone that first mounts this component. It is type-checked, linted
 * and built by CI in the meantime.
 */

import * as React from "react";
import { Loader2, Pause, Play, TriangleAlert } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export interface AudioPlayerProps {
  /** Where the audio lives. Usually `${PUBLIC_API_URL}/audio/${assetId}`. */
  src: string;
  /**
   * Shown beneath the controls. Required for synthesised speech by PRD §9.2; optional
   * here because a learner's own recording is captioned by its transcript elsewhere.
   */
  caption?: string;
  /** Accessible name for the play control, e.g. "the barista's reply". */
  label?: string;
  /**
   * Known ahead of time for a stored asset, so the scrubber has a real length before
   * the browser has read enough of the file to know one.
   */
  durationMs?: number;
  className?: string;
}

function formatTime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "0:00";
  const whole = Math.floor(seconds);
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

export function AudioPlayer({
  src,
  caption,
  label = "audio",
  durationMs,
  className,
}: AudioPlayerProps) {
  const audioRef = React.useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = React.useState(false);
  const [waiting, setWaiting] = React.useState(false);
  const [failed, setFailed] = React.useState(false);
  const [position, setPosition] = React.useState(0);
  // Seeded from the prop so the control is not a zero-length bar until metadata loads,
  // then replaced by what the file actually says. The two disagree more often than they
  // should: a WAV header is authoritative, a duration passed from a database row is a
  // record of what some other process measured.
  const [duration, setDuration] = React.useState((durationMs ?? 0) / 1000);

  // A new src is a different recording, not a seek within this one.
  React.useEffect(() => {
    setPlaying(false);
    setFailed(false);
    setPosition(0);
    setDuration((durationMs ?? 0) / 1000);
  }, [src, durationMs]);

  const toggle = React.useCallback(() => {
    const audio = audioRef.current;
    if (!audio || failed) return;
    if (audio.paused) {
      // `play()` rejects when autoplay policy blocks it or the source is unusable.
      // Unhandled, that is a console error and a button that appears to do nothing.
      void audio.play().catch(() => setFailed(true));
    } else {
      audio.pause();
    }
  }, [failed]);

  const seek = (seconds: number) => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.currentTime = seconds;
    setPosition(seconds);
  };

  return (
    <div
      className={cn(
        "flex flex-col gap-2 rounded-lg border border-border bg-card p-3",
        className,
      )}
    >
      <audio
        ref={audioRef}
        src={src}
        preload="metadata"
        onLoadedMetadata={(event) => {
          const value = event.currentTarget.duration;
          // A streamed or headerless file reports Infinity here. Keeping the prop's
          // value is better than rendering "Infinity:NaN".
          if (Number.isFinite(value) && value > 0) setDuration(value);
        }}
        onTimeUpdate={(event) => setPosition(event.currentTarget.currentTime)}
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onWaiting={() => setWaiting(true)}
        onPlaying={() => setWaiting(false)}
        onEnded={() => {
          setPlaying(false);
          setPosition(0);
        }}
        onError={() => {
          setFailed(true);
          setPlaying(false);
        }}
      />

      <div className="flex items-center gap-3">
        <Button
          type="button"
          size="icon"
          variant={failed ? "destructive" : "default"}
          onClick={toggle}
          disabled={failed}
          aria-label={
            failed ? `${label} failed to load` : `${playing ? "Pause" : "Play"} ${label}`
          }
        >
          {failed ? (
            <TriangleAlert />
          ) : waiting ? (
            <Loader2 className="animate-spin" />
          ) : playing ? (
            <Pause />
          ) : (
            <Play />
          )}
        </Button>

        <input
          type="range"
          min={0}
          max={duration || 0}
          step={0.05}
          value={Math.min(position, duration || 0)}
          onChange={(event) => seek(Number(event.target.value))}
          disabled={failed || !duration}
          aria-label={`Seek within ${label}`}
          className="h-1 flex-1 cursor-pointer appearance-none rounded-full bg-muted accent-primary disabled:cursor-not-allowed disabled:opacity-50"
        />

        <span
          className="shrink-0 font-mono text-xs tabular-nums text-muted-foreground"
          // Position changes several times a second; announcing every tick would make
          // a screen reader unusable. The duration is in the label instead.
          aria-hidden="true"
        >
          {formatTime(position)} / {formatTime(duration)}
        </span>
      </div>

      {failed && (
        <p role="alert" className="text-xs text-destructive">
          This audio could not be loaded. It may have been deleted — recordings are
          removed when audio retention is turned off.
        </p>
      )}

      {caption && (
        <p className="text-sm leading-relaxed text-muted-foreground">{caption}</p>
      )}
    </div>
  );
}
