/**
 * The sounds of this script worth a speaker's time, named in words and in their own words.
 *
 * `/IY/` is the right code and the wrong thing to show somebody. It is what the acoustic
 * model thinks in, and the person who has just recorded a take wants to know which sound
 * in their mouth to listen to — so each one is named as *the vowel in "see"*, and the
 * words beside it are theirs, taken from the script they were scored in.
 *
 * **Every row prints what it counted**: how many times the sound was scored, across how
 * many takes, and the mean score. A row that cannot show its measurement is advice, and
 * this product does not give advice. The score is stated as a distance, not as a mark:
 * what it says is how far the recording sat from what the model expected, and the caveat
 * under the list says so rather than leaving a negative number to be read as a grade.
 */

import type { SoundOut } from "@/lib/api";

export function Sounds({
  sounds,
  caveat,
  heading = "The sounds worth your time in this script",
}: {
  sounds: SoundOut[];
  caveat: string;
  heading?: string;
}) {
  if (sounds.length === 0) return null;

  return (
    <section aria-labelledby="sounds" className="flex flex-col gap-3">
      <h3 id="sounds" className="text-sm font-semibold">
        {heading}
      </h3>
      <ul className="flex flex-col gap-2">
        {sounds.map((sound) => (
          <li
            key={sound.phone}
            className="flex flex-wrap items-baseline gap-x-3 gap-y-1 rounded-lg border border-border p-3"
          >
            <span className="font-medium">{sound.name}</span>
            {sound.words.length > 0 && (
              <span className="text-sm text-muted-foreground">
                in your {sound.words.join(", ")}
              </span>
            )}
            <span className="ml-auto text-xs text-muted-foreground">
              {sound.instances} {sound.instances === 1 ? "time" : "times"} across{" "}
              {sound.takes} {sound.takes === 1 ? "take" : "takes"}, mean score{" "}
              {sound.mean_gop.toFixed(1)}
            </span>
          </li>
        ))}
      </ul>
      <p className="max-w-[70ch] text-xs text-muted-foreground">{caveat}</p>
    </section>
  );
}
