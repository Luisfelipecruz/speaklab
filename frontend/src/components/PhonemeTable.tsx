/**
 * The confusion pairs in a reading, rendered as `/θ/ → /s/ ×34`.
 *
 * **This is the screen read-aloud is for.** A GOP of −9.4 is a number; "you produced /s/
 * four times where English wants /θ/" is something a person can practise. On the probe
 * set the acoustic model named the substituted phone correctly in 10 cases out of 10 —
 * including the one probe whose *threshold* missed — so the second column is the more
 * reliable half of this table, not the decorative one.
 *
 * Only substitutions below the reading's own weakest band are listed. Every scored phone
 * has a `recognized_phone`, including the ones that were produced perfectly well — often
 * the same sound under a different symbol — and listing all of them would bury the two
 * rows that matter under two hundred that do not.
 *
 * Where the model reported no clear winner the row is absent rather than guessed at: no
 * pronunciation claim comes from something that did not assert it.
 */

import {
  Table,
} from "@/components/PhonemeTable.helpers";
import { confusionPairs, type PhonemeScore, type PronunciationSummary } from "@/lib/api";

export interface PhonemeTableProps {
  phonemes: PhonemeScore[];
  summary: PronunciationSummary | null;
}

export function PhonemeTable({ phonemes, summary }: PhonemeTableProps) {
  const floor = summary?.percentile_5 ?? Number.NEGATIVE_INFINITY;
  const pairs = confusionPairs(phonemes, floor);

  if (pairs.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No sound in this reading was clearly replaced by another one. That is the good
        outcome — the weakest phones were still the ones the text asked for.
      </p>
    );
  }

  return (
    <Table
      caption="Sounds where something else scored higher than the one the text asked for."
      head={["Wanted", "Heard", "Times", "Worst GOP"]}
      rows={pairs.map((pair) => [
        <span key="c" className="font-mono text-sm">/{pair.canonical}/</span>,
        <span key="h" className="font-mono text-sm">[{pair.heard}]</span>,
        <span key="n">{pair.count}</span>,
        <span key="w" className="font-mono text-sm tabular-nums">{pair.worst.toFixed(2)}</span>,
      ])}
    />
  );
}
