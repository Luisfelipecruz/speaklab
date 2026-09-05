"use client";

/**
 * The conversation screen: the whole product, on one page.
 *
 * It wires three things together and its own logic is mostly about the seams between
 * them — the recorder (`useRecorder`), the session (`useSession`), and playback of the
 * reply.
 *
 * **Recording is closed while the reply is speaking.** Not for tidiness: a microphone
 * open while the speakers play the persona records the persona, and the recogniser then
 * transcribes SpeakLab's own voice as though the learner had said it. The pause control
 * on the player is the way out for somebody who wants to answer sooner.
 *
 * **The timing line is on the screen, not behind a debug flag.** `TurnTiming` comes back
 * on every turn precisely so it can be: a latency regression is felt long before anybody
 * notices it, and a number nobody can see is a number nobody checks. It also makes the
 * honest thing visible: on a busy machine these figures nearly triple, and a user who can
 * see 6 s of "heard / thought / spoke" knows the machine is loaded rather than assuming
 * the app is broken.
 */

import Link from "next/link";
import { useState } from "react";

import { RecordButton, type RecordPhase } from "@/components/RecordButton";
import { SessionReport } from "@/components/SessionReport";
import { TranscriptPane } from "@/components/TranscriptPane";
import { Waveform } from "@/components/Waveform";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useRecorder } from "@/hooks/useRecorder";
import { useSession } from "@/hooks/useSession";
import type { SessionDetail, TurnTiming } from "@/lib/api";

function timingLine(timing: TurnTiming): string {
  const s = (ms: number) => `${(ms / 1000).toFixed(1)}s`;
  return `last turn ${s(timing.total_ms)} — heard ${s(timing.asr_ms)}, thought ${s(
    timing.generation_ms,
  )}, spoke ${s(timing.synthesis_ms)}`;
}

export function Conversation({
  sessionId,
  initial,
}: {
  sessionId: number;
  initial: SessionDetail | null;
}) {
  const recorder = useRecorder();
  const session = useSession(sessionId, initial);
  const [replyPlaying, setReplyPlaying] = useState(false);

  const speaker = session.session?.scenario_title ?? "The persona";
  const active = session.session?.status === "active";

  const phase: RecordPhase =
    recorder.state === "unsupported" || !active
      ? "disabled"
      : session.phase === "sending"
        ? "uploading"
        : recorder.state === "recording"
          ? "recording"
          : recorder.state === "requesting"
            ? "requesting"
            : replyPlaying
              ? "playing"
              : "idle";

  async function finishRecording() {
    const clip = await recorder.stop();
    if (clip) await session.send(clip);
  }

  if (session.phase === "gone") {
    return (
      <Alert variant="destructive">
        <AlertDescription>
          This conversation no longer exists.{" "}
          <Link href="/sessions" className="underline">
            Back to your history
          </Link>
          .
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex flex-col gap-1">
          <h1 className="text-2xl font-semibold tracking-tight">{speaker}</h1>
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Badge variant={active ? "default" : "secondary"}>
              {session.session?.status ?? "loading"}
            </Badge>
            <span>{session.session?.turn_count ?? 0} turns</span>
            {session.session?.scenario_slug && (
              <Link
                href={`/scenarios/${session.session.scenario_slug}`}
                className="underline underline-offset-4 hover:text-foreground"
              >
                the brief
              </Link>
            )}
          </div>
        </div>

        {active && (
          <Button
            variant="outline"
            onClick={() => void session.end()}
            disabled={session.phase === "ending"}
          >
            {session.phase === "ending" ? "Writing the report…" : "End and get a report"}
          </Button>
        )}
      </header>

      <TranscriptPane
        items={session.items}
        speakerLabel={speaker}
        lastSpeech={session.lastSpeech}
        autoPlayTurnId={session.lastReplyTurnId}
        onReplyPlayingChange={setReplyPlaying}
      />

      {session.session?.report && <SessionReport report={session.session.report} />}

      {session.error && (
        <Alert variant="destructive">
          <AlertDescription className="flex flex-wrap items-center gap-3">
            <span>{session.error}</span>
            {session.canRetry && (
              <Button size="sm" variant="outline" onClick={() => void session.retry()}>
                Send that recording again
              </Button>
            )}
          </AlertDescription>
        </Alert>
      )}

      {recorder.error && (
        <Alert variant={recorder.error.fault === "too-short" ? "default" : "destructive"}>
          <AlertDescription>{recorder.error.message}</AlertDescription>
        </Alert>
      )}

      {active ? (
        <div className="sticky bottom-0 flex flex-col gap-3 border-t border-border bg-background/95 py-4 backdrop-blur">
          <Waveform analyser={recorder.analyser} active={recorder.state === "recording"} />

          <RecordButton
            phase={phase}
            elapsedMs={recorder.elapsedMs}
            onStart={() => void recorder.start()}
            onStop={() => void finishRecording()}
            className="self-center"
          />

          {session.lastTiming && (
            <p className="text-center font-mono text-xs text-muted-foreground">
              {timingLine(session.lastTiming)}
            </p>
          )}
        </div>
      ) : (
        <div className="flex flex-col items-center gap-3 border-t border-border py-6">
          <p className="text-sm text-muted-foreground">
            This conversation has ended. The transcript above stays available.
          </p>
          <Button asChild variant="outline">
            <Link href="/scenarios">Practise another scenario</Link>
          </Button>
        </div>
      )}
    </div>
  );
}
