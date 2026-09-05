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

// The pointer-capture and scrolling APIs the menu and tooltip primitives call on the
// element they are about to open. jsdom implements none of them, and the failure is not
// an exception a test can see — the primitive's own handler throws inside an event, the
// menu never opens, and the assertion times out five seconds later looking for an item
// that was never rendered.
for (const name of [
  "hasPointerCapture",
  "setPointerCapture",
  "releasePointerCapture",
] as const) {
  if (!window.Element.prototype[name]) {
    Object.defineProperty(window.Element.prototype, name, {
      configurable: true,
      writable: true,
      value: jest.fn(() => false),
    });
  }
}

if (!window.Element.prototype.scrollIntoView) {
  Object.defineProperty(window.Element.prototype, "scrollIntoView", {
    configurable: true,
    writable: true,
    value: jest.fn(),
  });
}

// Used by the floating primitives to keep a menu anchored to its trigger. Absent from
// jsdom, where nothing has a size to observe in the first place. Both have to exist
// before the primitives are imported, which is why they are here and not in a test file:
// the positioning library reads them once, at module scope, and falls back to a polling
// loop that costs about ten seconds a suite when it does not find them.
if (!window.ResizeObserver) {
  window.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof window.ResizeObserver;
}

if (!window.IntersectionObserver) {
  window.IntersectionObserver = class {
    readonly root = null;
    readonly rootMargin = "";
    readonly thresholds: number[] = [];
    observe() {}
    unobserve() {}
    disconnect() {}
    takeRecords() {
      return [];
    }
  } as unknown as typeof window.IntersectionObserver;
  global.IntersectionObserver = window.IntersectionObserver;
}

// jsdom has no media queries at all — `window.matchMedia` is simply absent, and a
// component that asks whether the viewport is narrow, or whether the operating system
// prefers dark, throws on mount rather than getting an answer. The stub answers "no" to
// every query and notifies nobody, which is the honest reading of a jsdom window: it has
// no viewport and no operating system preference. A test that needs a different answer
// replaces it for itself.
if (!window.matchMedia) {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: jest.fn(),
    removeEventListener: jest.fn(),
    addListener: jest.fn(),
    removeListener: jest.fn(),
    dispatchEvent: jest.fn(() => false),
  })) as unknown as typeof window.matchMedia;
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
