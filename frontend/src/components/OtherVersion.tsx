"use client";

/**
 * The version that was not copied, folded under the one that was.
 *
 * Written behind the reply, so it is usually there by the time anyone looks; when it is
 * not, opening it writes it now rather than waiting for the work behind the reply.
 */

import { useState } from "react";
import { Loader2 } from "lucide-react";

import { CaptureEnglish } from "@/components/CaptureEnglish";
import { CopyButton } from "@/components/CopyButton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ApiError, type Capture, type CaptureVersion, writeCaptureVersion } from "@/lib/api";
import { VERSION_HINT, VERSION_LABEL } from "@/lib/notebook";

export function OtherVersion({
  capture,
  version,
}: {
  capture: Capture;
  version: CaptureVersion;
}) {
  const [current, setCurrent] = useState<Capture>(capture);
  const [writing, setWriting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const text = current.versions[version];

  async function write() {
    if (current.id === null) return;
    setWriting(true);
    setError(null);
    try {
      setCurrent(await writeCaptureVersion(current.id, version));
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "It could not be written.");
    } finally {
      setWriting(false);
    }
  }

  return (
    <details className="group rounded-lg border border-border p-4 open:bg-muted/30">
      <summary className="cursor-pointer text-sm font-medium">
        The other version · {VERSION_LABEL[version]}
        <span className="ml-2 font-normal text-muted-foreground">{VERSION_HINT[version]}</span>
      </summary>
      <div className="mt-4 flex flex-col gap-3">
        {text ? (
          <CaptureEnglish
            capture={current}
            version={version}
            actions={<CopyButton text={text} label={`Copy ${VERSION_LABEL[version]}`} />}
          />
        ) : (
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-sm text-muted-foreground">Not written yet.</span>
            <Button size="sm" variant="outline" disabled={writing} onClick={() => void write()}>
              {writing && <Loader2 className="animate-spin" />}
              Write it now
            </Button>
          </div>
        )}
        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
      </div>
    </details>
  );
}
