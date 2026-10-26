/**
 * One version of a capture's English, as it reads on the panel: large, with short lines;
 * for a check, the words it changed from the person's own beneath; and anything the keep
 * check could not find in it named underneath.
 *
 * A dropped name or number is said, never fixed: the version is the model's, the fact is
 * the person's, and only the person can decide which the message needs.
 */

import type { ReactNode } from "react";
import { TriangleAlert } from "lucide-react";

import { ChangedWords } from "@/components/ChangedWords";
import type { Capture, CaptureVersion } from "@/lib/api";
import { VERSION_LABEL } from "@/lib/notebook";

export function CaptureEnglish({
  capture,
  version,
  heading,
  actions,
}: {
  capture: Pick<Capture, "versions" | "dropped" | "changes">;
  version: CaptureVersion;
  heading?: string;
  actions?: ReactNode;
}) {
  const text = capture.versions[version];
  const dropped = capture.dropped[version] ?? [];
  const changes = capture.changes?.[version];
  if (!text) return null;
  return (
    <section className="flex flex-col gap-3" aria-label={heading ?? VERSION_LABEL[version]}>
      {heading && (
        <h2 className="text-xs font-medium tracking-wider text-muted-foreground uppercase">
          {heading}
        </h2>
      )}
      <p
        className="max-w-[64ch] text-lg leading-[1.6] whitespace-pre-wrap text-foreground"
        data-testid={`english-${version}`}
      >
        {text}
      </p>
      {changes && <ChangedWords steps={changes} />}
      {dropped.length > 0 && (
        <p className="flex items-start gap-2 text-sm text-muted-foreground" data-testid="dropped">
          <TriangleAlert className="mt-0.5 size-4 shrink-0 text-chart-4" aria-hidden="true" />
          <span>
            Not found in this version: {dropped.join(", ")}. Check it before you send it.
          </span>
        </p>
      )}
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </section>
  );
}
