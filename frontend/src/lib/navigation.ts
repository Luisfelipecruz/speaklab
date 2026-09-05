/**
 * Where a redirect is allowed to go.
 *
 * People reach the login page from the middle of something — a scenario they were about
 * to start, a conversation opened from a bookmark — and it carries where they were
 * going in `?next=`. That parameter is attacker-controlled by construction: anybody can
 * send somebody a link to this site with any `next` they like.
 *
 * An unchecked `next` is an open redirect, which is the standard way a real login form
 * becomes one hop in a phishing chain: the domain in the address bar is genuine, the
 * user signs in, and the site itself sends them somewhere else. Both checks below are
 * load-bearing — `//evil.example` starts with a slash and is a *protocol-relative URL*
 * that browsers resolve against another origin, so "starts with /" alone is not a
 * same-site test.
 */

/**
 * Where signing in lands when nothing else was asked for.
 *
 * `/home` rather than the catalogue: somebody arriving wants to know how they are doing
 * and what to do about it, and a grid of scenarios answers neither.
 */
export const DEFAULT_AFTER_LOGIN = "/home";

export function safeNext(value: string | null | undefined): string {
  if (!value || !value.startsWith("/") || value.startsWith("//")) return DEFAULT_AFTER_LOGIN;
  return value;
}
