/**
 * A version beside what was said: the person's changed words struck, the version's
 * marked, and nothing at all when the version kept every word.
 */

import { render, screen } from "@testing-library/react";

import { ChangedWords } from "@/components/ChangedWords";

const steps = [
  { said: "about", version: "about" },
  { said: "my", version: "my" },
  { said: "date", version: "day," },
  { said: "and", version: "and" },
  { said: null, version: "a" },
  { said: "implementation", version: "implementations." },
];

test("strikes the words of yours a version changed and marks its own in their place", () => {
  render(<ChangedWords steps={steps} />);

  const deleted = screen.getAllByRole("deletion").map((node) => node.textContent);
  const inserted = screen.getAllByRole("insertion").map((node) => node.textContent);
  expect(deleted).toEqual(["you had date", "you had implementation"]);
  expect(inserted).toEqual(["this version has day,", "this version has a", "this version has implementations."]);
  expect(screen.getByTestId("changed-words")).toHaveTextContent("3 words changed from yours");
});

test("says nothing when only case or punctuation differ", () => {
  const { container } = render(
    <ChangedWords
      steps={[
        { said: "well", version: "Well," },
        { said: "first", version: "first," },
      ]}
    />,
  );

  expect(container).toBeEmptyDOMElement();
});
