/**
 * Paste a script, see where it would be split, move a boundary, save it.
 *
 * The split is shown before anything is saved, because it is a suggestion about somebody
 * else's talk: where one part ends and the next begins is theirs to decide, and a split
 * nobody looked at is a talk cut in the wrong places.
 */

import { NewPresentation } from "@/app/(app)/rehearse/new/NewPresentation";
import { Page, PageHeader } from "@/components/PageHeader";

export const dynamic = "force-dynamic";

export const metadata = { title: "A new script — SpeakLab" };

export default function NewPresentationPage() {
  return (
    <Page className="gap-6">
      <PageHeader
        title="A new script"
        description="Paste the words you mean to say, in sentences. Every take is compared with
          them word by word, so a list of slide bullets makes a poor script — what you would
          say about that slide makes a good one. A blank line starts a new section; longer
          sections are cut at a sentence end."
      />
      <NewPresentation />
    </Page>
  );
}
