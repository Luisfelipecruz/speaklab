/**
 * A count with its noun agreed: `1 turn`, `2 turns`, `1 conversation`.
 *
 * The number is the reader's; the grammar is ours. A screen that says "1 turns" tells a
 * language learner that the people who built it did not read it.
 */
export function plural(count: number, noun: string, plurals: string = `${noun}s`): string {
  return `${count} ${count === 1 ? noun : plurals}`;
}
