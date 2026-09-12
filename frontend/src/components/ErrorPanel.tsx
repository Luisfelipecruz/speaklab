"use client";

/**
 * What a page shows when rendering it threw.
 *
 * The pages catch the failures they expect — the API unreachable, a 404, a model service
 * down — and say so in their own words. This is for the rest: a bug, or a failure nobody
 * anticipated. Next's default for that is a blank screen with one line on it, which reads
 * as the product having crashed rather than one page having failed.
 *
 * **Trying again asks the server again.** A server component that threw has no client
 * state to reset, so `reset` on its own would re-render the same failure; refreshing the
 * route first fetches it afresh.
 *
 * A production build withholds a server error's message from the browser and sends a
 * digest instead, which matches the error line in the frontend's own logs. The digest is
 * shown so a report can name it.
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTransition } from "react";

import { Page, PageHeader } from "@/components/PageHeader";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

export interface BoundaryProps {
  error: Error & { digest?: string };
  reset: () => void;
}

export function ErrorPanel({ error, reset }: BoundaryProps) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();

  function retry() {
    startTransition(() => {
      router.refresh();
      reset();
    });
  }

  return (
    <Page>
      <PageHeader
        title="This page could not be shown"
        description="Something failed while it was being put together. Trying again asks
          the server for it afresh."
      />

      <Alert variant="destructive" className="w-fit max-w-2xl">
        <AlertDescription>
          {error.digest ? (
            <>
              Reference <code className="font-mono">{error.digest}</code> — the same
              reference is in <code className="font-mono">docker compose logs frontend</code>.
            </>
          ) : (
            error.message || "No reason was given."
          )}
        </AlertDescription>
      </Alert>

      <div className="flex flex-wrap gap-2">
        <Button onClick={retry} disabled={pending}>
          Try again
        </Button>
        <Button asChild variant="outline">
          <Link href="/status">Check the services</Link>
        </Button>
      </div>
    </Page>
  );
}
