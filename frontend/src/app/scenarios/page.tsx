/**
 * The scenario catalogue.
 *
 * A server component, and one of the few screens that can be: the
 * scenario endpoints take no session, so there is no cookie to forward and no reason to
 * ship a fetch to the browser. The filters are links rather than a client-side control
 * for the same reason — a band is part of the address, so a filtered catalogue can be
 * bookmarked, shared, and reloaded, and the back button does what it looks like it does.
 *
 * The `band` value goes to the API unvalidated on purpose. `GET /scenarios?band=Z9`
 * answers 422 naming the allowed values rather than silently ignoring the parameter, so
 * re-checking the vocabulary here would be a second copy of the enum that can disagree
 * with the first.
 */

import Link from "next/link";

import { ScenarioCard } from "@/components/ScenarioCard";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { ApiError, CEFR_ORDER, type ScenarioSummary } from "@/lib/api";
import { serverRequest } from "@/lib/server-api";

export const dynamic = "force-dynamic";

export const metadata = { title: "Scenarios — SpeakLab" };

function query(params: Record<string, string | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) if (value) search.set(key, value);
  const encoded = search.toString();
  return encoded ? `?${encoded}` : "";
}

export default async function ScenariosPage({
  searchParams,
}: {
  searchParams: Promise<{ band?: string; category?: string }>;
}) {
  const { band, category } = await searchParams;

  let scenarios: ScenarioSummary[] = [];
  let failure: string | null = null;
  try {
    scenarios = await serverRequest<ScenarioSummary[]>(`/scenarios${query({ band, category })}`);
  } catch (error) {
    failure =
      error instanceof ApiError
        ? error.message
        : "The scenario list could not be loaded.";
  }

  // Derived from the rows on screen rather than from a constant, so a seed file that
  // adds a category does not need a second edit here to become filterable.
  const categories = [...new Set(scenarios.map((one) => one.category))].sort();

  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-col gap-2">
        <h1 className="text-3xl font-semibold tracking-tight">Choose a scenario</h1>
        <p className="max-w-2xl text-muted-foreground">
          Each one is a role-play with a goal and a persona who will push back. You speak,
          it answers out loud, and at the end you get a report of what actually happened.
        </p>
      </header>

      {failure && (
        <Alert variant="destructive">
          <AlertDescription>{failure}</AlertDescription>
        </Alert>
      )}

      <div className="flex flex-col gap-3">
        <FilterRow label="Level">
          <FilterLink href={`/scenarios${query({ category })}`} active={!band}>
            any
          </FilterLink>
          {CEFR_ORDER.map((value) => (
            <FilterLink
              key={value}
              href={`/scenarios${query({ band: value, category })}`}
              active={band === value}
            >
              {value}
            </FilterLink>
          ))}
        </FilterRow>

        {categories.length > 1 && (
          <FilterRow label="Setting">
            <FilterLink href={`/scenarios${query({ band })}`} active={!category}>
              any
            </FilterLink>
            {categories.map((value) => (
              <FilterLink
                key={value}
                href={`/scenarios${query({ band, category: value })}`}
                active={category === value}
              >
                {value.replace(/[_-]+/g, " ")}
              </FilterLink>
            ))}
          </FilterRow>
        )}
      </div>

      {!failure && scenarios.length === 0 ? (
        <Alert>
          <AlertDescription>
            No scenarios match that filter. If the catalogue is empty everywhere, the
            seeds have not been loaded — run <code className="font-mono">make seed</code>.
          </AlertDescription>
        </Alert>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {scenarios.map((scenario) => (
            <ScenarioCard key={scenario.slug} scenario={scenario} />
          ))}
        </div>
      )}
    </div>
  );
}

function FilterRow({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="w-14 text-xs text-muted-foreground">{label}</span>
      {children}
    </div>
  );
}

function FilterLink({
  href,
  active,
  children,
}: {
  href: string;
  active: boolean;
  children: React.ReactNode;
}) {
  return (
    <Badge asChild variant={active ? "default" : "outline"}>
      <Link href={href} aria-current={active ? "true" : undefined}>
        {children}
      </Link>
    </Badge>
  );
}
