"use client";

/**
 * Say a section out loud, see it against the script, and look at the takes together.
 *
 * **Start and stop, not hold.** A section runs the better part of a minute, and holding a
 * button that long is a test of the thumb rather than of the talk. The recording stops
 * itself at twice the target, or at three minutes — whichever is sooner — so a forgotten
 * second press cannot leave the microphone open, and the limit is said on screen before
 * anybody presses anything.
 *
 * **The script stays on the page while you say it.** A rehearsal is not a memory test:
 * the section is there to be read from at first and glanced at later, and hiding it would
 * be a different exercise from the one this is.
 *
 * **Every take stays.** They are listed newest first with what each one was worth — how
 * far from the script, how fast, how long, how many fillers — because the thing worth
 * seeing is the fourth take beside the first, not the fourth on its own.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ArrowRight, Info, Loader2, Mic, Square } from "lucide-react";

import { DifferenceGroups } from "@/components/DifferenceGroups";
import { FidelityText } from "@/components/FidelityText";
import { PhonemeHeatmap } from "@/components/PhonemeHeatmap";
import { PhonemeTable } from "@/components/PhonemeTable";
import { Sounds } from "@/components/Sounds";
import { StatTile } from "@/components/StatTile";
import { Table } from "@/components/PhonemeTable.helpers";
import { Waveform } from "@/components/Waveform";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/hooks/useAuth";
import { useRecorder } from "@/hooks/useRecorder";
import {
  ApiError,
  type Section,
  type SoundOut,
  type Take,
  getTake,
  postTake,
  setSectionTarget,
} from "@/lib/api";
import { clock } from "@/lib/answers";
import { before, takeSentence } from "@/lib/takes";

/** 1.5 s apart; 40 of them is a minute, against a budget of ten seconds for a section. */
const POLL_MS = 1500;
const MAX_POLLS = 40;

/** Nobody rehearses one section for three minutes. Without a target, this is the stop. */
const LONGEST_TAKE_MS = 180_000;

const PACE_WORD: Record<string, string> = {
  under: "inside your target",
  on: "on your target",
  over: "over your target",
};

function rounded(value: number | null): string {
  return value === null ? "—" : String(Math.round(value));
}

function pauses(take: Take): string | null {
  const ratio = take.delivery.pause_ratio;
  return ratio === null ? null : `${Math.round(ratio * 100)}%`;
}

export function SectionRehearsal({
  presentationId,
  section,
  earlier,
  nextIdx = null,
  sounds = [],
  soundsCaveat = "",
}: {
  presentationId: number;
  section: Section;
  earlier: Take[];
  /** The section after this one, or null when this is the last. */
  nextIdx?: number | null;
  /** The script's weakest sounds, shown where the take is rather than a page away. */
  sounds?: SoundOut[];
  soundsCaveat?: string;
}) {
  const recorder = useRecorder();
  const { user } = useAuth();
  const [takes, setTakes] = useState<Take[]>(earlier);
  const [shown, setShown] = useState<Take | null>(earlier[0] ?? null);
  const [target, setTarget] = useState<number | null>(section.target_seconds);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const unsentRef = useRef<{ blob: Blob; filename: string } | null>(null);
  const stoppingRef = useRef(false);
  const liveRef = useRef(true);
  const pollsRef = useRef(0);

  useEffect(() => {
    liveRef.current = true;
    return () => {
      liveRef.current = false;
    };
  }, []);

  const limitMs = Math.min(target ? target * 2000 : LONGEST_TAKE_MS, LONGEST_TAKE_MS);
  const recording = recorder.state === "recording";

  const poll = useCallback(async (id: number) => {
    pollsRef.current = 0;
    while (liveRef.current && pollsRef.current < MAX_POLLS) {
      await new Promise((resolve) => setTimeout(resolve, POLL_MS));
      if (!liveRef.current) return;
      pollsRef.current += 1;

      let next: Take;
      try {
        next = await getTake(id);
      } catch {
        // A poll that fails is not a take that failed. Keep trying to the ceiling.
        continue;
      }
      if (!liveRef.current) return;
      setShown(next);
      setTakes((current) => current.map((take) => (take.id === next.id ? next : take)));
      if (next.pronunciation !== "pending") return;
    }
  }, []);

  const send = useCallback(
    async (blob: Blob, filename: string) => {
      setError(null);
      setSending(true);
      try {
        const take = await postTake(presentationId, section.idx, blob, filename);
        unsentRef.current = null;
        setShown(take);
        setTakes((current) => [take, ...current]);
        if (take.pronunciation === "pending") void poll(take.id);
      } catch (cause) {
        unsentRef.current = { blob, filename };
        setError(
          cause instanceof ApiError ? cause.message : "Your recording could not be sent.",
        );
      } finally {
        setSending(false);
      }
    },
    [poll, presentationId, section.idx],
  );

  const stop = useCallback(async () => {
    if (stoppingRef.current) return;
    stoppingRef.current = true;
    try {
      const clip = await recorder.stop();
      if (clip) await send(clip.blob, clip.filename);
    } finally {
      stoppingRef.current = false;
    }
  }, [recorder, send]);

  useEffect(() => {
    if (recording && recorder.elapsedMs >= limitMs) void stop();
  }, [recording, recorder.elapsedMs, limitMs, stop]);

  async function saveTarget(seconds: number | null) {
    setTarget(seconds);
    try {
      await setSectionTarget(presentationId, section.idx, seconds);
    } catch {
      // The target is a convenience; a failure here must not lose the take that follows.
      setError("That target could not be saved, but you can still record.");
    }
  }

  async function retry() {
    const unsent = unsentRef.current;
    if (unsent) await send(unsent.blob, unsent.filename);
  }

  const busy = sending || recorder.state === "requesting";

  return (
    <div className="flex flex-col gap-8">
      <section aria-labelledby="the-words" className="flex flex-col gap-3">
        <h2 id="the-words" className="text-lg font-semibold tracking-tight">
          The words
        </h2>
        <p className="max-w-3xl text-lg leading-relaxed">{section.body}</p>
        {!section.scorable && (
          <p className="max-w-3xl text-sm text-muted-foreground">
            The sounds in this section are not scored:{" "}
            <span className="font-medium">{section.unscorable_words.join(", ")}</span>{" "}
            cannot be turned into phones. Everything else here works — writing them the way
            you say them, in the script, makes the sounds countable too.
          </p>
        )}
      </section>

      <section aria-labelledby="say-it" className="flex flex-col items-center gap-4">
        <h2 id="say-it" className="sr-only">
          Say it
        </h2>

        <div className="flex w-full max-w-sm items-end gap-3">
          <div className="flex flex-1 flex-col gap-2">
            <Label htmlFor="target">How long should it take? (seconds, optional)</Label>
            <Input
              id="target"
              type="number"
              min={1}
              max={600}
              value={target ?? ""}
              placeholder="no target"
              onChange={(event) => {
                const value = event.target.value.trim();
                void saveTarget(value === "" ? null : Number(value));
              }}
            />
          </div>
        </div>

        <Waveform analyser={recorder.analyser} active={recording} />
        <Button
          type="button"
          size="lg"
          variant={recording ? "destructive" : "default"}
          className="h-16 w-72 text-base font-medium"
          disabled={recorder.state === "unsupported" || busy}
          aria-pressed={recording}
          onClick={() => (recording ? void stop() : void recorder.start())}
        >
          {busy ? (
            <Loader2 className="animate-spin" aria-hidden="true" />
          ) : recording ? (
            <Square aria-hidden="true" />
          ) : (
            <Mic aria-hidden="true" />
          )}
          <span>
            {sending
              ? "Comparing it with your script"
              : recording
                ? `Stop — ${clock(Math.max(0, limitMs - recorder.elapsedMs))} left`
                : takes.length === 0
                  ? "Start the first take"
                  : "Start another take"}
          </span>
        </Button>
        <p className="text-xs text-muted-foreground">
          Press to start, press again to stop. It stops by itself after {clock(limitMs)}.
        </p>
        {user && !user.retain_audio && (
          // Said before the take rather than after it: everything is counted either way,
          // and the one thing that is lost — playing it back — is worth knowing about
          // while there is still time to turn the setting on.
          <p className="max-w-sm text-center text-xs text-muted-foreground">
            Your account does not keep recordings, so this take will be compared, counted
            and scored, and then the recording discarded. There will be nothing to play
            back.
          </p>
        )}
      </section>

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

      {shown && (
        <TakeView
          take={shown}
          section={section}
          sounds={sounds}
          soundsCaveat={soundsCaveat}
          previous={before(takes, shown)}
          sentence={takeSentence(shown, takes)}
          onTargetFromTake={
            shown.duration_ms
              ? () => void saveTarget(Math.round(shown.duration_ms! / 1000))
              : undefined
          }
        />
      )}

      {shown && (
        // Somebody who has just said a section says it again or says the next one, and
        // both should be reachable from where they are standing rather than back through
        // the script.
        <div>
          <Button asChild variant="outline">
            {nextIdx === null ? (
              <Link href={`/rehearse/${presentationId}`}>
                Back to the whole script
                <ArrowRight aria-hidden="true" />
              </Link>
            ) : (
              <Link href={`/rehearse/${presentationId}/${nextIdx}`}>
                Rehearse the next section
                <ArrowRight aria-hidden="true" />
              </Link>
            )}
          </Button>
        </div>
      )}

      {takes.length > 0 && (
        <section aria-labelledby="the-takes" className="flex flex-col gap-3">
          <h2 id="the-takes" className="text-lg font-semibold tracking-tight">
            Your takes
          </h2>
          <Table
            caption="Every take of this section, newest first."
            head={["When", "Words missed", "Words a minute", "Time", "Fillers", "Sounds"]}
            rows={takes.map((take) => [
              <button
                key={`when-${take.id}`}
                type="button"
                className="underline underline-offset-4"
                onClick={() => setShown(take)}
              >
                {take.created_at.slice(11, 16)}
              </button>,
              `${take.missed} of ${take.fidelity.reference_words}`,
              rounded(take.speech_rate_wpm),
              clock(take.duration_ms),
              String(take.fillers),
              take.median_gop === null ? "—" : take.median_gop.toFixed(1),
            ])}
          />
        </section>
      )}
    </div>
  );
}

function TakeView({
  take,
  section,
  sounds,
  soundsCaveat,
  previous,
  sentence,
  onTargetFromTake,
}: {
  take: Take;
  section: Section;
  sounds: SoundOut[];
  soundsCaveat: string;
  /** The take before this one of the same section, if there is one. */
  previous: Take | null;
  /** What this take was, assembled from the counts. Null when there is nothing to say. */
  sentence: string | null;
  /** Writes this take's own length as the section's target. */
  onTargetFromTake?: () => void;
}) {
  return (
    <section aria-labelledby={`take-${take.id}`} className="flex flex-col gap-6">
      <h2 id={`take-${take.id}`} className="text-lg font-semibold tracking-tight">
        What was heard
      </h2>

      {sentence && <p className="max-w-[70ch] text-base">{sentence}</p>}

      <FidelityText words={take.fidelity.words} />

      <DifferenceGroups words={take.fidelity.words} />

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        <StatTile
          label={`of ${take.fidelity.reference_words} words missed or changed`}
          value={take.missed}
          against={previous ? `was ${previous.missed} last take` : undefined}
        />
        <StatTile
          label="words a minute"
          value={rounded(take.speech_rate_wpm)}
          against={
            previous?.speech_rate_wpm
              ? `was ${rounded(previous.speech_rate_wpm)} last take`
              : undefined
          }
        />
        <StatTile
          // Without a target there is nothing to be over or under, so the tile says what
          // the number is. It used to say the bare word "long", which reads as a verdict
          // nobody made and nothing here could support.
          label={
            take.pace && take.target_seconds
              ? `${PACE_WORD[take.pace]} of ${clock(take.target_seconds * 1000)}`
              : "how long it took"
          }
          value={clock(take.duration_ms)}
          against={previous ? `was ${clock(previous.duration_ms)} last take` : undefined}
        />
        <StatTile
          label="of the time in pauses"
          value={pauses(take) ?? "—"}
          against={
            previous && pauses(previous) ? `was ${pauses(previous)} last take` : undefined
          }
        />
        <StatTile
          label={take.fillers === 1 ? "filler" : "fillers"}
          value={take.fillers}
          against={previous ? `was ${previous.fillers} last take` : undefined}
        />
      </div>

      {!take.target_seconds && onTargetFromTake && (
        // A target the speaker took from their own reading is defensible. An invented
        // one — "a presentation should run at 130 words a minute" — is not: no corpus of
        // good presentations has been measured here, so none is quoted.
        <div>
          <Button type="button" variant="outline" size="sm" onClick={onTargetFromTake}>
            Set this section&rsquo;s target to {clock(take.duration_ms)}
          </Button>
        </div>
      )}

      <p className="flex max-w-3xl gap-2 rounded-lg border border-chart-2/40 bg-chart-2/10 p-3 text-sm leading-relaxed">
        <Info className="mt-1 size-4 shrink-0 text-chart-2" aria-hidden="true" />
        <span>{take.caveat}</span>
      </p>

      {take.pronunciation === "pending" && (
        <p aria-live="polite" className="text-sm text-muted-foreground">
          Scoring the sounds&hellip;
        </p>
      )}

      {take.pronunciation === "unscorable" && (
        <p className="max-w-3xl text-sm text-muted-foreground">{take.pronunciation_detail}</p>
      )}

      {take.pronunciation !== "ok" &&
        take.pronunciation !== "pending" &&
        take.pronunciation !== "unscorable" &&
        take.pronunciation_detail && (
          <p className="max-w-3xl text-sm text-muted-foreground">{take.pronunciation_detail}</p>
        )}

      <Sounds sounds={sounds} caveat={soundsCaveat} />

      <p className="max-w-[70ch] text-sm text-muted-foreground">
        Tone, intonation and stress are not measured here. Nothing on this page is about
        how the words sounded together — only which words came out, how fast, and how each
        sound was made.
      </p>

      {take.pronunciation === "ok" && take.phonemes.length > 0 && (
        <div className="flex flex-col gap-6">
          <h3 className="text-sm font-semibold">The sounds you made</h3>
          <PhonemeHeatmap body={section.body} phonemes={take.phonemes} summary={take.summary} />
          <PhonemeTable phonemes={take.phonemes} summary={take.summary} />
        </div>
      )}
    </section>
  );
}
