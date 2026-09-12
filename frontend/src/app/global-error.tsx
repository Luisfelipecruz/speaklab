"use client";

/**
 * The last boundary: what shows when the root layout itself fails to render.
 *
 * It replaces the root layout, so it brings its own `<html>` and `<body>` and relies on
 * nothing the layout provides — no theme script, no session, no font. That is why it is a
 * sentence and a button and nothing else.
 */

import "./globals.css";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="en">
      <body className="antialiased">
        <main className="mx-auto flex max-w-xl flex-col gap-4 px-4 py-16">
          <h1 className="text-2xl font-semibold">SpeakLab could not show this page</h1>
          <p className="text-sm text-muted-foreground">
            {error.digest
              ? `Reference ${error.digest} — the same reference is in the frontend's logs.`
              : error.message || "No reason was given."}
          </p>
          <button
            type="button"
            onClick={reset}
            className="w-fit rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground"
          >
            Try again
          </button>
        </main>
      </body>
    </html>
  );
}
