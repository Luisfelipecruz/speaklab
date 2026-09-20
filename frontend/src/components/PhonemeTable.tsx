/**
 * The confusion pairs in a reading: the sound the text wanted, and what came out instead.
 *
 * **This is the screen read-aloud is for.** A GOP of −9.4 is a number; "you produced /s/
 * four times where English wants /θ/" is something a person can practise. On the probe
 * set the acoustic model named the substituted phone correctly in 10 cases out of 10 —
 * including the one probe whose *threshold* missed — so the second column is the more
 * reliable half of this table, not the decorative one.
 *
 * **The wanted sound is named in words, with its code beside it.** The code is what the
 * scorer thinks in and it is the only thing this table used to show, which left a reader
 * unable to join a row here to the same sound named anywhere else on the page. The name
 * comes first because it is the part anybody can act on; the code stays because two
 * screens have to be visibly about the same thing. What came out instead keeps its own
 * symbol: it is whatever the acoustic model asserted, in the model's own alphabet, and
 * naming it would mean claiming to know which English sound it was meant to be.
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
      caption="Each row is a sound the text asked for where something else scored higher — so what came out was closer to that other sound than to the one you were aiming for. The score is the lowest the wanted sound got: the further below zero, the further off it was."
      head={["The sound you were aiming for", "Closer to", "Times", "Lowest score"]}
      rows={pairs.map((pair) => [
        <span key="c" className="flex flex-wrap items-baseline gap-2">
          <span>{pair.name}</span>
          <span className="font-mono text-xs text-muted-foreground">/{pair.canonical}/</span>
        </span>,
        <span key="h" className="font-mono text-sm">[{pair.heard}]</span>,
        <span key="n">{pair.count}</span>,
        <span key="w" className="font-mono text-sm tabular-nums">{pair.worst.toFixed(2)}</span>,
      ])}
    />
  );
}
