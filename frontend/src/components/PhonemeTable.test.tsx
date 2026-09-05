/**
 * The confusion pairs — the output PRD §7.4 is written around.
 *
 * The filtering is the whole substance of this component. *Every* scored phone carries a
 * `recognized_phone`, including the ones produced perfectly, so a table that listed them
 * all would be 250 rows of noise with the two that matter somewhere inside it.
 */

import { render, screen } from "@testing-library/react";

import { PhonemeTable } from "@/components/PhonemeTable";
import { makePhoneme } from "@/test/fixtures";

const SUMMARY = {
  phones: 10,
  mean_gop: -1.5,
  median_gop: -0.5,
  percentile_5: -3.0,
  r_composites: 0,
  blank_dominated: 0,
};

test("a repeated substitution is counted, not listed once per occurrence", () => {
  // "/θ/ → /s/ ×4" is the shape of the finding. Four rows saying the same thing would
  // be the same information arranged so nobody notices the pattern.
  render(
    <PhonemeTable
      phonemes={[
        makePhoneme({ word_idx: 0, canonical_phone: "TH", recognized_phone: "s", gop: -9.4 }),
        makePhoneme({ word_idx: 1, canonical_phone: "TH1", recognized_phone: "s", gop: -8.2 }),
        makePhoneme({ word_idx: 2, canonical_phone: "TH", recognized_phone: "s", gop: -7.7 }),
        makePhoneme({ word_idx: 3, canonical_phone: "TH", recognized_phone: "s", gop: -6.1 }),
      ]}
      summary={SUMMARY}
    />,
  );

  expect(screen.getByText("/TH/")).toBeInTheDocument();
  expect(screen.getByText("[s]")).toBeInTheDocument();
  expect(screen.getByText("4")).toBeInTheDocument();
  expect(screen.getByText("-9.40")).toBeInTheDocument();
});

test("stress digits are stripped, so TH and TH1 are one row", () => {
  render(
    <PhonemeTable
      phonemes={[
        makePhoneme({ word_idx: 0, canonical_phone: "IH0", recognized_phone: "iː", gop: -5.0 }),
        makePhoneme({ word_idx: 1, canonical_phone: "IH1", recognized_phone: "iː", gop: -4.0 }),
      ]}
      summary={SUMMARY}
    />,
  );

  expect(screen.getAllByText("/IH/")).toHaveLength(1);
  expect(screen.getByText("2")).toBeInTheDocument();
});

test("phones produced acceptably are not listed even though they name a sound", () => {
  // The filter that makes the table readable. GOP 0 with recognized_phone "ð" for a /DH/
  // is correct speech — the model naming the sound it heard, which happens to be right.
  render(
    <PhonemeTable
      phonemes={[
        makePhoneme({ word_idx: 0, canonical_phone: "DH", recognized_phone: "ð", gop: 0 }),
        makePhoneme({ word_idx: 1, canonical_phone: "TH", recognized_phone: "s", gop: -9.4 }),
      ]}
      summary={SUMMARY}
    />,
  );

  expect(screen.queryByText("/DH/")).not.toBeInTheDocument();
  expect(screen.getByText("/TH/")).toBeInTheDocument();
});

test("a phone with no clear winner produces no row", () => {
  // Invariant I2: the model asserted nothing, so the table claims nothing.
  render(
    <PhonemeTable
      phonemes={[
        makePhoneme({ word_idx: 0, canonical_phone: "TH", recognized_phone: null, gop: -9.4 }),
      ]}
      summary={SUMMARY}
    />,
  );

  expect(screen.getByText(/No sound in this reading was clearly replaced/)).toBeInTheDocument();
});

test("a clean reading says so rather than showing an empty table", () => {
  render(
    <PhonemeTable
      phonemes={[makePhoneme({ word_idx: 0, gop: 0 })]}
      summary={SUMMARY}
    />,
  );

  expect(screen.getByText(/That is the good outcome/)).toBeInTheDocument();
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
});

test("the most frequent substitution comes first", () => {
  render(
    <PhonemeTable
      phonemes={[
        makePhoneme({ word_idx: 0, canonical_phone: "V", recognized_phone: "b", gop: -6.0 }),
        makePhoneme({ word_idx: 1, canonical_phone: "TH", recognized_phone: "s", gop: -9.4 }),
        makePhoneme({ word_idx: 2, canonical_phone: "TH", recognized_phone: "s", gop: -8.0 }),
      ]}
      summary={SUMMARY}
    />,
  );

  const cells = screen.getAllByText(/^\/(TH|V)\/$/);
  expect(cells[0]).toHaveTextContent("/TH/");
  expect(cells[1]).toHaveTextContent("/V/");
});
