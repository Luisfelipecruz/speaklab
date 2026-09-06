"use client";

/**
 * One turn of the conversation.
 *
 * Three things it renders are requirements rather than decoration, and each is a place
 * where the easy version would be dishonest.
 *
 * **A missing player is never silent.** An assistant turn with no audio means synthesis
 * failed, and a user turn with no audio means audio retention is off — two
 * different facts with two different sentences. Simply omitting the player would make
 * both of them look like a UI bug, and the second one look like data loss.
 *
 * **A low-confidence turn says so.** A mishearing scored as a grammar error is a
 * correction the speaker cannot act on. The threshold is the server's
 * (`ASR_CONFIDENCE_FLOOR`, still an uncalibrated placeholder), and the flag is read from
 * the response rather than recomputed here, so there is one number and not two.
 *
 * **The pending bubble contains no words.** It says the turn is being transcribed and
 * shows how long the recording was. The browser does not know what was said — the
 * recogniser is the only thing that does — so anything else in that space would be the
 * interface inventing a transcript.
 *
 * **Corrections are marked where they happened.** Once a session has its report, the
 * corrections found in a turn arrive with it, and the turn draws them on its own words
 * with a numbered list underneath. During the conversation there are none to draw: the
 * persona does not correct the speaker, and analysis runs behind the turn, so the marks
 * appear when the report does and not before.
 */

import { AlertTriangle, Loader2, VolumeX } from "lucide-react";

import { AudioPlayer } from "@/components/AudioPlayer";
import { CorrectionList, MarkedText } from "@/components/Corrections";
import { audioUrl, type LanguageErrorItem, type Speech, type Turn } from "@/lib/api";
import type { TranscriptItem } from "@/hooks/useSession";
import { markTranscript } from "@/lib/corrections";
import { cn } from "@/lib/utils";

export interface TurnBubbleProps {
  item: TranscriptItem;
  /** Who the assistant is, in this scenario. Falls back to a neutral noun. */
  speakerLabel?: string;
  /**
   * The voice's own account of the most recent reply. Only the turn that just arrived
   * has one — a reloaded transcript has the stored audio and nothing about how it went.
   */
  speech?: Speech | null;
  /** Speak this reply as soon as it appears. Set on the newest assistant turn only. */
  autoPlay?: boolean;
  onPlayingChange?: (playing: boolean) => void;
  /** The corrections the analysis found in this turn, from the session's report. */
  corrections?: LanguageErrorItem[];
}

function Frame({
  mine,
  children,
  className,
}: {
  mine: boolean;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex w-full", mine ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "flex max-w-[42rem] flex-col gap-2 rounded-xl border px-4 py-3",
          mine ? "border-primary/30 bg-primary/5" : "border-border bg-card",
          className,
        )}
      >
        {children}
      </div>
    </div>
  );
}

export function TurnBubble({
  item,
  speakerLabel = "The persona",
  speech,
  autoPlay = false,
  onPlayingChange,
  corrections,
}: TurnBubbleProps) {
  if (item.kind === "pending") {
    return (
      <Frame mine className="border-dashed">
        <span className="text-xs font-medium text-muted-foreground">You</span>
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" aria-hidden="true" />
          Transcribing {(item.durationMs / 1000).toFixed(1)}s of audio, then answering…
        </p>
      </Frame>
    );
  }

  const turn: Turn = item.turn;
  const mine = turn.role === "user";
  const src = audioUrl(turn.audio_url);
  const marked =
    mine && turn.transcript && corrections && corrections.length > 0
      ? markTranscript(turn.transcript, corrections)
      : null;

  return (
    <Frame mine={mine}>
      <div className="flex items-baseline justify-between gap-4">
        <span className="text-xs font-medium text-muted-foreground">
          {mine ? "You" : speakerLabel}
        </span>
        {turn.low_confidence && (
          <span className="flex items-center gap-1 text-xs text-amber-600 dark:text-amber-500">
            <AlertTriangle className="size-3.5" aria-hidden="true" />
            heard with low confidence
          </span>
        )}
      </div>

      {marked ? (
        <MarkedText marked={marked} />
      ) : turn.transcript ? (
        <p className="text-sm leading-relaxed whitespace-pre-wrap">{turn.transcript}</p>
      ) : (
        <p className="text-sm text-muted-foreground italic">
          Nothing was transcribed from this turn.
        </p>
      )}

      {turn.low_confidence && (
        <p className="text-xs text-muted-foreground">
          The recogniser was unsure of this one, so it will not count towards your
          accuracy over time. Re-recording somewhere quieter usually helps.
        </p>
      )}

      {src ? (
        <AudioPlayer
          src={src}
          label={mine ? "your recording" : `${speakerLabel}'s reply`}
          caption={!mine ? (turn.transcript ?? undefined) : undefined}
          autoPlay={autoPlay}
          onPlayingChange={onPlayingChange}
        />
      ) : (
        <p className="flex items-center gap-2 text-xs text-muted-foreground">
          <VolumeX className="size-3.5" aria-hidden="true" />
          {mine
            ? "Audio retention is off for your account, so this recording was not kept. The transcript and its measurements were."
            : speech?.detail
              ? `The voice could not speak this reply: ${speech.detail}`
              : "The voice was unavailable, so this reply is text only."}
        </p>
      )}

      {marked && <CorrectionList corrections={marked.corrections} />}
    </Frame>
  );
}
