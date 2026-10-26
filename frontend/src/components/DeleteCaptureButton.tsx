"use client";

/**
 * Delete one capture, or every one of them, with a second click as the confirmation.
 *
 * As with a conversation: the button says what the second click does and reverts when it
 * loses focus, and the list is rendered again from the API rather than edited locally,
 * since deleting a capture also deletes what was written of it.
 */

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ApiError, deleteAllCaptures, deleteCapture } from "@/lib/api";

function useTwoClicks(action: () => Promise<unknown>, after: () => void) {
  const [armed, setArmed] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function press() {
    if (!armed) {
      setArmed(true);
      return;
    }
    setPending(true);
    try {
      await action();
      after();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not delete it.");
      setPending(false);
      setArmed(false);
    }
  }

  return { armed, pending, error, press, disarm: () => setArmed(false) };
}

export function DeleteCaptureButton({ id, back = false }: { id: number; back?: boolean }) {
  const router = useRouter();
  const button = useTwoClicks(
    () => deleteCapture(id),
    () => (back ? router.push("/notebook") : router.refresh()),
  );
  return (
    <span className="flex items-center gap-2">
      {button.error && <span className="text-xs text-destructive">{button.error}</span>}
      <Button
        variant={button.armed ? "destructive" : "ghost"}
        size="sm"
        disabled={button.pending}
        onBlur={button.disarm}
        onClick={() => void button.press()}
        aria-label={button.armed ? `Confirm deleting capture ${id}` : `Delete capture ${id}`}
      >
        <Trash2 />
        {button.armed ? "Really delete" : "Delete"}
      </Button>
    </span>
  );
}

export function DeleteAllCaptures({ count }: { count: number }) {
  const router = useRouter();
  const button = useTwoClicks(deleteAllCaptures, () => router.refresh());
  if (count === 0) return null;
  return (
    <span className="flex items-center gap-2">
      {button.error && <span className="text-xs text-destructive">{button.error}</span>}
      <Button
        variant={button.armed ? "destructive" : "outline"}
        size="sm"
        disabled={button.pending}
        onBlur={button.disarm}
        onClick={() => void button.press()}
      >
        <Trash2 />
        {button.armed
          ? `Really delete all ${count}`
          : `Delete every capture, with what you wrote of them`}
      </Button>
    </span>
  );
}
