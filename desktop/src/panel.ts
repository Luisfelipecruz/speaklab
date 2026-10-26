// The Say it in English panel as a window: what it is made with, where it goes, and the
// one rule it changes for the app. Plain values, so the tests can read them without
// Electron.
//
// A panel (macOS's non-activating kind), frameless and translucent, above every window and
// every Space, full-screen ones included. Clicking it does not take focus from the app in
// front, so ⌘V still lands there; it takes focus only to be typed in or edited. It is made
// hidden at launch, so fn shows it at once.

import type { BrowserWindowConstructorOptions, Rectangle } from "electron";

import type { SaySettings } from "./say-settings.ts";

/** 46 rem: the English at 18 px stays under 64 characters a line. */
export const PANEL_WIDTH = 736;
export const PANEL_MIN_HEIGHT = 120;
export const PANEL_MAX_HEIGHT = 520;
/** Above the Dock, clear of what the person is writing in. */
export const PANEL_MARGIN = 48;

export function panelOptions(preload: string): BrowserWindowConstructorOptions {
  return {
    type: "panel",
    width: PANEL_WIDTH,
    height: PANEL_MIN_HEIGHT,
    show: false,
    frame: false,
    transparent: true,
    backgroundColor: "#00000000",
    resizable: false,
    movable: false,
    minimizable: false,
    maximizable: false,
    fullscreenable: false,
    skipTaskbar: true,
    focusable: false,
    hasShadow: true,
    roundedCorners: true,
    // Follows light and dark, as macOS's own translucent panels do; active even though the
    // panel is never the key window.
    vibrancy: "popover",
    visualEffectState: "active",
    webPreferences: {
      preload,
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
      // Hidden between uses, and it has to open the microphone the moment fn goes down.
      backgroundThrottling: false,
    },
  };
}

/**
 * Every Space, full-screen ones included. Asked for without `skipTransformProcessType`,
 * Electron switches the whole app to an agent and back each time, which hides the Dock icon
 * and every window for a moment; a panel-type window floats over full-screen apps without it.
 */
export const PANEL_SPACES = { visibleOnFullScreen: true, skipTransformProcessType: true } as const;

/** Centred, low on the display, its bottom edge fixed while its height follows its content. */
export function placement(workArea: Rectangle, height: number): Rectangle {
  const h = Math.round(Math.min(PANEL_MAX_HEIGHT, Math.max(PANEL_MIN_HEIGHT, height)));
  const w = Math.min(PANEL_WIDTH, workArea.width - 32);
  return {
    x: Math.round(workArea.x + (workArea.width - w) / 2),
    y: Math.round(workArea.y + workArea.height - h - PANEL_MARGIN),
    width: w,
    height: h,
  };
}

/**
 * Whether closing the last window quits the app. Not while Say it in English is on: the
 * key works all day from the menu bar, and Quit stops everything as before.
 */
export function quitsWhenWindowsClose(settings: SaySettings): boolean {
  return !settings.enabled;
}
