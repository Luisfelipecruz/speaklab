/**
 * A very small table primitive.
 *
 * shadcn's `table` component is not installed, and installing it to render four columns
 * once would add a file of variants nothing else in the app uses. This is the part of it
 * that is actually needed, with the accessibility that matters kept: a real `<caption>`,
 * real `<th scope="col">`, and no `role` attributes papering over divs.
 */

import * as React from "react";

export function Table({
  caption,
  head,
  rows,
}: {
  caption: string;
  head: string[];
  rows: React.ReactNode[][];
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-left">
        <caption className="pb-3 text-left text-xs text-muted-foreground">
          {caption}
        </caption>
        <thead>
          <tr className="border-b">
            {head.map((label) => (
              <th
                key={label}
                scope="col"
                className="py-2 pr-6 text-xs font-medium uppercase tracking-wide text-muted-foreground"
              >
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((cells, index) => (
            <tr key={index} className="border-b last:border-0">
              {cells.map((cell, column) => (
                <td key={column} className="py-2 pr-6">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
