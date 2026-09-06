"use client";

/**
 * The conversation so far, scrolled to the bottom.
 *
 * `role="log"` rather than a bare `aria-live` region on the container. The difference
 * matters: a live region announces whatever changed inside it, which on a scrolling
 * transcript can mean re-reading turns the listener has already heard, while `log`
 * means "new entries are appended at the end" and assistive technology announces only
 * the addition. It is the difference between a screen reader following a conversation
 * and one restarting it every 30 seconds.
 *
 * The auto-scroll is deliberately unconditional. A transcript that only follows along
 * when you are already at the bottom is the better behaviour for a chat client you read
 * back through; this is a conversation you are having *now*, where the thing you need on
 * screen is always the last turn.
 */

import * as React from "react";

import { TurnBubble } from "@/components/TurnBubble";
import type { LanguageErrorItem, Speech } from "@/lib/api";
import type { TranscriptItem } from "@/hooks/useSession";
import { cn } from "@/lib/utils";

export interface TranscriptPaneProps {
  items: TranscriptItem[];
  speakerLabel?: string;
  /** Attached to the last assistant turn only — see TurnBubble. */
  lastSpeech?: Speech | null;
  /**
   * The turn to speak on arrival, by id. The pane is told *which* rather than
   * "the last one", because on a reloaded transcript the last turn is an old reply and
   * a page that starts talking on load is a page nobody opens twice.
   */
  autoPlayTurnId?: number | null;
  onReplyPlayingChange?: (playing: boolean) => void;
  /**
   * Corrections keyed by turn id, from the session's report. Absent while the
   * conversation is still going — there is no report yet, and nothing to mark.
   */
  corrections?: ReadonlyMap<number, LanguageErrorItem[]>;
  className?: string;
}

export function TranscriptPane({
  items,
  speakerLabel,
  lastSpeech,
  autoPlayTurnId = null,
  onReplyPlayingChange,
  corrections,
  className,
}: TranscriptPaneProps) {
  const endRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    // `scrollIntoView` is absent from jsdom and from very old Safari. The transcript is
    // still correct without it; only the scroll position is not.
    endRef.current?.scrollIntoView?.({ behavior: "smooth", block: "end" });
  }, [items.length]);

  const lastIndex = items.length - 1;

  return (
    <div
      role="log"
      aria-live="polite"
      aria-label="Conversation transcript"
      className={cn("flex flex-col gap-4", className)}
    >
      {items.length === 0 && (
        <p className="text-sm text-muted-foreground">
          This conversation has no turns yet.
        </p>
      )}

      {items.map((item, index) => (
        <TurnBubble
          key={item.kind === "stored" ? `turn-${item.turn.id}` : item.localId}
          item={item}
          speakerLabel={speakerLabel}
          speech={index === lastIndex ? lastSpeech : null}
          autoPlay={item.kind === "stored" && item.turn.id === autoPlayTurnId}
          onPlayingChange={
            item.kind === "stored" && item.turn.id === autoPlayTurnId
              ? onReplyPlayingChange
              : undefined
          }
          corrections={item.kind === "stored" ? corrections?.get(item.turn.id) : undefined}
        />
      ))}

      <div ref={endRef} />
    </div>
  );
}
