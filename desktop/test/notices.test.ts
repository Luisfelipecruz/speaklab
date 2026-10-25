import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { describeFailures, labelOf, llmNotice } from "../src/notices.ts";

describe("the language model's notice", () => {
  it("is nothing while conversations work on the measured build", () => {
    assert.equal(llmNotice({ status: "ok" }), undefined);
    assert.equal(llmNotice(undefined), undefined);
  });

  it("says to open Ollama when nothing answers", () => {
    assert.match(llmNotice({ status: "unreachable", detail: "ConnectError: refused" })!, /Open Ollama .* then check again/);
  });

  it("passes on the API's own words for a model that is not pulled", () => {
    const detail = "gemma4:e4b is not pulled. Run: ollama pull gemma4:e4b";
    assert.equal(llmNotice({ status: "error", detail }), detail);
  });

  it("says conversations work on a build the figures were not measured on", () => {
    const notice = llmNotice({ status: "degraded", detail: "gemma4:e4b is pulled as build 0123456789ab, not c6eb396dbd59." })!;
    assert.match(notice, /^Conversations work\. gemma4:e4b is pulled as build 0123456789ab/);
  });
});

describe("what failed, in words", () => {
  it("says a job's own explanation as it is, and leaves out what only needed it", () => {
    const newer = "This data was written by a newer SpeakLab. Install the newer version.";
    const said = describeFailures({
      postgres: { state: "ready" },
      migrate: { state: "failed", detail: newer },
      seed: { state: "failed", detail: "needs migrate" },
      api: { state: "failed", detail: "needs seed" },
      pron: { state: "starting" },
    });
    assert.equal(said, newer);
  });

  it("names the part when the supervisor's words alone are not a sentence", () => {
    const said = describeFailures({
      pron: { state: "failed", detail: "exited 5 times in 5 minutes" },
      asr: { state: "failed", detail: "was not ready in time" },
      tts: { state: "ready" },
    });
    assert.equal(said, "Pronunciation scoring exited 5 times in 5 minutes.\nSpeech recognition was not ready in time.");
  });

  it("names what a part needed when nothing else is said to have failed", () => {
    assert.equal(describeFailures({ api: { state: "failed", detail: "needs postgres" } }), "SpeakLab's service needs the database.");
  });

  it("labels a part at the head of a line, and keeps a name it does not know", () => {
    assert.equal(labelOf("tts"), "The voice");
    assert.equal(labelOf("web"), "Web");
  });
});
