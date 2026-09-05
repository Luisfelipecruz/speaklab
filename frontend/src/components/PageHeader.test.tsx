/**
 * Width, and the heading block above it.
 *
 * The shell used to cap every screen at the same 1024 px, so a paragraph and a heatmap of
 * forty sounds got exactly the same room. What replaces it is three named answers rather
 * than a free value, and the test that matters is that they are actually different from
 * each other — a refactor that collapsed them to one class would restore the old problem
 * while every page still read as though it had made a choice.
 */

import { render, screen } from "@testing-library/react";

import { Page, PageHeader } from "@/components/PageHeader";

test("the three measures are three different measures", () => {
  const widths = (["prose", "wide", "full"] as const).map((width) => {
    const { container, unmount } = render(<Page width={width}>content</Page>);
    const className = (container.firstElementChild as HTMLElement).className;
    unmount();
    return className.split(" ").find((token) => token.startsWith("max-w-"));
  });

  expect(widths.every(Boolean)).toBe(true);
  expect(new Set(widths).size).toBe(3);
});

test("a page can add to its own layout without losing its measure", () => {
  const { container } = render(
    <Page width="wide" className="gap-6">
      content
    </Page>,
  );

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
