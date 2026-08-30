/**
 * The recorder, including the four ways it is allowed to fail.
 *
 * Every one of these is a state a real user reaches — a refused permission prompt, a
 * browser too old, a tap instead of a hold, Safari's container instead of Chrome's — and
 * every one of them is silent by default. The point of these tests is not that the happy
 * path works; it is that none of the unhappy ones reaches the user as an unhandled
 * promise rejection in a console they do not have open.
 */

import { act, renderHook, waitFor } from "@testing-library/react";

import { useRecorder } from "@/hooks/useRecorder";

// ── A MediaRecorder that does only what the hook needs it to ────────────────

class FakeMediaRecorder {
  static supported: string[] = ["audio/webm;codecs=opus", "audio/webm"];
  static isTypeSupported = (type: string) => FakeMediaRecorder.supported.includes(type);

  state: "inactive" | "recording" = "inactive";
  ondataavailable: ((event: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;

  constructor(
    readonly stream: MediaStream,
    readonly options?: { mimeType?: string },
  ) {}

  get mimeType(): string {
    return this.options?.mimeType ?? "";
  }

  start() {
    this.state = "recording";
  }

  stop() {
    this.state = "inactive";
    this.ondataavailable?.({ data: new Blob(["pretend audio"], { type: this.mimeType }) });
    this.onstop?.();
  }
}

let tracks: { stop: jest.Mock }[] = [];
let getUserMedia: jest.Mock;
let clock = 0;

function installBrowser({ supported = ["audio/webm;codecs=opus", "audio/webm"] } = {}) {
  tracks = [{ stop: jest.fn() }];
  FakeMediaRecorder.supported = supported;
  getUserMedia = jest.fn().mockResolvedValue({ getTracks: () => tracks } as unknown as MediaStream);

  Object.defineProperty(window.navigator, "mediaDevices", {
    configurable: true,
    value: { getUserMedia },
  });
  (window as unknown as { MediaRecorder: unknown }).MediaRecorder = FakeMediaRecorder;
  // No AudioContext: the analyser is optional and must never be why a recording fails
  // to start. Its absence here is also the Safari-without-a-prefix case.
  (window as unknown as { AudioContext?: unknown }).AudioContext = undefined;
}

beforeEach(() => {
  clock = 0;
  jest.spyOn(performance, "now").mockImplementation(() => clock);
  installBrowser();
});

afterEach(() => {
  jest.restoreAllMocks();
});

/** Hold the button for `ms` of (mocked) wall clock, and return whatever comes back. */
async function hold(result: { current: ReturnType<typeof useRecorder> }, ms: number) {
  await act(async () => {
    await result.current.start();
  });
  clock += ms;
  let clip: Awaited<ReturnType<typeof result.current.stop>> = null;
  await act(async () => {
    clip = await result.current.stop();
  });
  return clip as Awaited<ReturnType<typeof result.current.stop>>;
}

test("a held button produces a clip with the container the browser negotiated", async () => {
  const { result } = renderHook(() => useRecorder());

  const clip = await hold(result, 1500);

  expect(clip).not.toBeNull();
  expect(clip!.mimeType).toBe("audio/webm;codecs=opus");
  expect(clip!.filename).toBe("turn.webm");
  expect(clip!.durationMs).toBe(1500);
  expect(result.current.state).toBe("idle");
});

test("Safari's container is negotiated to an .m4a, not refused", async () => {
  // The whole reason MIME_CANDIDATES is a list. A browser that has no Opus/WebM is
  // supported, not told it cannot record.
  installBrowser({ supported: ["audio/mp4"] });
  const { result } = renderHook(() => useRecorder());

  const clip = await hold(result, 900);

  expect(clip!.mimeType).toBe("audio/mp4");
  expect(clip!.filename).toBe("turn.m4a");
});

test("a refused microphone is a state with instructions, not a rejected promise", async () => {
  getUserMedia.mockRejectedValue(
    Object.assign(new Error("denied"), { name: "NotAllowedError" }),
  );
  const { result } = renderHook(() => useRecorder());

  await act(async () => {
    await result.current.start();
  });

  expect(result.current.state).toBe("idle");
  expect(result.current.error?.fault).toBe("permission-denied");
  // The message has to say what to do next, not what went wrong.
  expect(result.current.error?.message).toMatch(/address bar/i);
});

test("a missing microphone and a busy one are told apart", async () => {
  getUserMedia.mockRejectedValue(
    Object.assign(new Error("none"), { name: "NotFoundError" }),
  );
  const { result } = renderHook(() => useRecorder());

  await act(async () => {
    await result.current.start();
  });
  expect(result.current.error?.fault).toBe("no-device");

  getUserMedia.mockRejectedValue(
    Object.assign(new Error("busy"), { name: "NotReadableError" }),
  );
  await act(async () => {
    await result.current.start();
  });
  expect(result.current.error?.fault).toBe("device-busy");
});

test("a browser without MediaRecorder says so instead of rendering a dead button", async () => {
  Object.defineProperty(window.navigator, "mediaDevices", {
    configurable: true,
    value: undefined,
  });
  const { result } = renderHook(() => useRecorder());

  await waitFor(() => expect(result.current.state).toBe("unsupported"));
  expect(result.current.error?.fault).toBe("no-mediarecorder");
  expect(result.current.error?.message).toMatch(/Safari 16/);
});

test("an insecure origin is diagnosed as such, not as a refused permission", async () => {
  // The failure a developer hits by opening the app on a LAN address instead of
  // localhost. The browser withholds `mediaDevices` entirely, which is byte-for-byte
  // what an old browser looks like — the origin is the only thing that tells them apart.
  Object.defineProperty(window.navigator, "mediaDevices", {
    configurable: true,
    value: undefined,
  });
  Object.defineProperty(window, "isSecureContext", { configurable: true, value: false });
  const { result } = renderHook(() => useRecorder());

  await waitFor(() => expect(result.current.error?.fault).toBe("insecure-context"));
  expect(result.current.error?.message).toMatch(/HTTPS or on localhost/);

  Object.defineProperty(window, "isSecureContext", { configurable: true, value: true });
});

test("a tap is refused locally rather than sent to three model services", async () => {
  const { result } = renderHook(() => useRecorder());

  const clip = await hold(result, 120);

  expect(clip).toBeNull();
  expect(result.current.error?.fault).toBe("too-short");
  expect(result.current.error?.message).toMatch(/Hold the button/);
});

test("stopping releases the microphone", async () => {
  // Not cosmetic: a live track leaves the browser's recording indicator on, which is
  // invisible in review and extremely visible in the tab.
  const { result } = renderHook(() => useRecorder());

  await hold(result, 1000);

  expect(tracks[0].stop).toHaveBeenCalled();
});

test("unmounting mid-recording releases the microphone too", async () => {
  const { result, unmount } = renderHook(() => useRecorder());

  await act(async () => {
    await result.current.start();
  });
  unmount();

  expect(tracks[0].stop).toHaveBeenCalled();
});
