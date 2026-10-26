// A multipart/form-data body, built by hand: Electron's `net.request` takes bytes, not a
// FormData. Text fields, then at most one file.

import { randomBytes } from "node:crypto";

export interface FilePart {
  name: string;
  filename: string;
  type: string;
  bytes: Uint8Array;
}

export function multipart(
  fields: Record<string, string>,
  file?: FilePart,
  boundary = `speaklab-${randomBytes(12).toString("hex")}`,
): { body: Buffer; contentType: string } {
  const parts: Buffer[] = [];
  for (const [name, value] of Object.entries(fields)) {
    parts.push(Buffer.from(`--${boundary}\r\nContent-Disposition: form-data; name="${name}"\r\n\r\n${value}\r\n`));
  }
  if (file) {
    parts.push(
      Buffer.from(
        `--${boundary}\r\nContent-Disposition: form-data; name="${file.name}"; filename="${file.filename}"\r\nContent-Type: ${file.type}\r\n\r\n`,
      ),
      Buffer.from(file.bytes),
      Buffer.from("\r\n"),
    );
  }
  parts.push(Buffer.from(`--${boundary}--\r\n`));
  return { body: Buffer.concat(parts), contentType: `multipart/form-data; boundary=${boundary}` };
}
