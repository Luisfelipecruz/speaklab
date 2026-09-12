/**
 * An address no route matches. Outside the shell, because nothing about the visitor is
 * known yet, with the gutter the shell would otherwise provide.
 */

import { NotFoundPanel } from "@/components/NotFoundPanel";

export const metadata = { title: "Nothing here — SpeakLab" };

export default function NotFound() {
  return (
    <main className="px-4 py-10 sm:px-8">
      <NotFoundPanel />
    </main>
  );
}
