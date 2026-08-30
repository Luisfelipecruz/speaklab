/**
 * What every test gets before it starts.
 *
 * Two kinds of thing live here and they are worth telling apart.
 *
 * The first is jest-dom, which adds the assertions (`toBeInTheDocument`,
 * `toBeDisabled`) that make a failing test say what was on the screen instead of
 * printing a null.
 *
 * The second is the browser APIs jsdom does not implement. **This is where a frontend
 * test suite quietly stops testing anything**, so each stub below is deliberately dumb:
 * it does the minimum to let the code under test run, and it never simulates behaviour
 * the real API has. A clever `MediaRecorder` mock that "records" would be a test of the
 * mock. `useRecorder.test.tsx` installs its own recorder per test, close to the
 * assertions, for exactly that reason — what is here is only the shape of the API, so a
 * component that merely touches it does not explode.
 */

import "@testing-library/jest-dom";

// jsdom implements neither the element nor the media pipeline behind it. `<audio>`
// renders, but play() is missing entirely, so AudioPlayer's click handler would throw
// TypeError rather than exercise its own error path.
Object.defineProperty(window.HTMLMediaElement.prototype, "play", {
  configurable: true,
  writable: true,
  value: jest.fn().mockResolvedValue(undefined),
});

Object.defineProperty(window.HTMLMediaElement.prototype, "pause", {
  configurable: true,
  writable: true,
  value: jest.fn(),
});

// jsdom's canvas is a stub that logs "Not implemented" to the virtual console on every
// getContext call. The components that draw already handle a null context — that is the
// real browser case where a context cannot be acquired — so returning null here is the
// honest stub rather than a silenced error.
Object.defineProperty(window.HTMLCanvasElement.prototype, "getContext", {
  configurable: true,
  writable: true,
  value: jest.fn(() => null),
});

// Present in every browser this project supports, absent from jsdom. Components that
// draw at frame rate call it; without it they throw on mount.
if (!window.requestAnimationFrame) {
  window.requestAnimationFrame = ((callback: FrameRequestCallback) =>
    setTimeout(() => callback(performance.now()), 16) as unknown as number) as typeof window.requestAnimationFrame;
  window.cancelAnimationFrame = ((handle: number) =>
    clearTimeout(handle)) as typeof window.cancelAnimationFrame;
}

// jsdom does not implement secure contexts and reports `false` on every origin,
// including the http://localhost/ it serves tests from — where a real browser reports
// `true` and grants microphone access. Left alone, every recorder test would exercise
// the "this page is not on a secure origin" branch and nothing else. The test that wants
// that branch sets this back to false itself.
Object.defineProperty(window, "isSecureContext", { configurable: true, value: true });

// `URL.createObjectURL` is how a recorded Blob becomes something an <audio src> can
// play. jsdom has neither half.
if (!window.URL.createObjectURL) {
  window.URL.createObjectURL = jest.fn(() => "blob:jest/00000000");
  window.URL.revokeObjectURL = jest.fn();
}

// Node's Blob has no arrayBuffer/size semantics problem, but jsdom's File constructor is
// used by the upload path and needs a stable `size`. Nothing to stub — this comment
// exists so the next person does not go looking for one.
