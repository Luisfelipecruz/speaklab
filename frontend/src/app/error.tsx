"use client";

/**
 * A page outside the shell that threw — sign-in, registration, the status page. The same
 * panel as inside it, with the gutter the shell would otherwise provide.
 */

import { type BoundaryProps, ErrorPanel } from "@/components/ErrorPanel";

export default function RootError(props: BoundaryProps) {
  return (
    <main className="px-4 py-10 sm:px-8">
      <ErrorPanel {...props} />
    </main>
  );
}
