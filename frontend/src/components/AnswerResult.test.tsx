/**
 * One answer, counted: the delivery, the signposts marked on the words, and the model's
 * feedback in each of the states it can arrive in.
 */

import { render, screen, within } from "@testing-library/react";

import { AnswerFeedbackCard } from "@/components/AnswerFeedbackCard";
import { AnswerResult } from "@/components/AnswerResult";
import { MarkedTranscript } from "@/components/MarkedTranscript";
import { makeAnswer } from "@/test/fixtures";

test("the delivery and the signposts are shown as counts", () => {
  render(<AnswerResult answer={makeAnswer()} />);

  expect(screen.getByRole("heading", { name: "Your answer" })).toBeInTheDocument();
  expect(screen.getByText("words in 0:09")).toBeInTheDocument();
  expect(screen.getByText("115")).toBeInTheDocument();
  expect(screen.getByText("12%")).toBeInTheDocument();
  const signposts = screen.getByRole("list", { name: "Signposts" });
  expect(within(signposts).getByText("a reason").parentElement).toHaveTextContent("1");
  expect(within(signposts).getByText("summing up").parentElement).toHaveTextContent("1");
  expect(screen.getByText(/3 sentences, 6 words each on average, the longest 9/)).toBeInTheDocument();
  expect(screen.getByText(/1 time a word or phrase was said twice/)).toBeInTheDocument();
});

test("a measure that did not clear its bar is not mentioned", () => {
  const answer = makeAnswer();
  render(
    <AnswerResult
      answer={{ ...answer, structure: { ...answer.structure, sentences: null, repeats: null } }}
    />,
  );

  expect(screen.queryByText(/sentences, /)).not.toBeInTheDocument();
  expect(screen.queryByText(/said twice\./)).not.toBeInTheDocument();
});

test("an answer said again is headed as one", () => {
  render(<AnswerResult answer={makeAnswer({ again_of: 3 })} />);

  expect(screen.getByRole("heading", { name: "Said again" })).toBeInTheDocument();
});

test("each signpost is marked on its own words, with its kind named for a screen reader", () => {
  const answer = makeAnswer();
  render(<MarkedTranscript transcript={answer.transcript} found={answer.structure.found} />);

  const marks = screen.getByTestId("marked-transcript").querySelectorAll("mark");
  expect(Array.from(marks).map((mark) => mark.textContent)).toEqual([
    "a reason: because",
    "said twice: We we",
    "summing up: In short",
  ]);
  // The words between the marks are there as said; the marks carry their kind as well.
  expect(screen.getByTestId("marked-transcript")).toHaveTextContent(
    "The release broke checkout a reason: because a field was missing.",
  );
  expect(screen.getByRole("list", { name: "Key" })).toHaveTextContent("a reason");
});

test("feedback that passed its check shows the note and the shorter answer", () => {
  render(<AnswerFeedbackCard feedback={makeAnswer().feedback} />);

  expect(screen.getByText("Say first that a missing field broke checkout.")).toBeInTheDocument();
  expect(screen.getByText("rolling back")).toBeInTheDocument();
  expect(screen.getByTestId("rewrite")).toHaveTextContent("A missing field broke checkout");
  expect(screen.getByText(/It did not hear you/)).toBeInTheDocument();
});

test("a withheld rewrite says so, and which words withheld it", () => {
  const feedback = {
    ...makeAnswer().feedback!,
    status: "refused" as const,
    rewrite: null,
    invented: ["Android", "300"],
  };
  render(<AnswerFeedbackCard feedback={feedback} />);

  expect(screen.queryByTestId("rewrite")).not.toBeInTheDocument();
  expect(screen.getByTestId("rewrite-withheld")).toHaveTextContent("“Android”, “300”");
});

test("a model that did not answer is said plainly, and the counts are said to be unaffected", () => {
  const feedback = {
    ...makeAnswer().feedback!,
    status: "unavailable" as const,
    lead: null,
    gaps: [],
    rewrite: null,
  };
  render(<AnswerFeedbackCard feedback={feedback} />);

  expect(screen.getByText(/did not answer this time/)).toHaveTextContent(/counted above is unaffected/);
});
