/**
 * A small button that plays one word, beside the place that word is named.
 *
 * **The label says what it plays and nothing more.** *Hear "is"* — never *hear the
 * correct pronunciation*. What comes out is a synthetic reading of one word by one
 * voice, and a screen that promoted it to a standard would be making a claim about
 * English that this product has not measured and cannot support. The speaker is being
 * offered something to listen to, not something to be marked against.
 *
 * **The word is fetched once and then replayed.** The route answers a word it has
 * already given out without synthesising it again, but a second press should not cost
 * even that, so the decoded audio is held for as long as the button is on screen. A
 * list of sounds is fifteen buttons, and it must not become fifteen requests per read.
 *
 * A failure is shown on the button rather than thrown. The sound list is the useful
 * thing on the page; a word that cannot be played should cost the reader that word, not
 * the screen.
 */

"use client";

import { useEffect, useRef, useState } from "react";

import { speakWord } from "@/lib/api";

type State = "idle" | "loading" | "failed";

export function SpeakButton({
  word,
  className = "",
}: {
  word: string;
  className?: string;
}) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [src, setSrc] = useState<string | null>(null);
  const [state, setState] = useState<State>("idle");

  // Released with the button. Without this a page of sounds leaks one decoded word for
  // every press it saw.
  useEffect(() => {
    if (!src) return;
    return () => URL.revokeObjectURL(src);
  }, [src]);

  // The word has arrived, so play it. Keyed on `src`, which changes exactly once: a
  // later press replays the element directly rather than going through here again.
  useEffect(() => {
    if (!src) return;
    void audioRef.current?.play().catch(() => setState("failed"));
  }, [src]);

  async function press() {
    if (state === "loading") return;
    if (src) {
      void audioRef.current?.play().catch(() => setState("failed"));
      return;
    }
    setState("loading");
    try {
      setSrc(URL.createObjectURL(await speakWord(word)));
      setState("idle");
    } catch {
      setState("failed");
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={press}
        disabled={state === "loading"}
        aria-label={`Hear "${word}"`}
        title={state === "failed" ? `"${word}" could not be played` : `Hear "${word}"`}
        className={`inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-border text-xs leading-none transition-colors hover:bg-muted disabled:opacity-50 ${
          state === "failed" ? "text-destructive" : "text-muted-foreground"
        } ${className}`}
      >
        <span aria-hidden="true">{state === "failed" ? "!" : "▶"}</span>
      </button>
      <audio ref={audioRef} src={src ?? undefined} className="hidden" />
    </>
  );
}
