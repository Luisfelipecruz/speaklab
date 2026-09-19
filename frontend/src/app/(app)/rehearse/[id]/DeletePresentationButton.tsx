"use client";

/**
 * Delete one script, with the confirmation step a destructive action gets.
 *
 * Two clicks rather than a modal, the same bargain the History page makes: the second
 * click is the confirmation, the button says so, and it reverts on blur.
 *
 * Deleting takes the takes and any recording nothing else points at with it, so the
 * button says that before it is pressed rather than after.
 */

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ApiError, deletePresentation } from "@/lib/api";

export function DeletePresentationButton({ id, title }: { id: number; title: string }) {
  const router = useRouter();
  const [armed, setArmed] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function remove() {
    if (!armed) {
      setArmed(true);
      return;
    }
    setPending(true);
    try {
      await deletePresentation(id);
      router.push("/rehearse");
      router.refresh();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not delete it.");
      setPending(false);
      setArmed(false);
    }
  }

  return (
    <span className="flex items-center gap-2">
      {error && <span className="text-xs text-destructive">{error}</span>}
      <Button
        variant={armed ? "destructive" : "ghost"}
        size="sm"
        disabled={pending}
        onBlur={() => setArmed(false)}
        onClick={remove}
        aria-label={armed ? `Confirm deleting ${title}` : `Delete ${title}`}
      >
        <Trash2 />
        {armed ? "Really delete, with every take" : "Delete"}
      </Button>
    </span>
  );
}
