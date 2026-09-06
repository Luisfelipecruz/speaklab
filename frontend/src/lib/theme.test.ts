/**
 * Light or dark, and the one thing that can quietly break it.
 *
 * The rule lives twice: once as functions the toggle calls, and once as a string of
 * source that runs in `<head>` before any module exists. Two expressions of one rule drift
 * apart, and the drift is invisible — the toggle keeps working and only a *reload* comes
 * back wrong, which is the case nobody clicks through while making a change. So the last
 * test here runs the string and compares what it did against what the functions do.
 */

import {
  applyTheme,
  DARK_CLASS,
  PRE_PAINT_SCRIPT,
  readStoredTheme,
  storeTheme,
  THEME_STORAGE_KEY,
  type Theme,
} from "@/lib/theme";

/** Run the head script the way the browser does. */
function runPrePaintScript(): void {
  new Function(PRE_PAINT_SCRIPT)();
}

function systemPrefersDark(dark: boolean): void {
  window.matchMedia = ((query: string) => ({
    matches: dark,
    media: query,
    addEventListener: jest.fn(),
    removeEventListener: jest.fn(),
  })) as unknown as typeof window.matchMedia;
}

beforeEach(() => {
  window.localStorage.clear();
  document.documentElement.classList.remove(DARK_CLASS);
  systemPrefersDark(false);
});

test("nothing stored means the operating system decides", () => {
  expect(readStoredTheme()).toBe("system");

  systemPrefersDark(true);
  applyTheme("system");
  expect(document.documentElement).toHaveClass(DARK_CLASS);

  systemPrefersDark(false);
  applyTheme("system");
  expect(document.documentElement).not.toHaveClass(DARK_CLASS);
});

test("an explicit choice overrides the operating system in both directions", () => {
  systemPrefersDark(true);
  applyTheme("light");
  expect(document.documentElement).not.toHaveClass(DARK_CLASS);

  systemPrefersDark(false);
  applyTheme("dark");
  expect(document.documentElement).toHaveClass(DARK_CLASS);
});

test("choosing system forgets the choice rather than storing the word", () => {
  // Storing "system" would freeze today's answer: somebody who picks it while their
  // machine is light would stay light after their machine switched to dark.
  storeTheme("dark");
  expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");

  storeTheme("system");
  expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBeNull();
});

test("a value nothing wrote is not trusted", () => {
  window.localStorage.setItem(THEME_STORAGE_KEY, "midnight");
  expect(readStoredTheme()).toBe("system");
});

test("a browser that refuses storage still renders", () => {
  // A private window, or cookies blocked: reading localStorage does not come back empty,
  // it throws — and an exception here happens before the app renders.
  const getItem = jest
    .spyOn(Storage.prototype, "getItem")
    .mockImplementation(() => {
      throw new Error("access denied");
    });
  const setItem = jest
    .spyOn(Storage.prototype, "setItem")
    .mockImplementation(() => {
      throw new Error("access denied");
    });

  expect(readStoredTheme()).toBe("system");
  expect(() => storeTheme("dark")).not.toThrow();

  getItem.mockRestore();
  setItem.mockRestore();
});

test("the choice survives a reload, before anything paints", () => {
  storeTheme("dark");

  // A reload: the class is gone, no module has loaded, and the head script is all there is.
  document.documentElement.classList.remove(DARK_CLASS);
  runPrePaintScript();

  expect(document.documentElement).toHaveClass(DARK_CLASS);
});

test("the head script and the module agree on every case", () => {
  const cases: { stored: Theme | null; system: boolean }[] = [
    { stored: "dark", system: false },
    { stored: "dark", system: true },
    { stored: "light", system: false },
    { stored: "light", system: true },
    { stored: null, system: false },
    { stored: null, system: true },
  ];

  for (const { stored, system } of cases) {
    systemPrefersDark(system);
    window.localStorage.clear();
    if (stored) storeTheme(stored);

    document.documentElement.classList.remove(DARK_CLASS);
    runPrePaintScript();
    const fromScript = document.documentElement.classList.contains(DARK_CLASS);

    document.documentElement.classList.remove(DARK_CLASS);
    applyTheme(readStoredTheme());
    const fromModule = document.documentElement.classList.contains(DARK_CLASS);

    expect({ stored, system, dark: fromScript }).toEqual({
      stored,
      system,
      dark: fromModule,
    });
  }
});
