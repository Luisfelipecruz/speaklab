import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

import { AuthProvider } from "@/components/AuthProvider";
import { TooltipProvider } from "@/components/ui/tooltip";
import { PRE_PAINT_SCRIPT } from "@/lib/theme";

// The variable names are what globals.css reads in its `@theme inline` block. Naming
// the sans font `--font-geist-sans` instead leaves `--font-sans` undefined and every
// `font-sans` utility silently falls back to the browser default.
//
// The classes go on `<html>`, not `<body>`, and that is load-bearing too. globals.css
// applies `font-sans` to `<html>`, which resolves `var(--font-sans)` *on that element*;
// with the variable defined one level down on `<body>` the lookup failed silently and
// every screen rendered in the browser's serif. A variable is visible to the element
// that sets it and its descendants, never to its parent.
const geistSans = Geist({ variable: "--font-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "SpeakLab",
  description:
    "Practise spoken English against local models. Scenario role-play, read-aloud pronunciation scoring, and measurable progress over time.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable}`}
      suppressHydrationWarning
    >
      <head>
        {/* Synchronous, in the head, before anything paints. The stored theme lives in
            localStorage, which the server cannot read, so the class it decides has to be
            put on <html> by the browser — and it has to happen before the first frame or
            somebody who chose dark gets a white flash on every navigation. React is told
            not to warn about the attribute it did not render, because the mismatch is
            the intended behaviour rather than a bug. */}
        <script dangerouslySetInnerHTML={{ __html: PRE_PAINT_SCRIPT }} />
      </head>
      <body className="antialiased">
        {/* One session for the whole application. The provider is a client component
            taking `children` as a prop, which does not make those children client
            components — every page below here is still server-rendered by default. */}
        <AuthProvider>
          {/* The navigation rail collapses to icons, and an icon with no name is a
              guess. The provider is here rather than around the rail because a tooltip
              renders in a portal at the end of the body. */}
          <TooltipProvider delayDuration={200}>{children}</TooltipProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
