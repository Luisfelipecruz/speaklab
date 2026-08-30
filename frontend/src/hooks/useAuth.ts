"use client";

/**
 * Session state for a client component.
 *
 * A hook rather than a context, deliberately. A provider is what you need when several
 * components must agree on one copy of the session; at m3 there are two consumers and
 * they are two separate pages that never render at the same time, so a context would be
 * indirection with one implementation. m6 adds the first authenticated shell — a header
 * that knows who is signed in, wrapped around pages that also need it — and that is the
 * milestone where this gets promoted to a provider. Doing it now would be guessing at
 * the shape of a layout that does not exist.
 *
 * `status` is a three-state, not a boolean. "Checking" and "signed out" are genuinely
 * different, and collapsing them is what produces the flash of a login form on every
 * page load for someone who is already signed in.
 */

import { useCallback, useEffect, useState } from "react";

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

export function useAuth(): UseAuth {
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
    await postLogout();
    setUser(null);
    setStatus("anonymous");
  }, []);

  return { user, status, error, pending, signIn, signUp, signOut };
}
