/**
 * One counted figure, set large, with what it counts underneath.
 *
 * The totals used to be four small numbers in a row inside one wide card, which at any
 * desktop width left the right two thirds of the card empty — a component occupying a row
 * it had nothing to put in. A tile per figure fills its row with the figures themselves,
 * and the grid that holds them decides how many share a line.
 *
 * The number is the content and it is styled as such: the largest thing on the tile, in
 * tabular figures so a column of them lines up. The label is small, capitalised and grey,
 * which is what makes it read as a label rather than as more content.
 */

export interface StatTileProps {
  label: string;
  value: number | string;
}

export function StatTile({ label, value }: StatTileProps) {
  return (
    <div className="flex flex-col gap-1 rounded-xl border border-border bg-card px-5 py-4 shadow-xs">
      <span className="text-3xl font-bold tracking-tight tabular-nums text-card-foreground">
        {value}
      </span>
      <span className="text-xs font-medium tracking-wider text-muted-foreground uppercase">
        {label}
      </span>
    </div>
  );
}
