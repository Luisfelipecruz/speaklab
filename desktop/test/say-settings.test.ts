import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, it } from "node:test";

import { DEFAULTS, loadSettings, parseSettings, saveSettings } from "../src/say-settings.ts";

describe("the settings", () => {
  let dir = "";

  beforeEach(() => {
    dir = mkdtempSync(join(tmpdir(), "say-settings-"));
  });

  afterEach(() => {
    rmSync(dir, { recursive: true, force: true });
  });

  it("start on, with fn, Organized and Corrected, saving, and not at login", () => {
    assert.deepEqual(loadSettings(join(dir, "say.json")), {
      enabled: true,
      key: "fn",
      fromOwn: "organized",
      fromEnglish: "corrected",
      save: true,
      openAtLogin: false,
    });
  });

  it("keep each field that is right, and give the default for each that is not", () => {
    assert.deepEqual(parseSettings({ key: "shortcuts", save: false, fromOwn: "word for word", enabled: "yes", extra: 1 }), {
      ...DEFAULTS,
      key: "shortcuts",
      save: false,
    });
  });

  it("are the defaults for anything that is not an object", () => {
    for (const raw of [null, undefined, "fn", 7, true]) {
      assert.deepEqual(parseSettings(raw), DEFAULTS, String(raw));
    }
  });

  it("are the defaults when the file is half-written", () => {
    const file = join(dir, "say.json");
    writeFileSync(file, '{"key": "shortc');
    assert.deepEqual(loadSettings(file), DEFAULTS);
  });

  it("come back as saved, from a file only the person can read, with no part file left", () => {
    const file = join(dir, "nested", "say.json");
    const settings = { ...DEFAULTS, key: "shortcuts" as const, fromOwn: "direct" as const, openAtLogin: true };
    saveSettings(file, settings);

    assert.deepEqual(loadSettings(file), settings);
    assert.equal(statSync(file).mode & 0o777, 0o600);
    assert.equal(statSync(join(dir, "nested")).mode & 0o777, 0o700);
    assert.ok(!existsSync(`${file}.part`));
  });

  it("write only the fields they know", () => {
    const file = join(dir, "say.json");
    saveSettings(file, { ...DEFAULTS, ...({ token: "secret" } as object) });

    assert.deepEqual(Object.keys(JSON.parse(readFileSync(file, "utf8")) as object).sort(), Object.keys(DEFAULTS).sort());
  });
});
