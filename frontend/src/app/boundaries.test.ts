/**
 * Every signed-in page has a loading state of its own, and the app has its error and
 * not-found pages.
 *
 * Read off the file tree rather than asserted page by page, because the page that lacks
 * one is the page added next. A section without its own `loading.tsx` borrows the nearest
 * one above it, so a scenario would load under the catalogue's grid of cards; this test
 * names the page instead.
 */

import fs from "fs";
import path from "path";

const APP = path.join(__dirname);
const SIGNED_IN = path.join(APP, "(app)");

function pageDirectories(root: string): string[] {
  const found: string[] = [];
  for (const entry of fs.readdirSync(root, { withFileTypes: true })) {
    const full = path.join(root, entry.name);
    if (entry.isDirectory()) found.push(...pageDirectories(full));
    else if (entry.name === "page.tsx") found.push(root);
  }
  return found;
}

test("every signed-in page has its own loading state", () => {
  const missing = pageDirectories(SIGNED_IN)
    .filter((dir) => !fs.existsSync(path.join(dir, "loading.tsx")))
    .map((dir) => path.relative(APP, dir));

  expect(missing).toEqual([]);
});

test.each([
  "(app)/error.tsx",
  "(app)/not-found.tsx",
  "(app)/loading.tsx",
  "error.tsx",
  "global-error.tsx",
  "not-found.tsx",
])("%s exists", (file) => {
  expect(fs.existsSync(path.join(APP, file))).toBe(true);
});
