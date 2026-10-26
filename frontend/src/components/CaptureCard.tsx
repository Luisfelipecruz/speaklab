/**
 * One capture in the Notebook's list: when and where, what was said, the English used,
 * where it is in the practice, and what can be done with it.
 */

import Link from "next/link";
import { PenLine } from "lucide-react";

import { CopyButton } from "@/components/CopyButton";
import { DeleteCaptureButton } from "@/components/DeleteCaptureButton";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { CaptureSummary } from "@/lib/api";
import { howLabel, stateLabel, VERSION_LABEL } from "@/lib/notebook";
import { timeOf } from "@/lib/time";

export function CaptureCard({ item, zone }: { item: CaptureSummary; zone?: string }) {
  return (
    <article
      className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4 shadow-xs"
      aria-labelledby={`capture-${item.id}`}
    >
      <header className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
        <time dateTime={item.created_at} className="font-medium text-foreground tabular-nums">
          {timeOf(item.created_at, zone)}
        </time>
        {item.app && <span>{item.app}</span>}
        <span>{howLabel(item)}</span>
        <Badge variant={item.state === "due" ? "default" : "secondary"} className="ml-auto">
          {stateLabel(item.state, item.practised)}
        </Badge>
      </header>
      <p id={`capture-${item.id}`} className="text-sm text-muted-foreground italic">
        «{item.source_text}»
      </p>
      <p className="text-base leading-relaxed whitespace-pre-wrap">{item.text}</p>
      <footer className="flex flex-wrap items-center gap-2">
        <span className="text-xs text-muted-foreground">
          {VERSION_LABEL[item.chosen]}
          {item.mode === "check" &&
            (item.fixes === 0
              ? " · no mistakes found"
              : ` · ${item.fixes} fix${item.fixes === 1 ? "" : "es"}`)}
        </span>
        <span className="flex-1" />
        <Button asChild size="sm">
          <Link href={`/notebook/${item.id}/practise`}>
            <PenLine aria-hidden="true" />
            Practise
          </Link>
        </Button>
        <Button asChild size="sm" variant="outline">
          <Link href={`/notebook/${item.id}`}>Open</Link>
        </Button>
        <CopyButton text={item.text} variant="ghost" />
        <DeleteCaptureButton id={item.id} />
      </footer>
    </article>
  );
}
