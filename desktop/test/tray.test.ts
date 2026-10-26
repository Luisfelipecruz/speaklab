import assert from "node:assert/strict";
import { describe, it } from "node:test";

import type { MenuItemConstructorOptions } from "electron";

import { DEFAULTS } from "../src/say-settings.ts";
import { hint, ICON_PX, iconBitmap, type TrayActions, type TrayState, trayMenu } from "../src/tray.ts";

function state(over: Partial<TrayState> = {}): TrayState {
  return { settings: DEFAULTS, access: true, language: "Spanish", ...over };
}

function recorder() {
  const calls: string[] = [];
  const actions: TrayActions = {
    type: () => calls.push("type"),
    copied: () => calls.push("copied"),
    fromOwn: (version) => calls.push(`fromOwn ${version}`),
    save: (on) => calls.push(`save ${on}`),
    notebook: () => calls.push("notebook"),
    settings: () => calls.push("settings"),
    quit: () => calls.push("quit"),
  };
  return { calls, actions };
}

function item(menu: MenuItemConstructorOptions[], label: string): MenuItemConstructorOptions {
  const found = menu.find((entry) => entry.label === label);
  assert.ok(found, `no item "${label}"`);
  return found;
}

/** A click as Electron makes it; the menu's handlers use none of its arguments. */
function click(entry: MenuItemConstructorOptions): void {
  (entry.click as unknown as () => void)();
}

describe("the menu bar icon", () => {
  const pixels = iconBitmap();

  it("is an 18-point template image at 2x: shape in alpha, colour left black", () => {
    assert.equal(pixels.length, ICON_PX * ICON_PX * 4);
    for (let i = 0; i < pixels.length; i += 4) {
      assert.equal(pixels[i]! | pixels[i + 1]! | pixels[i + 2]!, 0);
    }
  });

  it("has solid bars and clear corners", () => {
    const alpha = (x: number, y: number) => pixels[(y * ICON_PX + x) * 4 + 3];
    assert.equal(alpha(0, 0), 0);
    assert.equal(alpha(ICON_PX - 1, ICON_PX - 1), 0);
    assert.ok([...Array(ICON_PX * ICON_PX).keys()].some((i) => pixels[i * 4 + 3] === 255));
    // The middle bar, the tallest, runs through the centre.
    assert.equal(alpha(ICON_PX / 2, ICON_PX / 2), 255);
  });
});

describe("the menu", () => {
  it("leads with how to start, or with what stops fn", () => {
    assert.equal(hint(state()), "Hold fn to say it in English");
    assert.equal(hint(state({ access: null })), "Hold fn to say it in English");
    assert.equal(hint(state({ access: false })), "fn needs Input Monitoring: see Settings");
    assert.equal(hint(state({ settings: { ...DEFAULTS, key: "shortcuts" }, access: false })), "⌃⌥Space to say it in English");
  });

  it("lists the ways in, the version, saving, and the windows, in that order", () => {
    const labels = trayMenu(state(), recorder().actions)
      .filter((entry) => entry.type !== "separator")
      .map((entry) => entry.label);
    assert.deepEqual(labels, [
      "Hold fn to say it in English",
      "Type in the panel",
      "Translate or check what I copied",
      "From Spanish: Organized",
      "From Spanish: Direct",
      "Save to Notebook",
      "Open Notebook",
      "Settings…",
      "Quit SpeakLab",
    ]);
  });

  it("checks the version copied from the person's language and whether saving is on", () => {
    const menu = trayMenu(state({ settings: { ...DEFAULTS, fromOwn: "direct", save: false } }), recorder().actions);
    assert.equal(item(menu, "From Spanish: Organized").checked, false);
    assert.equal(item(menu, "From Spanish: Direct").checked, true);
    assert.equal(item(menu, "Save to Notebook").checked, false);
  });

  it("hands each click to its action, saving flipped from what it is", () => {
    const { calls, actions } = recorder();
    const menu = trayMenu(state(), actions);
    for (const label of ["Type in the panel", "Translate or check what I copied", "From Spanish: Direct", "Save to Notebook", "Open Notebook", "Settings…", "Quit SpeakLab"]) {
      click(item(menu, label));
    }
    assert.deepEqual(calls, ["type", "copied", "fromOwn direct", "save false", "notebook", "settings", "quit"]);
  });

  it("shows the shortcuts it registers", () => {
    const menu = trayMenu(state(), recorder().actions);
    assert.equal(item(menu, "Type in the panel").accelerator, "Control+Alt+Space");
    assert.equal(item(menu, "Translate or check what I copied").accelerator, "Control+Alt+C");
  });

  it("names the language it does not know yet as the person's own", () => {
    const menu = trayMenu(state({ language: "your language" }), recorder().actions);
    item(menu, "From your language: Organized");
  });
});
