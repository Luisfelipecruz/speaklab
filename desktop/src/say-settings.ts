// Say it in English's settings, in userData/say.json: whether it is on, the key, the
// version copied by default from each language, whether captures are saved, and starting
// at login. A file that is missing, unreadable or half-written gives the defaults, field
// by field, so a setting the person never touched cannot be lost to one they did.

import { mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";

export interface SaySettings {
  /** The key, the panel and the menu bar. Off, the app behaves as it did without them. */
  enabled: boolean;
  /** Hold fn, or the shortcuts only, for a keyboard without fn. */
  key: "fn" | "shortcuts";
  /** What goes on the clipboard from the person's own language. */
  fromOwn: "organized" | "direct";
  /** What goes on the clipboard from English. */
  fromEnglish: "corrected" | "polished";
  /** Captures are kept in the Notebook; off, nothing reaches it. */
  save: boolean;
  openAtLogin: boolean;
}

export const DEFAULTS: SaySettings = {
  enabled: true,
  key: "fn",
  fromOwn: "organized",
  fromEnglish: "corrected",
  save: true,
  openAtLogin: false,
};

function one<T extends string>(value: unknown, allowed: readonly T[], fallback: T): T {
  return allowed.includes(value as T) ? (value as T) : fallback;
}

function flag(value: unknown, fallback: boolean): boolean {
  return typeof value === "boolean" ? value : fallback;
}

export function parseSettings(raw: unknown): SaySettings {
  const given = raw && typeof raw === "object" ? (raw as Record<string, unknown>) : {};
  return {
    enabled: flag(given.enabled, DEFAULTS.enabled),
    key: one(given.key, ["fn", "shortcuts"] as const, DEFAULTS.key),
    fromOwn: one(given.fromOwn, ["organized", "direct"] as const, DEFAULTS.fromOwn),
    fromEnglish: one(given.fromEnglish, ["corrected", "polished"] as const, DEFAULTS.fromEnglish),
    save: flag(given.save, DEFAULTS.save),
    openAtLogin: flag(given.openAtLogin, DEFAULTS.openAtLogin),
  };
}

export function loadSettings(file: string): SaySettings {
  try {
    return parseSettings(JSON.parse(readFileSync(file, "utf8")));
  } catch {
    return { ...DEFAULTS };
  }
}

/** Written whole and then moved into place, so a crash mid-write leaves the last good file. */
export function saveSettings(file: string, settings: SaySettings): void {
  mkdirSync(dirname(file), { recursive: true, mode: 0o700 });
  const part = `${file}.part`;
  writeFileSync(part, `${JSON.stringify(parseSettings(settings), null, 2)}\n`, { mode: 0o600 });
  renameSync(part, file);
}
