import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  PANEL_MARGIN,
  PANEL_MAX_HEIGHT,
  PANEL_MIN_HEIGHT,
  PANEL_SPACES,
  PANEL_WIDTH,
  panelOptions,
  placement,
  quitsWhenWindowsClose,
} from "../src/panel.ts";
import { DEFAULTS } from "../src/say-settings.ts";

describe("the panel window", () => {
  const options = panelOptions("/app/static/panel-preload.cjs");

  it("is a hidden, non-activating panel that never takes focus on its own", () => {
    assert.equal(options.type, "panel");
    assert.equal(options.show, false);
    assert.equal(options.focusable, false);
    assert.equal(options.skipTaskbar, true);
    assert.equal(options.frame, false);
    assert.equal(options.transparent, true);
    assert.equal(options.resizable, false);
    assert.equal(options.fullscreenable, false);
  });

  it("joins every Space, full-screen ones too, without turning the whole app into an agent", () => {
    assert.deepEqual(PANEL_SPACES, { visibleOnFullScreen: true, skipTransformProcessType: true });
  });

  it("follows light and dark through the system's own translucency", () => {
    assert.equal(options.vibrancy, "popover");
    assert.equal(options.visualEffectState, "active");
  });

  it("runs its page sandboxed, with only its preload, and keeps it awake while hidden", () => {
    assert.deepEqual(options.webPreferences, {
      preload: "/app/static/panel-preload.cjs",
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
      backgroundThrottling: false,
    });
  });
});

describe("where the panel goes", () => {
  const laptop = { x: 0, y: 38, width: 1512, height: 944 };

  it("is centred, low, above the Dock by a margin", () => {
    assert.deepEqual(placement(laptop, 200), {
      x: (1512 - PANEL_WIDTH) / 2,
      y: 38 + 944 - 200 - PANEL_MARGIN,
      width: PANEL_WIDTH,
      height: 200,
    });
  });

  it("keeps its bottom edge where it is as its height follows the content", () => {
    const short = placement(laptop, 150);
    const tall = placement(laptop, 400);
    assert.equal(short.y + short.height, tall.y + tall.height);
  });

  it("holds its height between the least and the most", () => {
    assert.equal(placement(laptop, 10).height, PANEL_MIN_HEIGHT);
    assert.equal(placement(laptop, 5000).height, PANEL_MAX_HEIGHT);
  });

  it("fits a narrow display, and a display that is not the first", () => {
    assert.deepEqual(placement({ x: -800, y: 0, width: 600, height: 900 }, 200), {
      x: -800 + 16,
      y: 900 - 200 - PANEL_MARGIN,
      width: 600 - 32,
      height: 200,
    });
  });
});

describe("closing the last window", () => {
  it("does not quit while Say it in English is on, and quits as before when it is off", () => {
    assert.equal(quitsWhenWindowsClose(DEFAULTS), false);
    assert.equal(quitsWhenWindowsClose({ ...DEFAULTS, enabled: false }), true);
  });
});
