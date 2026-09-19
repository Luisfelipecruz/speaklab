import { plural } from "@/lib/format";

test("one takes the singular, everything else the plural", () => {
  expect(plural(1, "turn")).toBe("1 turn");
  expect(plural(0, "turn")).toBe("0 turns");
  expect(plural(2, "conversation")).toBe("2 conversations");
});

test("an irregular plural is given, not guessed", () => {
  expect(plural(1, "reading", "readings")).toBe("1 reading");
  expect(plural(3, "sitting", "sittings")).toBe("3 sittings");
});
