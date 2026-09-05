"use client";

/**
 * The microphone, as a state machine with no silent failures.
 *
 * Browser recording has four ways to go wrong that all look identical to a user — the
 * page is not on a secure origin, the browser has no `MediaRecorder`, permission was
 * refused, or there is no input device — and the default behaviour of each is a promise
 * that rejects into a console nobody has open. Every one of them is a named state here,
 * carrying a sentence about what to do next. Recording is keyboard-operable and the
 * browser support floor is Safari 16; an unsupported browser has to say so rather than
 * render a button that does nothing.
 *
 * **Push and hold, not click to toggle.** Voice-activity detection guesses wrong, and
 * cutting somebody off mid-sentence is worse than making them hold a button. `start`
 * and `stop` are exposed rather than a `toggle`, so the caller can bind them to
 * pointerdown/pointerup and to keydown/keyup on Space with the same pair.
 *
 * `stop()` resolves with the clip rather than pushing it through a callback. The final
 * `dataavailable` event fires after `MediaRecorder.stop()` returns, so a synchronous
 * `stop()` would hand back a blob assembled from every chunk *except the last one* —
 * a recording missing its final ~100 ms, which is exactly where the end of a sentence
 * lives.
 */

import { useCallback, useEffect, useRef, useState } from "react";

export type RecorderState = "unsupported" | "idle" | "requesting" | "recording";

export type RecorderFault =
  | "insecure-context"
  | "no-mediarecorder"
  | "permission-denied"
  | "no-device"
  | "device-busy"
  | "too-short"
  | "failed";

export interface RecorderError {
  fault: RecorderFault;
  /** One sentence, addressed to the person holding the microphone. */
  message: string;
}

export interface RecordedClip {
  blob: Blob;
  mimeType: string;
  durationMs: number;
  /** A filename with the right container, for the multipart upload. */
  filename: string;
}

export interface UseRecorder {
  state: RecorderState;
  error: RecorderError | null;
  /** The negotiated container, or null before the first recording. */
  mimeType: string | null;
  /**
   * Live signal for the waveform. Null until the first recording starts and after the
   * last one ends — a waveform with nothing behind it should draw a flat line, not
   * pretend.
   */
  analyser: AnalyserNode | null;
  /** Milliseconds since this recording started. 0 when not recording. */
  elapsedMs: number;
  start: () => Promise<void>;
  stop: () => Promise<RecordedClip | null>;
  /** Abandon the recording in progress and keep nothing. */
  cancel: () => void;
  clearError: () => void;
}

/**
 * Candidate containers, most preferred first.
 *
 * Chrome and Edge take the first; Safari 16 takes `audio/mp4`, which is why it is on the
 * list at all and why the list is not just Opus. The empty string is the deliberate last
 * resort — it tells `MediaRecorder` to pick its own default, which is better than
 * refusing to record on a browser whose container this project has not heard of. The API
 * decodes whatever ffmpeg reads, so being liberal here costs nothing: normalisation
 * belongs at the service boundary, not in the browser.
 */
const MIME_CANDIDATES = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/mp4;codecs=mp4a.40.2",
  "audio/mp4",
  "audio/ogg;codecs=opus",
] as const;

/**
 * Below this, a "recording" is a mis-click. Sending it costs a round trip through three
 * model services to be told there was no speech, and the honest answer — hold the button
 * while you speak — is one the browser can give immediately.
 */
export const MIN_CLIP_MS = 400;

/** Container to file extension. The recogniser sniffs the bytes; this is for the log. */
function extensionFor(mimeType: string): string {
  if (mimeType.includes("webm")) return "webm";
  if (mimeType.includes("mp4")) return "m4a";
  if (mimeType.includes("ogg")) return "ogg";
  if (mimeType.includes("wav")) return "wav";
  return "bin";
}

function pickMimeType(): string {
  const supported = (type: string) =>
    typeof MediaRecorder !== "undefined" &&
    typeof MediaRecorder.isTypeSupported === "function" &&
    MediaRecorder.isTypeSupported(type);

  return MIME_CANDIDATES.find(supported) ?? "";
}

/** `getUserMedia`'s DOMException names, turned into something actionable. */
function faultFor(cause: unknown): RecorderError {
  const name = (cause as { name?: string } | null)?.name ?? "";

  if (name === "NotAllowedError" || name === "SecurityError") {
    return {
      fault: "permission-denied",
      message:
        "Microphone access was blocked. Allow it for this site in your browser's address bar, then try again.",
    };
  }
  if (name === "NotFoundError" || name === "OverconstrainedError") {
    return {
      fault: "no-device",
      message: "No microphone was found. Connect one and reload the page.",
    };
  }
  if (name === "NotReadableError" || name === "AbortError") {
    return {
      fault: "device-busy",
      message:
        "The microphone is in use by another application. Close it and try again.",
    };
  }
  return {
    fault: "failed",
    message: "The microphone could not be started. Reload the page and try again.",
  };
}

export function useRecorder(): UseRecorder {
  const [state, setState] = useState<RecorderState>("idle");
  const [error, setError] = useState<RecorderError | null>(null);
  const [mimeType, setMimeType] = useState<string | null>(null);
  const [analyser, setAnalyser] = useState<AnalyserNode | null>(null);
  const [elapsedMs, setElapsedMs] = useState(0);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const startedAtRef = useRef(0);
  const tickRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Support is decided after mount, never during render. `navigator` does not exist
  // while the server renders this page, and reading it there is the hydration mismatch
  // where the server sends "unsupported" and the browser replaces it with a button.
  useEffect(() => {
    if (typeof window === "undefined") return;

    const usable =
      Boolean(navigator.mediaDevices?.getUserMedia) && typeof MediaRecorder !== "undefined";
    if (usable) return;

    // Only diagnose once something is actually missing, and let the origin decide which
    // diagnosis it is. Checking `isSecureContext` first would be wrong in both
    // directions: it says nothing about whether this browser can record, and a browser
    // that plainly can would be told to change its URL.
    //
    // The insecure case is the one a developer hits by opening the app on a LAN address
    // instead of localhost. `navigator.mediaDevices` is simply absent there, which is
    // indistinguishable from an old browser unless the origin is looked at.
    setState("unsupported");
    setError(
      window.isSecureContext
        ? {
            fault: "no-mediarecorder",
            message:
              "This browser cannot record audio. SpeakLab needs Chrome, Edge, or Safari 16 or newer.",
          }
        : {
            fault: "insecure-context",
            message:
              "Browsers only grant microphone access over HTTPS or on localhost. Open this page at http://localhost:3003.",
          },
    );
  }, []);

  /** Release the microphone, the graph and the timer. Safe to call twice. */
  const teardown = useCallback(() => {
    if (tickRef.current !== null) {
      clearInterval(tickRef.current);
      tickRef.current = null;
    }
    // Stopping the tracks is what turns the browser's recording indicator off. Leaving
    // them live is invisible in code review and extremely visible in the tab title.
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;

    void audioContextRef.current?.close().catch(() => {});
    audioContextRef.current = null;

    recorderRef.current = null;
    setAnalyser(null);
    setElapsedMs(0);
  }, []);

  useEffect(() => teardown, [teardown]);

  const start = useCallback(async () => {
    if (state === "unsupported" || state === "recording" || state === "requesting") return;

    setError(null);
    setState("requesting");

    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        // Browser-side cleanup, requested rather than assumed: every one of these is a
        // hint the implementation may ignore, and none of them replaces the 16 kHz mono
        // normalisation the API does at the service boundary.
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
    } catch (cause) {
      setError(faultFor(cause));
      setState("idle");
      return;
    }

    const type = pickMimeType();
    let recorder: MediaRecorder;
    try {
      recorder = type ? new MediaRecorder(stream, { mimeType: type }) : new MediaRecorder(stream);
    } catch (cause) {
      stream.getTracks().forEach((track) => track.stop());
      setError(faultFor(cause));
      setState("idle");
      return;
    }

    streamRef.current = stream;
    recorderRef.current = recorder;
    chunksRef.current = [];
    recorder.ondataavailable = (event) => {
      if (event.data && event.data.size > 0) chunksRef.current.push(event.data);
    };

    // The analyser is a nicety and must never be the reason a recording fails to start:
    // Safari has needed a prefix, and a locked AudioContext throws on construction.
    try {
      const AudioContextCtor =
        window.AudioContext ??
        (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
      if (AudioContextCtor) {
        const context = new AudioContextCtor();
        const node = context.createAnalyser();
        node.fftSize = 1024;
        context.createMediaStreamSource(stream).connect(node);
        audioContextRef.current = context;
        setAnalyser(node);
      }
    } catch {
      setAnalyser(null);
    }

    // A timeslice, so `dataavailable` fires during the recording rather than only at the
    // end. Without it a browser that crashes mid-turn loses everything, and Safari has
    // historically produced a single unreadable blob for long single-chunk recordings.
    recorder.start(250);
    startedAtRef.current = performance.now();
    setMimeType(recorder.mimeType || type || null);
    setState("recording");

    setElapsedMs(0);
    tickRef.current = setInterval(
      () => setElapsedMs(Math.round(performance.now() - startedAtRef.current)),
      100,
    );
  }, [state]);

  const stop = useCallback(async (): Promise<RecordedClip | null> => {
    const recorder = recorderRef.current;
    if (!recorder || recorder.state === "inactive") {
      teardown();
      setState("idle");
      return null;
    }

    const durationMs = Math.round(performance.now() - startedAtRef.current);
    const type = recorder.mimeType || mimeType || "audio/webm";

    const blob = await new Promise<Blob>((resolve) => {
      recorder.onstop = () => resolve(new Blob(chunksRef.current, { type }));
      recorder.stop();
    });

    teardown();
    setState("idle");

    if (durationMs < MIN_CLIP_MS || blob.size === 0) {
      setError({
        fault: "too-short",
        message: "That was too short to hear. Hold the button down while you speak.",
      });
      return null;
    }

    return { blob, mimeType: type, durationMs, filename: `turn.${extensionFor(type)}` };
  }, [mimeType, teardown]);

  const cancel = useCallback(() => {
    const recorder = recorderRef.current;
    if (recorder && recorder.state !== "inactive") {
      recorder.onstop = null;
      recorder.stop();
    }
    chunksRef.current = [];
    teardown();
    setState((current) => (current === "unsupported" ? current : "idle"));
  }, [teardown]);

  const clearError = useCallback(() => setError(null), []);

  return { state, error, mimeType, analyser, elapsedMs, start, stop, cancel, clearError };
}
