/**
 * Each sound, placed against this speaker's own recent readings.
 *
 * **Why a distance and not a score.** Goodness-of-pronunciation moves with the microphone,
 * the room and how far the speaker sat from it. A raw number compared across weeks is
 * partly a comparison of equipment, so what is drawn is how far each sound sits from the
 * same speaker's own baseline, in standard deviations. Nothing here is ever compared
 * against another person.
 *
 * **A sound with no baseline is shown and not scored.** In a first month that is every
 * sound. The row says so in words rather than drawing a bar at zero, which would place a
 * speaker exactly on a baseline that does not exist.
 *
 * **There is no pass mark.** No GOP threshold is calibrated in this system — the method is
 * settled and the numbers need recordings from more than one speaker — so this panel ranks
 * sounds against each other and against their own history, and never says a sound is
 * wrong. The bar is a position, not a grade.
 */

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { Gate, PhoneTrend } from "@/lib/api";
import { cn } from "@/lib/utils";

export interface PhonemeTrendProps {
  phones: PhoneTrend[];
  gate: Gate;
}

/** Where a z-score sits on a bar that runs from three deviations below to three above. */
function offset(z: number): { left: number; width: number } {
  const clamped = Math.max(-3, Math.min(3, z));
  const centre = 50;
  const distance = (Math.abs(clamped) / 3) * 50;
  return clamped < 0
    ? { left: centre - distance, width: distance }
    : { left: centre, width: distance };
}

export function PhonemeTrend({ phones, gate }: PhonemeTrendProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Sound by sound</CardTitle>
        <CardDescription>
          Each sound against your own recent readings of it, in standard deviations. Left
          of the middle is below your usual; right of it is above.
        </CardDescription>
      </CardHeader>

      <CardContent className="flex flex-col gap-4">
        {!gate.shown ? (
          <p className="text-sm text-muted-foreground" data-testid="phone-gate">
            {gate.reason}
          </p>
        ) : phones.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No sound has turned up often enough in your readings yet to be worth a line of
            its own.
          </p>
        ) : (
          <ul className="flex flex-col gap-3">
            {phones.map((phone) => (
              <li key={phone.phone} className="flex flex-col gap-1">
                <div className="flex flex-wrap items-baseline gap-2 text-sm">
                  <span className="font-medium tabular-nums">/{phone.phone}/</span>
                  <span className="text-xs text-muted-foreground">
                    {phone.samples} instance{phone.samples === 1 ? "" : "s"}
                  </span>
                  {phone.z === null ? (
                    <Badge variant="outline" className="ml-auto text-xs">
                      no baseline yet
                    </Badge>
                  ) : (
                    <span
                      className="ml-auto text-sm font-semibold tabular-nums"
                      data-testid={`z-${phone.phone}`}
                    >
                      {phone.z > 0 ? "+" : ""}
                      {phone.z.toFixed(1)} sd
                    </span>
                  )}
                </div>

                {phone.z === null ? (
                  <p className="text-xs text-muted-foreground">
                    Scoring {phone.mean_gop.toFixed(1)} today. Read a few more passages and
                    this becomes a comparison against yourself.
                  </p>
                ) : (
                  <div
                    className="relative h-2 w-full rounded-full bg-muted"
                    role="presentation"
                  >
                    <span className="absolute inset-y-0 left-1/2 w-px bg-border" />
                    <span
                      className={cn(
                        "absolute inset-y-0 rounded-full",
                        phone.z < 0 ? "bg-amber-500/70" : "bg-primary",
                      )}
                      style={{
                        left: `${offset(phone.z).left}%`,
                        width: `${Math.max(1, offset(phone.z).width)}%`,
                      }}
                    />
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
