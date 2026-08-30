"use client";

/**
 * Session state, shared by everything that renders inside the application.
 *
 * **This was a plain hook at m3 and is a context at m7, which is what m3 said would
 * happen.** The note it carried read: a provider is what you need when several
 * components must agree on one copy of the session; at m3 there were two consumers and
 * they were two pages that never render at the same time, so a context would have been
 * indirection with one implementation.
 *
 * m7 is the milestone that changes the arithmetic. The header knows who is signed in and
 * sits *around* pages that also need the profile, so the hook-per-consumer version would
 * mount two independent copies of the session on every screen — two `GET /auth/me` calls
 * on load, and a sign-out that empties one of them while the other still renders an
 * email address. Neither is a bug a test would have caught; both are the reason the
 * promotion was scheduled rather than done speculatively.
 *
 * `status` is a three-state, not a boolean. "Checking" and "signed out" are genuinely
 * different, and collapsing them is what produces the flash of a login form on every
 * page load for someone who is already signed in.
 */

import { createContext, useCallback, useContext, useEffect, useState } from "react";

import { ApiError, fetchMe, login as postLogin, logout as postLogout, register as postRegister } from "@/lib/auth";
import type { RegisterInput, UserProfile } from "@/lib/auth";

export type AuthStatus = "checking" | "authenticated" | "anonymous";

export interface UseAuth {
  user: UserProfile | null;
  status: AuthStatus;
  /** The last failure, in words, or null. Cleared at the start of each attempt. */
  error: string | null;
  /** True while a submit is in flight, so a form can disable its button. */
  pending: boolean;
  signIn: (email: string, password: string) => Promise<UserProfile | null>;
  signUp: (input: RegisterInput) => Promise<UserProfile | null>;
  signOut: () => Promise<void>;
}

export const AuthContext = createContext<UseAuth | null>(null);

/**
 * The state itself. Exported for `AuthProvider`, which is its only caller — a second
 * caller would be a second copy of the session, which is the thing this file stopped
 * doing.
 */
export function useAuthState(): UseAuth {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [status, setStatus] = useState<AuthStatus>("checking");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    // `cancelled` rather than an AbortController: the request should still complete and
    // populate the browser's cookie jar if it is in flight, we just must not call
    // setState on a component that has gone. React 18's StrictMode runs this twice in
    // development, which is exactly the case this guards.
    let cancelled = false;

    fetchMe()
      .then((profile) => {
        if (cancelled) return;
        setUser(profile);
        setStatus(profile ? "authenticated" : "anonymous");
      })
      .catch((cause: unknown) => {
        if (cancelled) return;
        // Reaching here means something other than a 401 — the API is down, or it
        // answered 500. Reporting it as "anonymous" with an error is honest: we do not
        // know who this is, and we know why we do not know.
        setStatus("anonymous");
        setError(cause instanceof ApiError ? cause.message : "Could not check the session");
      });

    return () => {
      cancelled = true;
    };
  }, []);

  /** Shared shape for the two submitting actions: clear, run, report, settle. */
  const attempt = useCallback(
    async (action: () => Promise<UserProfile>): Promise<UserProfile | null> => {
      setError(null);
      setPending(true);
      try {
        const profile = await action();
        setUser(profile);
        setStatus("authenticated");
        return profile;
      } catch (cause: unknown) {
        setError(cause instanceof ApiError ? cause.message : "Something went wrong");
        return null;
      } finally {
        setPending(false);
      }
    },
    [],
  );

  const signIn = useCallback(
    (email: string, password: string) => attempt(() => postLogin(email, password)),
    [attempt],
  );

  const signUp = useCallback((input: RegisterInput) => attempt(() => postRegister(input)), [attempt]);

  const signOut = useCallback(async () => {
    // The local state is cleared whatever the request did. A logout that failed
    // server-side still means this browser should stop showing somebody's email, and
    // leaving the UI signed in because the network blinked is the worse of the two
    // wrong answers.
    try {
      await postLogout();
    } finally {
      setUser(null);
      setStatus("anonymous");
    }
  }, []);

  return { user, status, error, pending, signIn, signUp, signOut };
}

/**
 * The session, from the nearest provider.
 *
 * Throws outside one rather than falling back to a private copy. A silent fallback is
 * how a component ends up with its own session that nothing else updates, which is
 * precisely the failure the provider was introduced to remove.
 */
export function useAuth(): UseAuth {
  const value = useContext(AuthContext);
  if (value === null) {
    throw new Error("useAuth must be used inside <AuthProvider>");
  }
  return value;
}
