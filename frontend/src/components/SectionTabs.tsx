/**
 * A row of tabs that are ordinary links, for a page with more on it than fits a screen.
 *
 * **Links rather than a client-side tab widget.** The state lives in the URL, so a tab can
 * be shared, bookmarked and reached by the back button, the server renders only the
 * section being looked at, and the whole thing works before any JavaScript arrives. A tab
 * component would have to be a client component holding state the address bar already
 * holds better.
 *
 * **`nav` and `aria-current`, not `role="tablist"`.** The ARIA tab pattern describes
 * panels swapped in place within one document; these are separate addresses, and
 * announcing them as tabs would promise a keyboard contract — arrow keys moving between
 * panels — that navigation links do not honour.
 */

import Link from "next/link";

import { cn } from "@/lib/utils";

export interface Section {
  key: string;
  label: string;
  href: string;
}

export function SectionTabs({
  label,
  sections,
  current,
}: {
  label: string;
  sections: Section[];
  current: string;
}) {
  return (
    <nav aria-label={label}>
      {/* Scrolls rather than wraps: on a phone five tabs would otherwise become two rows
          that push the content below the fold. As wide as its tabs and no wider — a
          block-level flex row would paint the grey track across the whole page, and a
          track with five tabs in its left fifth is a bar of nothing. */}
      <ul className="inline-flex max-w-full gap-1 overflow-x-auto rounded-lg bg-muted p-1">
        {sections.map((section) => {
          const active = section.key === current;
          return (
            <li key={section.key} className="shrink-0">
              <Link
                href={section.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "block rounded-md px-3 py-1.5 text-sm font-medium whitespace-nowrap transition-colors",
                  active
                    ? "bg-card text-foreground shadow-sm ring-1 ring-border"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {section.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
