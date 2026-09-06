/**
 * Which section owns the address.
 *
 * Everything else about the rail is asserted through the shell it only ever renders
 * inside. This is the one piece of it with a decision in it, and the decision is easy to
 * get wrong in the direction that looks fine: a plain `startsWith` passes every test
 * anybody would think to write and then lights up "Read aloud" for a future `/reading-list`
 * — leaving two sections marked at once, which is the same as none, because the current
 * section is the whole of the wayfinding here.
 */

import { isCurrent } from "@/components/AppSidebar";

test("a section owns its own address", () => {
  expect(isCurrent("/progress", "/progress")).toBe(true);
});

test("a section owns everything under it", () => {
  expect(isCurrent("/sessions/12", "/sessions")).toBe(true);
  expect(isCurrent("/read/third-street-theatre", "/read")).toBe(true);
});

test("it does not own an address that merely starts with its name", () => {
  expect(isCurrent("/reading-list", "/read")).toBe(false);
  expect(isCurrent("/progressive", "/progress")).toBe(false);
});

test("sections do not claim each other", () => {
  expect(isCurrent("/scenarios/job-interview-backend", "/sessions")).toBe(false);
  expect(isCurrent("/home", "/read")).toBe(false);
});
