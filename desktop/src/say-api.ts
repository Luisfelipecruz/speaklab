// The API, from the main process, as the person signed in to the window: Electron's
// network stack with the default session's cookies, so the session cookie the window's
// sign-in set goes with every request. Sent as from the window's own origin, which is what
// makes a request carrying a SameSite=Lax cookie same-site. Nothing here keeps a token of
// its own.

import { net } from "electron";

import { type Capture, type CaptureRequest, type SayApi, SayApiError, type Version } from "./dictation.ts";
import { multipart } from "./multipart.ts";

function detailOf(body: string, status: number): string {
  try {
    const detail = (JSON.parse(body) as { detail?: unknown }).detail;
    if (typeof detail === "string") return detail;
  } catch {
    // Not JSON.
  }
  return `The API answered ${status}.`;
}

interface Where {
  base: string;
  origin: string;
}

function call<T>(where: Where, method: string, path: string, body?: Buffer, type?: string): Promise<T> {
  return new Promise((resolve, reject) => {
    const request = net.request({ method, url: `${where.base}${path}`, origin: where.origin, useSessionCookies: true });
    if (type) request.setHeader("Content-Type", type);
    request.on("response", (response) => {
      const chunks: Buffer[] = [];
      response.on("data", (chunk) => chunks.push(chunk));
      response.on("end", () => {
        const text = Buffer.concat(chunks).toString("utf8");
        const status = response.statusCode;
        if (status >= 400) return reject(new SayApiError(detailOf(text, status), status));
        if (status === 202 || status === 204 || !text) return resolve(undefined as T);
        try {
          resolve(JSON.parse(text) as T);
        } catch {
          reject(new SayApiError("The API answered with something that is not JSON.", status));
        }
      });
    });
    request.on("error", (error) => reject(new SayApiError(error.message, 0)));
    request.end(body);
  });
}

export function sayApi(base: string, origin: string): SayApi {
  const where = { base, origin };
  return {
    warm: () => call<void>(where, "POST", "/captures/warm"),
    capture(given: CaptureRequest) {
      const fields: Record<string, string> = {
        mode: given.mode,
        version: given.versions.join(","),
        save: given.save ? "true" : "false",
      };
      if (given.app) fields.app = given.app;
      if (given.text !== undefined) {
        fields.text = given.text;
        fields.via = given.via === "copied" ? "copied" : "typed";
      }
      const file = given.audio
        ? { name: "audio", filename: "say.webm", type: given.audio.mimeType, bytes: given.audio.bytes }
        : undefined;
      const { body, contentType } = multipart(fields, file);
      return call<Capture>(where, "POST", "/captures", body, contentType);
    },
    version: (id: number, version: Version) => call<Capture>(where, "POST", `/captures/${id}/versions/${version}`),
    remove: (id: number) => call<void>(where, "DELETE", `/captures/${id}`),
  };
}
