"use client";

/**
 * Delete one conversation, with the confirmation step that a destructive action gets.
 *
 * Two clicks rather than a modal: the second click is the confirmation, the button says
 * so, and it reverts on blur. A dialog for a row action is more ceremony than the action
 * deserves, and a bare one-click delete beside a link people are aiming at is how
 * somebody loses a session they wanted.
 *
 * `router.refresh()` rather than removing the row locally. The list is server-rendered
 * from the API, so the server's answer is the one that decides what is there — and
 * deleting a session also deletes recordings that nothing else references, which is a
 * consequence this page should show rather than simulate.
 */

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ApiError, deleteSession } from "@/lib/api";

export function DeleteSessionButton({ id }: { id: number }) {
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
      await deleteSession(id);
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
        aria-label={armed ? `Confirm deleting session ${id}` : `Delete session ${id}`}
      >
        <Trash2 />
        {armed ? "Really delete" : "Delete"}
      </Button>
    </span>
  );
}
