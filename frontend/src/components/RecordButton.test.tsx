/**
 * The control, in each of its four states, driven by a pointer and by a keyboard.
 *
 * The keyboard tests are not an accessibility afterthought here. Recording has to be
 * keyboard-operable, and a held gesture is the one interaction where the
 * keyboard genuinely differs from a click — Space has to start on keydown and stop on
 * keyup, and the browser's own "Space activates a button on keyup" behaviour has to be
 * suppressed or every recording ends with a second, empty one.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { RecordButton } from "@/components/RecordButton";

function setup(phase: Parameters<typeof RecordButton>[0]["phase"] = "idle") {
  const onStart = jest.fn();
  const onStop = jest.fn();
  render(<RecordButton phase={phase} onStart={onStart} onStop={onStop} elapsedMs={1500} />);
  return { onStart, onStop, user: userEvent.setup(), button: screen.getByRole("button") };
}

test("idle invites the gesture and says how", () => {
  setup("idle");

  expect(screen.getByRole("button", { name: "Hold to speak" })).toBeEnabled();
  expect(screen.getByRole("button")).toHaveAttribute("aria-pressed", "false");
  expect(screen.getByText(/hold the button/i)).toBeInTheDocument();
});

test("holding the pointer starts, releasing stops", async () => {
  const { onStart, onStop, user, button } = setup("idle");

  await user.pointer({ keys: "[MouseLeft>]", target: button });
  expect(onStart).toHaveBeenCalledTimes(1);
  expect(onStop).not.toHaveBeenCalled();

  await user.pointer({ keys: "[/MouseLeft]", target: button });
  // The parent re-renders into "recording"; this instance never does, so the release is
  // a no-op here. What matters is that no second start was fired by the synthetic click.
  expect(onStart).toHaveBeenCalledTimes(1);
});

test("releasing while recording sends the turn", async () => {
  const { onStop, user, button } = setup("recording");

  await user.pointer({ keys: "[MouseLeft>]", target: button });
  await user.pointer({ keys: "[/MouseLeft]", target: button });

  expect(onStop).toHaveBeenCalledTimes(1);
});

test("Space is the same held gesture, not a click", async () => {
  const { onStart, user, button } = setup("idle");

  button.focus();
  await user.keyboard("[Space>]");

  expect(onStart).toHaveBeenCalledTimes(1);
});

test("holding Space does not restart on every key repeat", () => {
  // A held key auto-repeats: the browser sends keydown over and over with `repeat` set.
  // `user-event` has no notion of auto-repeat, so this is the one place a raw event is
  // the honest way to reproduce what a finger on the space bar actually does.
  const { onStart, button } = setup("idle");

  button.focus();
  fireEvent.keyDown(button, { key: " " });
  fireEvent.keyDown(button, { key: " ", repeat: true });
  fireEvent.keyDown(button, { key: " ", repeat: true });

  expect(onStart).toHaveBeenCalledTimes(1);
});

test("releasing Space while recording stops, exactly once", async () => {
  const { onStop, user, button } = setup("recording");

  button.focus();
  await user.keyboard("[Space>][/Space]");

  // Once, not twice: the browser's own activation on keyup is suppressed. Without that
  // preventDefault this is 2, and the second gesture records nothing.
  expect(onStop).toHaveBeenCalledTimes(1);
});

test("recording announces itself as pressed and shows a clock", () => {
  setup("recording");

  const button = screen.getByRole("button");
  expect(button).toHaveAttribute("aria-pressed", "true");
  expect(button).toHaveAccessibleName("Recording — release to send");
  expect(screen.getByText(/Recording 1.5s/)).toBeInTheDocument();
});

test("a turn in flight cannot start another one", async () => {
  const { onStart, user, button } = setup("uploading");

  await user.pointer({ keys: "[MouseLeft>]", target: button });
  button.focus();
  await user.keyboard("[Space>]");

  expect(onStart).not.toHaveBeenCalled();
  expect(button).toHaveAccessibleName("Sending your turn");
});

test("the microphone stays shut while the reply is speaking", async () => {
  // Recording over the speakers feeds the persona's own voice back into the recogniser.
  const { onStart, user, button } = setup("playing");

  await user.pointer({ keys: "[MouseLeft>]", target: button });

  expect(onStart).not.toHaveBeenCalled();
  expect(button).toHaveAccessibleName("Playing the reply");
});

test("an unsupported browser gets a disabled control, not a dead one", () => {
  setup("disabled");

  expect(screen.getByRole("button")).toBeDisabled();
  expect(screen.getByRole("button")).toHaveAccessibleName("Recording is unavailable");
});

test("losing focus mid-recording stops it", async () => {
  const { onStop, user, button } = setup("recording");

  button.focus();
  await user.tab();

  expect(onStop).toHaveBeenCalled();
});
