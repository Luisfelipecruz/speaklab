/**
 * The heatmap, and the two decisions in it that are easy to get quietly wrong.
 *
 * **Word indices.** The scorer counts a word as a token containing a letter, and the
 * heatmap has to split the same text the same way or every tint lands on the wrong word.
 * That is not a hypothetical: the em dash in two of the twelve seeded passages is exactly
 * the token that made the *service* desync, and the browser splits the same string with
 * different code. So the alignment is asserted here as well as there.
 *
 * **The worst phone, not the mean.** A word is mispronounced if any sound in it was.
 */

import { render, screen } from "@testing-library/react";

import { PhonemeHeatmap } from "@/components/PhonemeHeatmap";
import { makePhoneme } from "@/test/fixtures";

const SUMMARY = {
  phones: 10,
  mean_gop: -1.5,
  median_gop: -0.5,
  percentile_5: -3.0,
  r_composites: 0,
  blank_dominated: 0,
};

function bandOfWord(text: string): string | null {
  const node = screen.getByText(text, { selector: "span[data-band]" });
  return node.getAttribute("data-band");
}

test("a word whose worst phone is below the fifth percentile is marked", () => {
  render(
    <PhonemeHeatmap
      body="the theatre"
      phonemes={[
        makePhoneme({ word: "the", word_idx: 0, gop: 0 }),
        makePhoneme({ word: "theatre", word_idx: 1, canonical_phone: "TH", gop: -9.4 }),
      ]}
      summary={SUMMARY}
    />,
  );

  expect(bandOfWord("theatre")).toBe("weakest");
  expect(bandOfWord("the")).toBe("clear");
});

test("one bad phone marks the word even when its other phones are perfect", () => {
  // The averaging trap. Mean of [0, 0, 0, 0, -9.4] is -1.88, which sits above the
  // percentile and would leave the one word the reader needs to find untinted.
  render(
    <PhonemeHeatmap
      body="thistles"
      phonemes={[
        makePhoneme({ word: "thistles", word_idx: 0, phone_idx: 0, canonical_phone: "TH", gop: -9.4 }),
        makePhoneme({ word: "thistles", word_idx: 0, phone_idx: 1, gop: 0 }),
        makePhoneme({ word: "thistles", word_idx: 0, phone_idx: 2, gop: 0 }),
        makePhoneme({ word: "thistles", word_idx: 0, phone_idx: 3, gop: 0 }),
        makePhoneme({ word: "thistles", word_idx: 0, phone_idx: 4, gop: 0 }),
      ]}
      summary={SUMMARY}
    />,
  );

  expect(bandOfWord("thistles")).toBe("weakest");
});

test("a standalone em dash takes no word index, so the tints do not slide", () => {
  // The regression that broke two of the twelve seeded passages at the service. Here the
  // consequence would be silent and worse: every word after the dash tinted by the score
  // of its neighbour.
  render(
    <PhonemeHeatmap
      body="casual — she should"
      phonemes={[
        makePhoneme({ word: "casual", word_idx: 0, gop: 0 }),
        makePhoneme({ word: "she", word_idx: 1, gop: 0 }),
        makePhoneme({ word: "should", word_idx: 2, canonical_phone: "SH", gop: -8.1 }),
      ]}
      summary={SUMMARY}
    />,
  );

  expect(bandOfWord("should")).toBe("weakest");
  expect(bandOfWord("she")).toBe("clear");
});

test("the marked count is shown, so a few tinted words do not read as a bad reading", () => {
  render(
    <PhonemeHeatmap
      body="the theatre on third street"
      phonemes={[
        makePhoneme({ word_idx: 0, gop: 0 }),
        makePhoneme({ word_idx: 1, gop: -9.4 }),
        makePhoneme({ word_idx: 2, gop: 0 }),
        makePhoneme({ word_idx: 3, gop: 0 }),
        makePhoneme({ word_idx: 4, gop: 0 }),
      ]}
      summary={SUMMARY}
    />,
  );

  expect(screen.getByText("1 of 5 words marked")).toBeInTheDocument();
});

test("the legend says the bands are relative, because no calibrated threshold exists", () => {
  // The interface must not imply a pass mark it does not have — a tinted word here
  // means "the weakest sound in this reading", not "you got this wrong".
  render(
    <PhonemeHeatmap body="the theatre" phonemes={[makePhoneme()]} summary={SUMMARY} />,
  );

  expect(screen.getByText(/relative to this reading/)).toBeInTheDocument();
  expect(screen.getByText(/not a pass mark/)).toBeInTheDocument();
});

test("with no summary nothing is marked rather than everything", () => {
  // An attempt scored while `pron` was down has phones from an earlier run and no
  // summary. Comparing against a null threshold must not tint the whole passage.
  render(
    <PhonemeHeatmap
      body="the theatre"
      phonemes={[
        makePhoneme({ word_idx: 0, gop: 0 }),
        makePhoneme({ word_idx: 1, gop: -9.4 }),
      ]}
      summary={null}
    />,
  );

  expect(bandOfWord("the")).toBe("clear");
  expect(bandOfWord("theatre")).toBe("clear");
});

test("each marked word says which sound and what was heard instead", () => {
  render(
    <PhonemeHeatmap
      body="theatre"
      phonemes={[
        makePhoneme({ word: "theatre", word_idx: 0, canonical_phone: "TH", recognized_phone: "s", gop: -9.4 }),
      ]}
      summary={SUMMARY}
    />,
  );

  expect(screen.getByTitle("TH — GOP -9.40, heard s")).toBeInTheDocument();
});

test("a phone with no clear winner does not have a sound invented for it", () => {
  // Invariant I2 in the interface: the model reported nothing won that segment, so the
  // tooltip says the score and stops.
  render(
    <PhonemeHeatmap
      body="theatre"
      phonemes={[
        makePhoneme({ word: "theatre", word_idx: 0, canonical_phone: "TH", recognized_phone: null, gop: -4.2 }),
      ]}
      summary={SUMMARY}
    />,
  );

  expect(screen.getByTitle("TH — GOP -4.20")).toBeInTheDocument();
});
