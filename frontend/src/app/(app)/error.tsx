"use client";

/**
 * A signed-in page that threw. Inside the shell, so the rail and the way to every other
 * section stay on screen around the failure.
 */

import { type BoundaryProps, ErrorPanel } from "@/components/ErrorPanel";

export default function SectionError(props: BoundaryProps) {
  return <ErrorPanel {...props} />;
}
