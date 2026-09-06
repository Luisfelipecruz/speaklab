/**
 * The measure, and the heading block above it.
 *
 * Every screen used to pick one of three container widths, so moving between sections
 * moved the left edge of the content. What replaces it is one measure for all of them, and
 * a narrower column that running text can opt into *inside* a page — the distinction the
 * old design lost. The test that matters is that `Prose` narrows itself without `Page`
 * changing, because the obvious refactor is to push the measure back up to the frame and
 * that would restore the original problem while every page still looked deliberate.
 */

import { render, screen } from "@testing-library/react";

import { Page, PageHeader, Prose } from "@/components/PageHeader";

test("every page gets the same measure", () => {
  const measures = ["one", "two"].map((content) => {
    const { container, unmount } = render(<Page>{content}</Page>);
    const className = (container.firstElementChild as HTMLElement).className;
    unmount();
    return className.split(" ").find((token) => token.startsWith("max-w-"));
  });

  expect(measures[0]).toBeDefined();
  expect(measures[0]).toBe(measures[1]);
});

test("running text narrows itself without the page around it changing", () => {
  const { container } = render(
    <Page>
      <Prose>a paragraph</Prose>
    </Page>,
  );

  const page = container.firstElementChild as HTMLElement;
  const prose = page.firstElementChild as HTMLElement;

  const pageMeasure = page.className.split(" ").find((t) => t.startsWith("max-w-"));
  const proseMeasure = prose.className.split(" ").find((t) => t.startsWith("max-w-"));

  expect(proseMeasure).toBeDefined();
  expect(proseMeasure).not.toBe(pageMeasure);
});

test("a page can add to its own layout without losing its measure", () => {
  const { container } = render(<Page className="gap-6">content</Page>);

  const root = container.firstElementChild as HTMLElement;
  expect(root).toHaveClass("gap-6");
  expect(root.className).toMatch(/max-w-/);
});

test("the title is the page's heading, not a styled paragraph", () => {
  render(<PageHeader title="Your progress" description="Weeks from A to B." />);

  expect(
    screen.getByRole("heading", { level: 1, name: "Your progress" }),
  ).toBeInTheDocument();
  expect(screen.getByText("Weeks from A to B.")).toBeInTheDocument();
});

test("a page with nothing to say about itself renders only its title", () => {
  render(<PageHeader title="Status" />);

  expect(screen.getByRole("heading", { level: 1, name: "Status" })).toBeInTheDocument();
});

test("actions sit in the header rather than being pushed off it", () => {
  render(<PageHeader title="Your progress" actions={<button>Rebuild</button>} />);

  const header = screen.getByRole("banner");
  expect(header).toContainElement(screen.getByRole("button", { name: "Rebuild" }));
});

test("an eyebrow sits above the title without becoming part of its name", () => {
  render(<PageHeader eyebrow={<span>B2</span>} title="Apartment viewing" />);

  expect(
    screen.getByRole("heading", { level: 1, name: "Apartment viewing" }),
  ).toBeInTheDocument();
  expect(screen.getByText("B2")).toBeInTheDocument();
});
