/**
 * The Next.js server's half of the API client.
 *
 * **Server components only.** It imports `next/headers`, which throws in a client
 * component, so importing this from anything with `"use client"` at the top is a build
 * error rather than a subtle runtime one. That guard is the reason it is a separate
 * module instead of a branch inside `lib/api.ts`.
 *
 * It exists for one reason: **there is no shared cookie jar between the browser and the
 * Next.js server.** A server component that fetches `/sessions/12` is a different HTTP
 * client from the browser that has the session cookie, so it gets a 401 unless the
 * incoming request's own `Cookie` header is forwarded explicitly. m3's `lib/auth.ts`
 * wrote that down as a warning; this is the milestone that needed it.
 *
 * Why bother, when a client component could fetch the same thing? FR-10 — a session
 * survives a page reload — is about what is on the screen after the reload, and a client
 * fetch means the transcript arrives one round trip *after* the first paint. Rendering a
 * spinner over a conversation the server already had is a worse answer to the
 * requirement than rendering the conversation.
 *
 * `INTERNAL_API_URL` and not the public one: this call is made inside the compose
 * network, where the API answers to `api:8000` and `localhost:8002` is the frontend
 * container talking to itself.
 */

import { headers } from "next/headers";

import { ApiError, INTERNAL_API_URL, messageFrom } from "@/lib/api";

export async function serverRequest<T>(path: string): Promise<T> {
  const cookie = (await headers()).get("cookie") ?? "";

  let response: Response;
  try {
    response = await fetch(`${INTERNAL_API_URL}${path}`, {
      headers: cookie ? { cookie } : {},
      // A conversation transcript that came out of a cache is a conversation missing
      // its last turn. Nothing this module fetches is cacheable.
      cache: "no-store",
    });
  } catch {
    throw new ApiError("Could not reach the API. Is the stack running?", 0);
  }

  const body = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(messageFrom(body, response.status), response.status);
  return body as T;
}

/**
 * Fetch, or `null` for the two answers a page can render as a state rather than a crash:
 * not signed in, and no such row.
 *
 * Every other failure still throws, so a 500 or an unreachable API reaches the error
 * boundary instead of being rendered as an empty list — which would tell the user their
 * history is gone.
 */
export async function serverRequestOrNull<T>(path: string): Promise<T | null> {
  try {
    return await serverRequest<T>(path);
  } catch (error) {
    if (error instanceof ApiError && (error.status === 401 || error.status === 404)) {
      return null;
    }
    throw error;
  }
}
