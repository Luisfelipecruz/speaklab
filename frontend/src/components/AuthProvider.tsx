"use client";

/**
 * One copy of the session, for everything rendered underneath.
 *
 * Mounted in the root layout, which is a server component — a client provider taking
 * `children` as a prop does not make those children client components, so pages below
 * it stay server-rendered. Getting that backwards ("use client" on the layout itself) is
 * what turns a whole application into a client bundle by accident.
 */

import type { ReactNode } from "react";

import { AuthContext, useAuthState } from "@/hooks/useAuth";

export function AuthProvider({ children }: { children: ReactNode }) {
  const auth = useAuthState();

  return <AuthContext.Provider value={auth}>{children}</AuthContext.Provider>;
}
