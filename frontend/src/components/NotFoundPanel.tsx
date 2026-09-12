/**
 * What an address that leads nowhere shows, inside the shell or outside it.
 *
 * It does not say whether the thing ever existed. A conversation that belongs to another
 * account answers 404 exactly as a deleted one does, and a page that said "deleted" for
 * one and "never here" for the other would tell a stranger which ids are taken.
 */

import Link from "next/link";

import { Page, PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";

export function NotFoundPanel() {
  return (
    <Page>
      <PageHeader
        title="Nothing here"
        description="This address does not lead to anything you can open: a conversation
          that was deleted, something no longer offered, or a link typed by hand."
      />
      <div className="flex flex-wrap gap-2">
        <Button asChild>
          <Link href="/home">Go to your practice</Link>
        </Button>
        <Button asChild variant="outline">
          <Link href="/scenarios">Choose a scenario</Link>
        </Button>
      </div>
    </Page>
  );
}
