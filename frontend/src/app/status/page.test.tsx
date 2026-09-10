/**
 * The stack describing itself, and the one state a fresh clone is most likely to be in:
 * every container healthy, Ollama running, and the model never pulled. That state fails
 * every conversation, so this page has to say which command fixes it rather than leave
 * the person running the stack to find out from a 503 on their first recording.
 *
 * The page is an async server component, so it is awaited and its result rendered;
 * `getHealth` is the one thing it does that a test environment cannot.
 */

import { render, screen } from "@testing-library/react";

import StatusPage from "@/app/status/page";
import type { Health, ProbeResult } from "@/lib/api";

jest.mock("@/lib/api", () => ({
  ...jest.requireActual("@/lib/api"),
  getHealth: jest.fn(),
}));

import { getHealth } from "@/lib/api";

const health = getHealth as jest.MockedFunction<typeof getHealth>;

const OK: ProbeResult = { status: "ok", latency_ms: 2 };

function stack(models: Record<string, ProbeResult>): Health {
  return {
    status: Object.values(models).every((m) => m.status === "ok") ? "ok" : "degraded",
    version: "0.13.1",
    database: { status: "ok", latency_ms: 1 },
    models,
  };
}

beforeEach(() => {
  health.mockReset();
});

test("a model that is not pulled shows the command that pulls it", async () => {
  health.mockResolvedValue(
    stack({
      asr: OK,
      tts: OK,
      pron: OK,
      llm: {
        status: "error",
        detail: "gemma3:4b is not pulled. Run: ollama pull gemma3:4b",
      },
    }),
  );

  render(await StatusPage());

  expect(screen.getByText("The persona's words, from Ollama on the host")).toBeInTheDocument();
  expect(
    screen.getByText("gemma3:4b is not pulled. Run: ollama pull gemma3:4b"),
  ).toBeInTheDocument();
  expect(screen.getByText("degraded")).toBeInTheDocument();
});

test("every model service gets a row, and a healthy stack shows no detail", async () => {
  health.mockResolvedValue(stack({ asr: OK, tts: OK, pron: OK, llm: OK }));

  render(await StatusPage());

  for (const role of [
    "Transcript with word timestamps and per-word logprobs",
    "The persona's spoken reply",
    "Forced alignment and per-phoneme GOP",
    "The persona's words, from Ollama on the host",
  ]) {
    expect(screen.getByText(role)).toBeInTheDocument();
  }
  // API, database and four model services — and the stack's own badge.
  expect(screen.getAllByText("ok")).toHaveLength(7);
  expect(screen.queryByText(/Run:/)).not.toBeInTheDocument();
});

test("an unreachable service is said by its badge, not by an exception string", async () => {
  health.mockResolvedValue(
    stack({
      asr: OK,
      tts: OK,
      pron: { status: "unreachable", detail: "ConnectError: [Errno -2] Name does not resolve" },
      llm: OK,
    }),
  );

  render(await StatusPage());

  expect(screen.getByText("unreachable")).toBeInTheDocument();
  expect(screen.queryByText(/ConnectError/)).not.toBeInTheDocument();
});

test("an API that does not answer says how to start it", async () => {
  health.mockResolvedValue(null);

  render(await StatusPage());

  expect(screen.getByText("api unreachable")).toBeInTheDocument();
  expect(screen.getByText(/The API did not answer/)).toBeInTheDocument();
});
