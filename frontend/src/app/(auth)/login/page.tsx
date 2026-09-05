"use client";

/**
 * Sign in.
 *
 * A client component because it owns form state and calls the API from the browser —
 * the session cookie is set by that response, and a server-side fetch would set it on
 * the Next.js server instead of on the person's browser.
 *
 * `router.refresh()` after a successful sign-in is not optional: the pages it lands on
 * are server components with `force-dynamic` that fetch with the browser's cookie
 * forwarded, and without the refresh they would render from the client-side cache as
 * though nobody had signed in.
 *
 * **`?next=` is honoured.** People arrive here from the middle of something — a
 * scenario they were about to start, a conversation they opened from a bookmark — and
 * landing them on the home page afterwards makes them find their way back by hand. The
 * value is checked by `safeNext` before it is used: an unchecked `next` is an open
 * redirect, which is the standard way a login form becomes a phishing hop.
 */

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/hooks/useAuth";
import { safeNext } from "@/lib/navigation";

export default function LoginPage() {
  // `useSearchParams` opts the tree into client-side rendering, and Next requires the
  // boundary to be explicit rather than inferring one around the whole page.
  return (
    <Suspense fallback={null}>
      <LoginForm />
    </Suspense>
  );
}

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { signIn, error, pending } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    const profile = await signIn(email, password);
    if (profile) {
      router.push(safeNext(searchParams.get("next")));
      router.refresh();
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-2xl">Sign in</CardTitle>
        <CardDescription>Pick up where your last session left off.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>

          <div className="flex flex-col gap-2">
            <Label htmlFor="password">Password</Label>
            <Input
              id="password"
              type="password"
              // `current-password`, not `new-password`. It is what tells a password
              // manager to offer the saved entry rather than to propose a new one.
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>

          {error && (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          <Button type="submit" disabled={pending} className="mt-2">
            {pending ? "Signing in…" : "Sign in"}
          </Button>
        </form>

        <p className="text-muted-foreground mt-6 text-center text-sm">
          No account yet?{" "}
          <Link href="/register" className="text-foreground underline underline-offset-4">
            Create one
          </Link>
        </p>
      </CardContent>
    </Card>
  );
}
