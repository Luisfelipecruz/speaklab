/**
 * The browser's half of the session.
 *
 * Every call here sets `credentials: "include"`, and that flag is the whole design. The
 * token is in an httpOnly cookie, so this module cannot read it, cannot attach it to a
 * header, and cannot store it — it can only ask the browser to send it. Omitting the
 * flag is the failure this file exists to prevent: `fetch` drops cross-origin cookies
 * by default, so a login would appear to succeed and every following request would 401,
 * with nothing in the console to say why.
 *
 * These are browser-side calls, so they use PUBLIC_API_URL (`localhost:8002`) rather
 * than the in-network address. A server component that ever needs the session has to
 * forward the incoming cookie header explicitly; there is no shared jar between the
 * browser and the Next.js server.
 */

import { PUBLIC_API_URL } from "@/lib/api";

/** Mirrors `api/models/auth.py::UserProfile`. No token, no hash — there is no field for either. */
export interface UserProfile {
  id: number;
  email: string;
  native_language: string;
  cefr_self_assessed: string | null;
  retain_audio: boolean;
  created_at: string;
}

export interface RegisterInput {
  email: string;
  password: string;
  native_language: string;
  cefr_self_assessed?: string | null;
}

/** A failed request, carrying the status so a caller can tell 401 from 409. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/**
 * Turn an error body into one sentence a person can act on.
 *
 * FastAPI answers with two different shapes and they have to be told apart. A raised
 * `HTTPException` gives `{detail: "Incorrect email or password"}`; a validation failure
 * gives `{detail: [{loc, msg, type}, ...]}`. Rendering the second one as-is puts
 * `[object Object]` or a JSON array in front of the user, which is the most common way
 * a FastAPI frontend leaks its own internals into the interface.
 */
function messageFrom(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown } | null)?.detail;

  if (typeof detail === "string") return detail;

  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as { loc?: unknown[]; msg?: string };
    // `loc` is ["body", "password"]; the field name is the part worth showing.
    const field = Array.isArray(first.loc) ? first.loc[first.loc.length - 1] : undefined;
    const message = first.msg ?? "is not valid";
    return field ? `${String(field)}: ${message}` : message;
  }

  return `Request failed (${status})`;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${PUBLIC_API_URL}${path}`, {
      ...init,
      credentials: "include",
      headers: { "Content-Type": "application/json", ...init.headers },
    });
  } catch {
    // A network-level failure, not an HTTP one: the API container is not running, or
    // CORS rejected the request before it was made. Status 0 marks it as "never
    // answered", which is a different thing from a 500.
    throw new ApiError("Could not reach the API. Is the stack running?", 0);
  }

  if (response.status === 204) return undefined as T;

  const body = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(messageFrom(body, response.status), response.status);
  return body as T;
}

export function register(input: RegisterInput): Promise<UserProfile> {
  return request<UserProfile>("/auth/register", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function login(email: string, password: string): Promise<UserProfile> {
  return request<UserProfile>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function logout(): Promise<void> {
  return request<void>("/auth/logout", { method: "POST" });
}

/**
 * The current account, or `null` when there is no session.
 *
 * A 401 is resolved to `null` rather than thrown, because "nobody is logged in" is the
 * ordinary state of this endpoint and not an error. Every other status still throws —
 * a 500 must not be indistinguishable from being signed out, or the interface answers
 * an outage by quietly showing the login page.
 */
export async function fetchMe(): Promise<UserProfile | null> {
  try {
    return await request<UserProfile>("/auth/me");
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return null;
    throw error;
  }
}

/** The languages offered at registration. Two-letter ISO 639-1, matching `LanguageCode`. */
export const NATIVE_LANGUAGES = [
  { value: "es", label: "Spanish" },
  { value: "pt", label: "Portuguese" },
  { value: "fr", label: "French" },
  { value: "de", label: "German" },
  { value: "it", label: "Italian" },
  { value: "zh", label: "Chinese" },
  { value: "ja", label: "Japanese" },
  { value: "ko", label: "Korean" },
  { value: "ar", label: "Arabic" },
  { value: "ru", label: "Russian" },
] as const;

export const CEFR_BANDS = ["A1", "A2", "B1", "B2", "C1", "C2"] as const;
