import { render, screen } from "@testing-library/react";

import { PageSkeleton, type SkeletonShape } from "@/components/PageSkeleton";

test("a loading page says so in words, not only in grey", () => {
  render(<PageSkeleton shape="cards" label="Loading the scenarios" />);

  expect(screen.getByRole("status")).toHaveTextContent("Loading the scenarios");
});

test("the grey blocks are hidden from a screen reader", () => {
  const { container } = render(<PageSkeleton shape="list" label="Loading" />);

  const blocks = container.querySelectorAll('[data-slot="skeleton"]');
  expect(blocks.length).toBeGreaterThan(0);
  for (const block of blocks) {
    expect(block.closest('[aria-hidden="true"]')).not.toBeNull();
  }
});

test.each<SkeletonShape>(["cards", "list", "tiles", "document"])(
  "the %s shape draws a body under the heading",
  (shape) => {
    const { container } = render(<PageSkeleton shape={shape} label="Loading" />);

    expect(screen.getByRole("status")).toHaveAttribute("data-shape", shape);
    // The heading block is two; anything past that is the body.
    expect(container.querySelectorAll('[data-slot="skeleton"]').length).toBeGreaterThan(2);
  },
);
