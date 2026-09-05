/**
 * The passage, with each word tinted by the weakest sound in it.
 *
 * **The bands are relative to this reading, and the copy says so.** There is no
 * calibrated GOP threshold in this system: m0 settled the *method* — a percentile of the
 * correct-speech distribution, per phone — and could not settle the *numbers*, because it
 * had one speaker and ten probes (handoff Q2). `PRON_GOP_THRESHOLDS` is deliberately
 * empty, and a heatmap that invented one would be the interface deciding which sounds a
 * learner is told to work on, on the strength of a constant somebody typed.
 *
 * So the bands come from the reading's own distribution — its 5th percentile and its
 * median — and the legend calls them *the weakest sounds in this reading* rather than
 * mistakes. That framing is not a hedge, it is what the numbers support: within one
 * reading, GOP genuinely ranks sounds against each other. What it cannot yet do is say
 * whether the weakest one was actually wrong.
 *
 * A consequence worth being awake to: about 5 % of words will be tinted even in a
 * flawless reading, because a percentile always has something below it. That is why the
 * strongest band is styled as *attention*, not as *error*, and why the count is shown —
 * "3 of 79" reads very differently from a page of red.
 *
 * **`worstByWord`, not the mean.** A word is mispronounced if any sound in it was, and
 * averaging one bad phone with four good ones hides exactly the word the learner needs
 * to find. `lib/api.ts` holds that function because the table below uses the same rule.
 */

import { Badge } from "@/components/ui/badge";
import { type PhonemeScore, type PronunciationSummary, worstByWord } from "@/lib/api";
import { cn } from "@/lib/utils";

export interface PhonemeHeatmapProps {
  body: string;
  phonemes: PhonemeScore[];
  summary: PronunciationSummary | null;
}

/** The same rule `infra/pron/g2p.py` uses: a word is a token containing a letter. */
const HAS_LETTER = /[A-Za-z]/;

type Band = "weakest" | "weaker" | "clear";

function bandOf(gop: number, weakest: number, weaker: number): Band {
  if (gop <= weakest) return "weakest";
  if (gop <= weaker) return "weaker";
  return "clear";
}

const BAND_STYLES: Record<Band, string> = {
  weakest: "bg-amber-500/25 text-amber-950 dark:text-amber-100 underline decoration-amber-600 decoration-2 underline-offset-4",
  weaker: "bg-amber-500/10",
  clear: "",
};

export function PhonemeHeatmap({ body, phonemes, summary }: PhonemeHeatmapProps) {
  const worst = worstByWord(phonemes);

  // Tokens are split for *display* and indexed to match the scorer's word indices, which
  // count only tokens containing a letter. Punctuation-only tokens keep their place in
  // the rendered text and take no index — the same split that, done differently, desynced
  // two passages at the service (see `infra/pron/g2p.py`).
  let wordIndex = 0;
  const tokens = body.split(/(\s+)/).map((token) => {
    if (!HAS_LETTER.test(token)) return { token, index: null as number | null };
    return { token, index: wordIndex++ };
  });

  const weakest = summary?.percentile_5 ?? Number.NEGATIVE_INFINITY;
  const weaker = summary?.median_gop ?? Number.NEGATIVE_INFINITY;

  const flagged = [...worst.values()].filter((phone) => phone.gop <= weakest).length;
  const words = wordIndex;

  return (
    <div className="flex flex-col gap-4">
      <p className="text-lg leading-relaxed tracking-[-0.005em]">
        {tokens.map(({ token, index }, position) => {
          const phone = index === null ? undefined : worst.get(index);
          if (!phone) return <span key={position}>{token}</span>;
          const band = bandOf(phone.gop, weakest, weaker);
          return (
            <span
              key={position}
              data-band={band}
              data-word-index={index}
              title={`${phone.canonical_phone.replace(/[0-2]$/, "")} — GOP ${phone.gop.toFixed(2)}${
                phone.recognized_phone ? `, heard ${phone.recognized_phone}` : ""
              }`}
              className={cn("rounded px-0.5", BAND_STYLES[band])}
            >
              {token}
            </span>
          );
        })}
      </p>

      <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
        <Badge variant="outline" className="bg-amber-500/25">
          weakest sounds
        </Badge>
        <Badge variant="outline" className="bg-amber-500/10">
          below this reading&rsquo;s median
        </Badge>
        <span>
          {flagged} of {words} words marked
        </span>
      </div>

      <p className="text-xs leading-relaxed text-muted-foreground">
        These bands are <strong>relative to this reading</strong>, not a pass mark. They
        rank the sounds you produced against each other, so a few words are marked even
        when everything was clear. A calibrated threshold needs recordings from more than
        one speaker, which is why there is not one yet.
      </p>
    </div>
  );
}
