import { DEFAULT_AFTER_LOGIN, safeNext } from "@/lib/navigation";

test("a path on this site is honoured", () => {
  expect(safeNext("/sessions/12")).toBe("/sessions/12");
  expect(safeNext("/scenarios/job-interview-backend")).toBe("/scenarios/job-interview-backend");
});

test("no destination lands on the signed-in home", () => {
  // Somebody who has just signed in wants to know what to practise, which is a question
  // the catalogue cannot answer because it knows nothing about them.
  expect(DEFAULT_AFTER_LOGIN).toBe("/home");
  expect(safeNext(null)).toBe(DEFAULT_AFTER_LOGIN);
  expect(safeNext("")).toBe(DEFAULT_AFTER_LOGIN);
});

test("another origin is refused", () => {
  expect(safeNext("https://evil.example/login")).toBe(DEFAULT_AFTER_LOGIN);
  expect(safeNext("http://evil.example")).toBe(DEFAULT_AFTER_LOGIN);
});

test("a protocol-relative URL is refused, though it starts with a slash", () => {
  // The check that a naive `startsWith("/")` misses. Browsers resolve `//host/path`
  // against another origin entirely, so this is an external redirect wearing a path's
  // clothes — and it is the exact shape used to turn a login form into a phishing hop.
  expect(safeNext("//evil.example/login")).toBe(DEFAULT_AFTER_LOGIN);
  expect(safeNext("//evil.example")).toBe(DEFAULT_AFTER_LOGIN);
});
