import type { Timers } from "../src/keys.ts";

export interface FakeTimers extends Timers {
  /** Moves time on by `ms`, firing what falls due in the order it falls due. */
  advance(ms: number): void;
  /** How many timers are set and not yet fired or cleared. */
  readonly pending: number;
}

/** Time that moves only when the test says. */
export function fakeTimers(): FakeTimers {
  let now = 0;
  let next = 1;
  const set = new Map<number, { at: number; callback: () => void }>();
  return {
    set(callback, ms) {
      const id = next++;
      set.set(id, { at: now + ms, callback });
      return id;
    },
    clear(id) {
      set.delete(id as number);
    },
    advance(ms) {
      const until = now + ms;
      for (;;) {
        const due = [...set.entries()].filter(([, timer]) => timer.at <= until).sort((a, b) => a[1].at - b[1].at)[0];
        if (!due) break;
        set.delete(due[0]);
        now = due[1].at;
        due[1].callback();
      }
      now = until;
    },
    get pending() {
      return set.size;
    },
  };
}
