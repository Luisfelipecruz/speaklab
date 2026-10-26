import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { multipart } from "../src/multipart.ts";

describe("a multipart body", () => {
  it("carries the text fields, then the file, then the closing boundary", () => {
    const { body, contentType } = multipart(
      { mode: "auto", version: "organized,corrected" },
      { name: "audio", filename: "say.webm", type: "audio/webm;codecs=opus", bytes: new Uint8Array([0, 255, 13, 10]) },
      "B",
    );

    assert.equal(contentType, "multipart/form-data; boundary=B");
    assert.deepEqual(
      body,
      Buffer.concat([
        Buffer.from(
          '--B\r\nContent-Disposition: form-data; name="mode"\r\n\r\nauto\r\n' +
            '--B\r\nContent-Disposition: form-data; name="version"\r\n\r\norganized,corrected\r\n' +
            '--B\r\nContent-Disposition: form-data; name="audio"; filename="say.webm"\r\nContent-Type: audio/webm;codecs=opus\r\n\r\n',
        ),
        Buffer.from([0, 255, 13, 10]),
        Buffer.from("\r\n--B--\r\n"),
      ]),
    );
  });

  it("keeps text in UTF-8, accents and all", () => {
    const { body } = multipart({ text: "mañana, ¿vale?" }, undefined, "B");
    assert.ok(body.includes(Buffer.from("mañana, ¿vale?", "utf8")));
    assert.ok(body.toString("utf8").endsWith("--B--\r\n"));
  });

  it("draws a fresh boundary each time when none is given", () => {
    const one = multipart({}).contentType;
    const two = multipart({}).contentType;
    assert.match(one, /^multipart\/form-data; boundary=speaklab-[0-9a-f]{24}$/);
    assert.notEqual(one, two);
  });
});
