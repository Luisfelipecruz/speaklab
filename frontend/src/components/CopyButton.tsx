"use client";

/**
 * Put a text on the clipboard, and say that it is there.
 *
 * A browser refuses the clipboard to a page that is not focused or not on a secure origin,
 * so a refusal is said in words rather than left as a button that did nothing.
 */

import { useEffect, useState } from "react";
import { Check, Copy } from "lucide-react";

import { Button } from "@/components/ui/button";

export function CopyButton({
  text,
  label = "Copy",
  variant = "outline",
}: {
  text: string;
  label?: string;
  variant?: "outline" | "default" | "ghost";
}) {
  const [state, setState] = useState<"idle" | "copied" | "refused">("idle");

  useEffect(() => {
    if (state !== "copied") return;
    const timer = setTimeout(() => setState("idle"), 2000);
    return () => clearTimeout(timer);
  }, [state]);

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setState("copied");
    } catch {
      setState("refused");
    }
  }

  return (
    <span className="inline-flex items-center gap-2">
      <Button type="button" size="sm" variant={variant} onClick={() => void copy()}>
        {state === "copied" ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}
        {state === "copied" ? "Copied" : label}
      </Button>
      <span aria-live="polite" className="text-xs text-muted-foreground">
        {state === "refused" ? "The browser did not allow it: select the text and copy it." : ""}
      </span>
    </span>
  );
}
