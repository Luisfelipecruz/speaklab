/**
 * The front door shows the product before it describes it: the conversation screen and
 * the names of the models sit above the three claims, and no engineer's term reaches
 * the sentence a stranger reads first.
 */

import { render, screen } from "@testing-library/react";

import Home from "@/app/page";

test("the product is on the page: one sentence, the conversation screen, the stack", () => {
  render(<Home />);

  expect(screen.getByRole("heading", { level: 1, name: "SpeakLab" })).toBeInTheDocument();
  expect(screen.getByRole("img", { name: /A conversation in SpeakLab/ })).toBeInTheDocument();
  for (const part of ["Whisper", "Gemma 4", "Piper", "wav2vec2", "your machine"]) {
    expect(screen.getByText(part)).toBeInTheDocument();
  }
});

test("the ways in are the same two links, and the status page is named last", () => {
  render(<Home />);

  expect(screen.getByRole("link", { name: "Start practising" })).toHaveAttribute("href", "/home");
  expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login");
  expect(screen.getByRole("link", { name: "Service status" })).toHaveAttribute("href", "/status");
});

test("the first sentence speaks to a learner, not an engineer", () => {
  const { container } = render(<Home />);

  const header = container.querySelector("header");
  expect(header).not.toHaveTextContent(/GOP/);
  expect(header).not.toHaveTextContent(/phoneme/i);
  expect(header).toHaveTextContent(/counted from what you said/);
});
