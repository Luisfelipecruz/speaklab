/**
 * The theme control.
 *
 * Two things are worth asserting and they are not the same thing. One is that choosing a
 * theme changes the page — the class on `<html>` is what every `dark:` utility keys on.
 * The other is that the choice is *written down*, because a preference that only lasts
 * until the tab is closed is not a preference, it is a fidget.
 *
 * The first render says "system" whatever is stored, deliberately: the server cannot read
 * localStorage, and rendering a guess is a hydration mismatch that blanks the subtree.
 * The test waits for the correction rather than asserting the guess is absent.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { ThemeToggle } from "@/components/ThemeToggle";
import { DARK_CLASS, THEME_STORAGE_KEY } from "@/lib/theme";

beforeEach(() => {
  window.localStorage.clear();
  document.documentElement.classList.remove(DARK_CLASS);
});

/**
 * Open the menu and pick an option with the keyboard.
 *
 * The keyboard rather than the mouse, for two reasons. It is the path more likely to be
 * broken and less likely to be tried by hand, and driving this particular menu with
 * synthesised pointer events costs about eleven seconds per open in jsdom — enough on its
 * own to make the whole frontend suite something people stop running.
 */
function choose(label: string) {
  fireEvent.keyDown(screen.getByRole("button", { name: /^Theme:/ }), { key: "Enter" });
  fireEvent.keyDown(screen.getByRole("menuitem", { name: label }), { key: "Enter" });
}

test("choosing dark turns the page dark and writes the choice down", () => {
  render(<ThemeToggle />);

  choose("Dark");

  expect(document.documentElement).toHaveClass(DARK_CLASS);
  expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");
});

test("choosing light turns it back", () => {
  document.documentElement.classList.add(DARK_CLASS);
  render(<ThemeToggle />);

  choose("Light");

  expect(document.documentElement).not.toHaveClass(DARK_CLASS);
  expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");
});

test("a stored choice is what the control reports once it can read it", async () => {
  window.localStorage.setItem(THEME_STORAGE_KEY, "dark");
  render(<ThemeToggle />);

  await waitFor(() =>
    expect(screen.getByRole("button", { name: "Theme: dark" })).toBeInTheDocument(),
  );
});

test("system is offered, and choosing it forgets the override", () => {
  window.localStorage.setItem(THEME_STORAGE_KEY, "dark");
  render(<ThemeToggle />);

  choose("System");

  expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBeNull();
});
