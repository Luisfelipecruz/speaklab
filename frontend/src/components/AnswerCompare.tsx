/**
 * Two answers to the same prompt, side by side, on the same counts.
 *
 * No pass mark and no arrows. A shorter answer is not always a clearer one, and more
 * signposts is not better; the page lays the two out and leaves the reading to the person
 * who gave them.
 */

import type { SpokenAnswer } from "@/lib/api";
import { compareRows } from "@/lib/answers";

export function AnswerCompare({ first, second }: { first: SpokenAnswer; second: SpokenAnswer }) {
  return (
    <section className="flex flex-col gap-3" aria-labelledby="compare-heading">
      <h2 id="compare-heading" className="text-lg font-semibold tracking-tight">
        The two side by side
      </h2>
      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full text-sm tabular-nums">
          <thead className="bg-muted/50 text-left text-xs text-muted-foreground">
            <tr>
              <th scope="col" className="px-3 py-2 font-medium">
                Counted
              </th>
              <th scope="col" className="px-3 py-2 font-medium">
                First
              </th>
              <th scope="col" className="px-3 py-2 font-medium">
                Again
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {compareRows(first, second).map((row) => (
              <tr key={row.label}>
                <th scope="row" className="px-3 py-2 text-left font-normal">
                  {row.label}
                </th>
                <td className="px-3 py-2">{row.first}</td>
                <td className="px-3 py-2">{row.second}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-muted-foreground">
        The same counts for both. Nothing here says which is better: a shorter answer is not
        always a clearer one, and more signposts is not a better answer.
      </p>
    </section>
  );
}
