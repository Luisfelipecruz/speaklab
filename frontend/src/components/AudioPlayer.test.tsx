/**
 * The properties under test are the three the component's own docstring calls
 * requirements rather than polish — keyboard operation, a caption slot, and a visible
 * error state — plus `autoPlay` and `onPlayingChange`.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { AudioPlayer } from "@/components/AudioPlayer";

beforeEach(() => jest.clearAllMocks());

test("it is a real button and a real slider, so the keyboard works for free", async () => {
  render(<AudioPlayer src="http://localhost:8002/audio/7" label="the reply" durationMs={4000} />);

  const play = screen.getByRole("button", { name: "Play the reply" });
  await userEvent.click(play);

  expect(window.HTMLMediaElement.prototype.play).toHaveBeenCalled();
  expect(screen.getByRole("slider", { name: "Seek within the reply" })).toBeEnabled();
});

test("the caption is rendered, because synthesised speech has to be captioned", () => {
  render(<AudioPlayer src="/audio/7" caption="Over what period?" />);

  expect(screen.getByText("Over what period?")).toBeInTheDocument();
});

test("audio that cannot be loaded says so instead of sitting there looking idle", () => {
  render(<AudioPlayer src="/audio/nope" label="the reply" />);

  fireEvent.error(document.querySelector("audio")!);

  expect(screen.getByRole("alert")).toHaveTextContent(/could not be loaded/);
  expect(screen.getByRole("button", { name: /failed to load/ })).toBeDisabled();
});

test("the duration passed in is used before the file has been read", () => {
  render(<AudioPlayer src="/audio/7" durationMs={95_000} />);

  // 1:35 from the prop, not 0:00 from an <audio> element that has loaded no metadata.
  expect(screen.getByText("0:00 / 1:35")).toBeInTheDocument();
});

test("a headerless file reporting an infinite duration does not render Infinity", () => {
  render(<AudioPlayer src="/audio/7" durationMs={4000} />);

  const audio = document.querySelector("audio")!;
  Object.defineProperty(audio, "duration", { configurable: true, value: Infinity });
  fireEvent.loadedMetadata(audio);

  expect(screen.getByText("0:00 / 0:04")).toBeInTheDocument();
});

test("a player that read its file before it mounted still shows the length", () => {
  // A server-rendered page loads the header before React attaches a handler, so
  // loadedmetadata has already fired by the time the component could hear it.
  const duration = jest
    .spyOn(window.HTMLMediaElement.prototype, "duration", "get")
    .mockReturnValue(15.17);
  const readyState = jest
    .spyOn(window.HTMLMediaElement.prototype, "readyState", "get")
    .mockReturnValue(4);

  render(<AudioPlayer src="/audio/129" />);

  expect(screen.getByText("0:00 / 0:15")).toBeInTheDocument();
  duration.mockRestore();
  readyState.mockRestore();
});

test("a length that arrives after the metadata is shown", () => {
  render(<AudioPlayer src="/audio/131" />);

  const audio = document.querySelector("audio")!;
  Object.defineProperty(audio, "duration", { configurable: true, value: 16.07 });
  fireEvent.durationChange(audio);

  expect(screen.getByText("0:00 / 0:16")).toBeInTheDocument();
});

test("an infinite length is worked out by seeking to the end, then back to the start unshown", () => {
  render(<AudioPlayer src="/audio/130" />);

  const audio = document.querySelector("audio")!;
  let length = Infinity;
  let time = 0;
  Object.defineProperty(audio, "duration", { configurable: true, get: () => length });
  Object.defineProperty(audio, "currentTime", {
    configurable: true,
    get: () => time,
    set: (value: number) => {
      time = value;
    },
  });

  fireEvent.loadedMetadata(audio);
  // Chrome's MediaRecorder WebM declares no length; a seek past the end makes it read one.
  expect(time).toBe(Number.MAX_SAFE_INTEGER);
  fireEvent.timeUpdate(audio);
  expect(screen.getByText("0:00 / 0:00")).toBeInTheDocument();

  length = 19.44;
  fireEvent.durationChange(audio);

  expect(time).toBe(0);
  expect(screen.getByText("0:00 / 0:19")).toBeInTheDocument();
});

test("autoPlay speaks on mount and reports that it is playing", () => {
  const onPlayingChange = jest.fn();
  render(<AudioPlayer src="/audio/7" autoPlay onPlayingChange={onPlayingChange} />);

  expect(window.HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(1);

  fireEvent.play(document.querySelector("audio")!);
  expect(onPlayingChange).toHaveBeenCalledWith(true);

  fireEvent.ended(document.querySelector("audio")!);
  expect(onPlayingChange).toHaveBeenLastCalledWith(false);
});

test("an autoplay the browser refuses leaves a working player, not a failed one", async () => {
  // Every browser blocks audio until the page has been interacted with. That is policy,
  // not a broken file, and the `failed` state means something much more alarming.
  (window.HTMLMediaElement.prototype.play as jest.Mock).mockRejectedValueOnce(
    new DOMException("blocked", "NotAllowedError"),
  );

  render(<AudioPlayer src="/audio/7" label="the reply" autoPlay />);

  // Flush the rejected promise the effect swallowed.
  await Promise.resolve();

  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Play the reply" })).toBeEnabled();
});
