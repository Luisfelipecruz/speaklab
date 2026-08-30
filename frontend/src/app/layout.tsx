import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

import { AuthProvider } from "@/components/AuthProvider";

// The variable names are what globals.css reads in its `@theme inline` block. Naming
// the sans font `--font-geist-sans` instead leaves `--font-sans` undefined and every
// `font-sans` utility silently falls back to the browser default.
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
    <html lang="en">
      <body className={`${geistSans.variable} ${geistMono.variable} antialiased`}>
        {/* One session for the whole application. The provider is a client component
            taking `children` as a prop, which does not make those children client
            components — every page below here is still server-rendered by default. */}
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
