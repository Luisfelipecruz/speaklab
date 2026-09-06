"use client";

/**
 * Recompute the snapshots this page is drawn from.
 *
 * It is offered rather than done automatically, because rebuilding on every page load is
 * exactly what a snapshot table exists to avoid — the cost would grow with how much the
 * user had practised, which is backwards. Ending a session rolls itself up, so this is
 * normally unnecessary; it is here for read-aloud scoring, which finishes after the
 * request that started it, and for turns filled in by a backfill.
 *
 * `router.refresh()` rather than swallowing the response. The page is server-rendered, so
 * the server's answer is the one that decides what is on screen — rendering the body of
 * this request instead would leave two sources of truth one refresh apart.
 */

import { useRouter } from "next/navigation";
import { useState } from "react";
import { RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ApiError, refreshProgress } from "@/lib/api";

export function RefreshProgress({ stale }: { stale: boolean }) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function rebuild() {
    setPending(true);
    setError(null);
    try {
      await refreshProgress();
      router.refresh();
    } catch (cause) {
      setError(
        cause instanceof ApiError ? cause.message : "Could not rebuild the figures.",
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <span className="flex items-center gap-2">
      {error && <span className="text-xs text-destructive">{error}</span>}
      <Button
        variant={stale ? "default" : "outline"}
        size="sm"
        disabled={pending}
        onClick={rebuild}
      >
        <RefreshCw />
        {pending ? "Rebuilding" : stale ? "Bring up to date" : "Rebuild"}
      </Button>
    </span>
  );
}
