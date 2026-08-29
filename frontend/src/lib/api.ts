/**
 * The one place that knows the API's address.
 *
 * Two base URLs, because there are two callers. A server component runs inside the
 * compose network and resolves `api:8000`; the browser runs on the host and resolves
 * `localhost:8002`. Using one for both is the classic Next.js-in-a-container bug: it
 * works in `npm run dev` on the host and fails the moment it is containerised, or the
 * other way round.
 */

export const INTERNAL_API_URL =
  process.env.INTERNAL_API_URL ?? "http://localhost:8002";

export const PUBLIC_API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8002";

/** Closed vocabulary, mirroring api/routers/health.py. */
export type ServiceStatus = "ok" | "unreachable" | "error";

export interface ProbeResult {
  status: ServiceStatus;
  url?: string;
  latency_ms?: number;
  detail?: string;
  /** The service's own body. `model_loaded: false` while weights are still downloading. */
  reports?: Record<string, unknown>;
}

export interface Health {
  status: "ok" | "degraded" | "unavailable";
  version: string;
  database: { status: string; latency_ms?: number; detail?: string };
  models: Record<string, ProbeResult>;
}

/**
 * Fetch /health, or `null` if the API itself cannot be reached.
 *
 * `null` is a third state and not an error: it is what the page shows when the API
 * container is not running, which is different from the API running and reporting that
 * something else is down. Throwing here would render an error boundary that says less.
 *
 * `cache: "no-store"` because a cached health check is not a health check.
 */
export async function getHealth(): Promise<Health | null> {
  try {
    const response = await fetch(`${INTERNAL_API_URL}/health`, {
      cache: "no-store",
    });
    // 503 is a real answer — the API is up and telling us the database is gone — so it
    // is parsed rather than treated as unreachable.
    return (await response.json()) as Health;
  } catch {
    return null;
  }
}
