/**
 * The waveform, and the reason it exists: a flat line is a diagnosis.
 *
 * The interesting assertion is the silent one. A user whose microphone is muted, or
 * whose OS has selected the wrong input device, sees a granted permission prompt and a
 * button that appears to work — and the only thing in the interface that can tell them
 * otherwise is this. A person who does not know what a waveform looks like cannot read
 * a flat one, so it also says it in words.
 */

import { render, screen, act } from "@testing-library/react";

import { SILENT_AFTER_MS, Waveform } from "@/components/Waveform";

/** An analyser that fills the buffer with a constant, so the level is controllable. */
function analyserAt(level: number): AnalyserNode {
  return {
    fftSize: 1024,
    getByteTimeDomainData: (array: Uint8Array) => array.fill(128 + level),
  } as unknown as AnalyserNode;
}

test("the canvas is hidden from assistive technology", () => {
  const { container } = render(<Waveform analyser={null} active={false} />);

  // It changes sixty times a second. Announcing that would make a screen reader useless,
  // so the state it represents is announced once, as text, below it.
  expect(container.querySelector("canvas")).toHaveAttribute("aria-hidden", "true");
});

test("nothing is announced when nothing is being recorded", () => {
  render(<Waveform analyser={analyserAt(40)} active={false} />);

  expect(screen.getByRole("status")).toHaveTextContent("");
});

test("a live microphone reports that it is listening", () => {
  jest.useFakeTimers();
  render(<Waveform analyser={analyserAt(40)} active />);

  act(() => {
    jest.advanceTimersByTime(100);
  });

  expect(screen.getByRole("status")).toHaveTextContent("Listening.");
  jest.useRealTimers();
});

test("a flat line becomes a sentence about a muted microphone", () => {
  jest.useFakeTimers();
  render(<Waveform analyser={analyserAt(0)} active />);

  act(() => {
    jest.advanceTimersByTime(SILENT_AFTER_MS + 200);
  });

  expect(screen.getByRole("status")).toHaveTextContent(/No sound is reaching the microphone/);
  expect(screen.getByRole("status")).toHaveTextContent(/input device/);
  jest.useRealTimers();
});

test("a brief pause for breath is not reported as a dead microphone", () => {
  jest.useFakeTimers();
  render(<Waveform analyser={analyserAt(0)} active />);

  act(() => {
    jest.advanceTimersByTime(SILENT_AFTER_MS - 400);
  });

  expect(screen.getByRole("status")).toHaveTextContent("Listening.");
  jest.useRealTimers();
});

test("a missing 2d context does not stop the component working", () => {
  // jsdom returns null here, and so does a real browser that has run out of contexts.
  // The message that matters is text, which is why it survives having nowhere to draw.
  jest.useFakeTimers();
  expect(() =>
    render(<Waveform analyser={analyserAt(0)} active />),
  ).not.toThrow();

  act(() => {
    jest.advanceTimersByTime(SILENT_AFTER_MS + 200);
  });
  expect(screen.getByRole("status")).toHaveTextContent(/No sound is reaching/);
  jest.useRealTimers();
});
