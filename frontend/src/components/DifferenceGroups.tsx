/**
 * The words that came out differently, sorted into what kind of difference each one is.
 *
 * One number for every word that differed is the least useful true thing this page can
 * say. A dropped plural and a word the recogniser misheard are not the same event, and a
 * number said correctly and written as a digit is not an event at all — so they are
 * counted apart, each group carries its pairs, and the figures group says out loud that
 * it is not counted.
 *
 * Nothing here judges. A group is a heading, a line saying what that kind of difference
 * is, and the pairs themselves; the reader decides which of them is worth their evening.
 */

import type { AlignedWord } from "@/lib/api";
import {
  DIFFERENCE_HEADING,
  DIFFERENCE_NOTE,
  DIFFERENCE_ORDER,
  DIFFERENCE_TINT,
  differenceSentence,
  wordsOfKind,
} from "@/lib/differences";

export function DifferenceGroups({ words }: { words: AlignedWord[] }) {
  const groups = DIFFERENCE_ORDER.map((kind) => ({
    kind,
    pairs: wordsOfKind(words, kind),
  })).filter((group) => group.pairs.length > 0);

  if (groups.length === 0) return null;

  const sentence = differenceSentence(words);

  return (
    <section aria-labelledby="differences" className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <h3 id="differences" className="text-sm font-semibold">
          What came out differently
        </h3>
        {sentence ? (
          <p className="text-sm text-muted-foreground">{sentence}</p>
        ) : (
          <p className="text-sm text-muted-foreground">
            Every word of the script was said as written.
          </p>
        )}
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        {groups.map(({ kind, pairs }) => (
          <div key={kind} className="flex flex-col gap-2 rounded-lg border border-border p-3">
            <p className={`text-sm font-medium ${DIFFERENCE_TINT[kind]}`}>
              {DIFFERENCE_HEADING[kind]} · {pairs.length}
            </p>
            <p className="text-xs text-muted-foreground">{DIFFERENCE_NOTE[kind]}</p>
            <ul className="flex flex-col gap-1 text-sm">
              {pairs.map((pair, index) => (
                <li key={`${pair.expected}-${index}`}>
                  <span className="text-muted-foreground line-through">{pair.expected}</span>{" "}
                  <span aria-hidden="true">→</span>{" "}
                  <span className="font-medium">{pair.heard}</span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </section>
  );
}
