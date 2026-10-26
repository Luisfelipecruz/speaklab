// The menu bar: SpeakLab's mark as a template image, and the menu under it, as plain data
// the main process hands to Electron and the tests read.
//
// The mark is drawn here rather than shipped as a file: the five bars of the site's mark,
// black on transparent, which macOS tints for the light and dark menu bar.

import type { MenuItemConstructorOptions } from "electron";

import type { SaySettings } from "./say-settings.ts";

/** 18 points at 2x. */
export const ICON_PX = 36;
export const ICON_SCALE = 2;

// The bars of the mark, in its 32-unit drawing: x, and where each starts and ends.
const BARS: readonly [number, number, number][] = [
  [8, 13.5, 18.5],
  [12.5, 10, 22],
  [17, 7.5, 24.5],
  [21.5, 11, 21],
  [26, 14, 18],
];
const STROKE = 2.4;

/** RGBA pixels of the template image: alpha carries the shape, colour is ignored. */
export function iconBitmap(size = ICON_PX): Buffer {
  const pixels = Buffer.alloc(size * size * 4);
  // The bars' extent, 18 by 17 units plus the stroke, fitted to the square with a margin.
  const unit = (size * 0.84) / (18 + STROKE);
  const left = (size - 18 * unit) / 2 - 8 * unit;
  const top = (size - 17 * unit) / 2 - 7.5 * unit;
  const radius = (STROKE / 2) * unit;
  for (let py = 0; py < size; py++) {
    for (let px = 0; px < size; px++) {
      const x = px + 0.5;
      const y = py + 0.5;
      let coverage = 0;
      for (const [bx, y0, y1] of BARS) {
        const cx = left + bx * unit;
        const cy = Math.min(Math.max(y, top + y0 * unit), top + y1 * unit);
        const distance = Math.hypot(x - cx, y - cy);
        coverage = Math.max(coverage, Math.min(1, Math.max(0, radius + 0.5 - distance)));
      }
      pixels[(py * size + px) * 4 + 3] = Math.round(coverage * 255);
    }
  }
  return pixels;
}

export interface TrayState {
  settings: SaySettings;
  /** Input Monitoring: null until the helper has said. */
  access: boolean | null;
  /** The account's language by name, for "From Spanish". */
  language: string;
}

export interface TrayActions {
  type(): void;
  copied(): void;
  fromOwn(version: SaySettings["fromOwn"]): void;
  save(on: boolean): void;
  notebook(): void;
  settings(): void;
  quit(): void;
}

/** The first line: how to start, or what is stopping fn from working. */
export function hint(state: TrayState): string {
  if (state.settings.key === "shortcuts") return "⌃⌥Space to say it in English";
  if (state.access === false) return "fn needs Input Monitoring: see Settings";
  return "Hold fn to say it in English";
}

export function trayMenu(state: TrayState, actions: TrayActions): MenuItemConstructorOptions[] {
  const { settings } = state;
  return [
    { label: hint(state), enabled: false },
    { type: "separator" },
    { label: "Type in the panel", accelerator: "Control+Alt+Space", click: () => actions.type() },
    { label: "Translate or check what I copied", accelerator: "Control+Alt+C", click: () => actions.copied() },
    { type: "separator" },
    {
      label: `From ${state.language}: Organized`,
      type: "radio",
      checked: settings.fromOwn === "organized",
      click: () => actions.fromOwn("organized"),
    },
    {
      label: `From ${state.language}: Direct`,
      type: "radio",
      checked: settings.fromOwn === "direct",
      click: () => actions.fromOwn("direct"),
    },
    { type: "separator" },
    { label: "Save to Notebook", type: "checkbox", checked: settings.save, click: () => actions.save(!settings.save) },
    { type: "separator" },
    { label: "Open Notebook", click: () => actions.notebook() },
    { label: "Settings…", accelerator: "Command+,", click: () => actions.settings() },
    { label: "Quit SpeakLab", accelerator: "Command+Q", click: () => actions.quit() },
  ];
}
