/**
 * The browser's half of the session.
 *
 * The transport lives in `lib/api.ts` now, and this module is the auth vocabulary on top
 * of it: the profile shape, the five calls, and the one place that decides a 401 is not
 * an error. m3 wrote `request` here because auth was the only thing calling the API from
 * a browser; m7 added scenarios, sessions and turns, and a second copy of "attach the
 * cookie, normalise the failure" is how the two would eventually disagree about what a
 * 422 body looks like.
 *
 * `ApiError` is re-exported rather than moved-and-forgotten: every m3 caller imports it
 * from here, and a rename across files is churn that reviews nothing.
 */

import { ApiError, request } from "@/lib/api";

export { ApiError };

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
