/**
 * Light or dark, and the one hard part of it.
 *
 * The hard part is not the toggle — it is that the choice has to be on the `<html>`
 * element *before the browser paints anything*. A theme applied from a React effect runs
 * after hydration, which for somebody who chose dark means a white page for a few hundred
 * milliseconds on every single navigation. That flash is the reason this is a synchronous
 * script in `<head>` rather than a `useEffect`, and it is why the source below is a string
 * instead of a function: it has to run before the bundle exists.
 *
 * **A string of code and a set of functions describing the same rule is a drift risk**, so
 * the two are held together by a test that runs the string and compares the class it sets
 * against the class `apply(read())` sets. Change one and the other has to follow.
 *
 * Three states, not two. "System" is a real answer and it is the default: somebody who has
 * told their operating system they prefer dark has already expressed the preference, and
 * asking them again is the kind of question a product asks when it has not been thought
 * about. Only an explicit choice is stored.
 */

export type Theme = "light" | "dark" | "system";

export const THEME_STORAGE_KEY = "speaklab-theme";

/** The class Tailwind's dark variant is keyed on. Set on `<html>`, read by `&:is(.dark *)`. */
export const DARK_CLASS = "dark";

export function isTheme(value: unknown): value is Theme {
  return value === "light" || value === "dark" || value === "system";
}

/**
 * The stored choice, or "system".
 *
 * Wrapped because `localStorage` is not merely empty in a private window or with cookies
 * blocked — reading it *throws*, and an exception here would happen before the app
 * renders and take the whole page with it.
 */
export function readStoredTheme(): Theme {
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    return isTheme(stored) ? stored : "system";
  } catch {
    return "system";
  }
}

export function storeTheme(theme: Theme): void {
  try {
    if (theme === "system") window.localStorage.removeItem(THEME_STORAGE_KEY);
    else window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // A browser that refuses storage still gets the theme it asked for for this page.
    // Silently keeping the visual change is the better of the two failures.
  }
}

/** Whether a choice resolves to dark, consulting the operating system for "system". */
export function prefersDark(theme: Theme): boolean {
  if (theme !== "system") return theme === "dark";
  // Absent in jsdom and in any browser old enough not to matter here; "not dark" is the
  // right answer when the question cannot be asked.
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
}

export function applyTheme(theme: Theme): void {
  document.documentElement.classList.toggle(DARK_CLASS, prefersDark(theme));
}

/**
 * The same rule, small enough to inline in `<head>` and run before first paint.
 *
 * Deliberately not the functions above: this executes before any module has loaded. It is
 * wrapped in its own try/catch for the same reason `readStoredTheme` is — a throw here is
 * a throw in `<head>`, which is a blank page rather than a mis-coloured one.
 */
export const PRE_PAINT_SCRIPT = `
try {
  var stored = window.localStorage.getItem(${JSON.stringify(THEME_STORAGE_KEY)});
  var dark = stored === "dark" || ((stored !== "light") &&
    !!(window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches));
  document.documentElement.classList.toggle(${JSON.stringify(DARK_CLASS)}, dark);
} catch (error) {}
`.trim();
