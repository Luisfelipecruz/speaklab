/**
 * The tabs, and the two things that make them links rather than a widget.
 *
 * The section a reader is in has to be announced, not only shaded — the whole point of the
 * row is saying where you are, and colour alone says it to nobody using a screen reader.
 * And every tab has to be a real href, because the state lives in the URL and a button
 * would take that away from the back button and from sharing.
 */

import { render, screen } from "@testing-library/react";

import { SectionTabs } from "@/components/SectionTabs";

const SECTIONS = [
  { key: "overview", label: "Overview", href: "/progress" },
  { key: "fluency", label: "How you speak", href: "/progress?view=fluency" },
  { key: "accuracy", label: "What you get wrong", href: "/progress?view=accuracy" },
];

test("every section is a link with an address of its own", () => {
  render(<SectionTabs label="Progress sections" sections={SECTIONS} current="overview" />);

  const links = screen.getAllByRole("link");
  expect(links.map((link) => link.getAttribute("href"))).toEqual([
    "/progress",
    "/progress?view=fluency",
    "/progress?view=accuracy",
  ]);
});

test("the section being read is marked, and it is the only one", () => {
  render(<SectionTabs label="Progress sections" sections={SECTIONS} current="fluency" />);

  const marked = screen
    .getAllByRole("link")
    .filter((link) => link.getAttribute("aria-current") === "page");

  expect(marked).toHaveLength(1);
  expect(marked[0]).toHaveTextContent("How you speak");
});

test("the row is a named landmark, so it can be skipped to and skipped over", () => {
  render(<SectionTabs label="Progress sections" sections={SECTIONS} current="overview" />);

  expect(screen.getByRole("navigation", { name: "Progress sections" })).toBeInTheDocument();
});
