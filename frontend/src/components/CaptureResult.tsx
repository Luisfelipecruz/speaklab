"use client";

/**
 * What came back: the English to paste, the other version a click away, the fixes for a
 * check, and anything the person should know about how it was made.
 *
 * A capture kept in the Notebook writes its other version on the server; one made with
 * saving paused has no row to write it to, so asking for it sends the same words again,
 * paused too.
 */

import Link from "next/link";
import { useState } from "react";
import { ArrowRight, Info, Loader2 } from "lucide-react";

import { CaptureEnglish } from "@/components/CaptureEnglish";
import { CaptureFixes } from "@/components/CaptureFixes";
import { CopyButton } from "@/components/CopyButton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ApiError, type Capture, postCapture, writeCaptureVersion } from "@/lib/api";
import { otherVersion, VERSION_LABEL } from "@/lib/notebook";

export function CaptureResult({ capture }: { capture: Capture }) {
  const [current, setCurrent] = useState(capture);
  const [shown, setShown] = useState(capture.chosen);
  const [writing, setWriting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const other = otherVersion(current);

  async function showOther() {
    setError(null);
    if (current.versions[other]) {
      setShown(other);
      return;
    }
    setWriting(true);
    try {
      if (current.id !== null) {
        setCurrent(await writeCaptureVersion(current.id, other));
      } else if (other !== "rough") {
        const again = await postCapture({
          text: current.source_text,
          mode: current.mode,
          version: other,
          save: false,
        });
        setCurrent({ ...current, versions: { ...current.versions, ...again.versions } });
      }
      setShown(other);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "It could not be written.");
    } finally {
      setWriting(false);
    }
  }

  const text = current.versions[shown] ?? current.text;
  return (
    <section
      className="flex flex-col gap-4 rounded-xl border border-border bg-card p-5 shadow-xs"
      aria-label="The English"
      aria-live="polite"
    >
      <CaptureEnglish
        capture={current}
        version={shown}
        heading={`${VERSION_LABEL[shown]}${shown === current.chosen ? " · copied by default" : ""}`}
        actions={
          <>
            <CopyButton text={text} variant="default" />
            {shown !== other && other !== "rough" && (
              <Button size="sm" variant="outline" disabled={writing} onClick={() => void showOther()}>
                {writing && <Loader2 className="animate-spin" />}
                Show {VERSION_LABEL[other]}
              </Button>
            )}
            {shown !== current.chosen && (
              <Button size="sm" variant="ghost" onClick={() => setShown(current.chosen)}>
                Back to {VERSION_LABEL[current.chosen]}
              </Button>
            )}
          </>
        }
      />

      {current.mode === "check" && (
        <CaptureFixes
          text={current.source_text}
          fixes={current.fixes}
          uncounted={
            !current.saved
              ? "not counted: saving is paused"
              : current.via === "voice"
                ? "shown, not counted: said aloud"
                : undefined
          }
        />
      )}

      {current.notes.map((note) => (
        <p key={note} className="flex items-start gap-2 text-sm text-muted-foreground">
          <Info className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <span>{note}</span>
        </p>
      ))}

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {current.id !== null ? (
        <Button asChild variant="link" size="sm" className="self-start px-0">
          <Link href={`/notebook/${current.id}`}>
            Kept in the Notebook: open its moment
            <ArrowRight aria-hidden="true" />
          </Link>
        </Button>
      ) : (
        <p className="text-xs text-muted-foreground">Not kept: saving is paused.</p>
      )}
    </section>
  );
}
