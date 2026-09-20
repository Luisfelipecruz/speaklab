/**
 * The sounds of a script, named and measured.
 *
 * The fixture is the profile four takes of one speaker's own script produced. What is
 * tested is that the name is what is read rather than the code, that the speaker's own
 * words come with it, that every row prints what it counted, and that a script with
 * nothing scored yet shows nothing instead of an empty frame.
 */

import { render, screen } from "@testing-library/react";

import { Sounds } from "@/components/Sounds";
import type { SoundOut } from "@/lib/api";

const CAVEAT = "Scored from your takes of this script.";

const MEASURED: SoundOut[] = [
  {
    phone: "IY",
    name: 'the vowel in "see"',
    instances: 15,
    takes: 4,
    mean_gop: -3.79,
    words: ["peels", "these", "we"],
  },
  {
    phone: "DH",
    name: 'the "th" in "this"',
    instances: 16,
    takes: 4,
    mean_gop: -3.43,
    words: [],
  },
];

test("a sound is read as a sound, not as the code the model thinks in", () => {
  render(<Sounds sounds={MEASURED} caveat={CAVEAT} />);

  expect(screen.getByText('the vowel in "see"')).toBeInTheDocument();
  expect(screen.queryByText(/\/IY\//)).not.toBeInTheDocument();
});

test("the words beside a sound are the speaker's own", () => {
  render(<Sounds sounds={MEASURED} caveat={CAVEAT} />);

  expect(screen.getByText("in your peels, these, we")).toBeInTheDocument();
});

test("every row prints what it counted", () => {
  render(<Sounds sounds={MEASURED} caveat={CAVEAT} />);

  expect(screen.getByText("15 times across 4 takes, mean score -3.8")).toBeInTheDocument();
  expect(screen.getByText("16 times across 4 takes, mean score -3.4")).toBeInTheDocument();
  expect(screen.getByText(CAVEAT)).toBeInTheDocument();
});

test("a sound with none of the script's words beside it still says its measurement", () => {
  render(<Sounds sounds={[MEASURED[1]]} caveat={CAVEAT} />);

  expect(screen.getByText('the "th" in "this"')).toBeInTheDocument();
  expect(screen.queryByText(/in your/)).not.toBeInTheDocument();
});

test("nothing scored yet draws nothing rather than an empty list", () => {
  const { container } = render(<Sounds sounds={[]} caveat={CAVEAT} />);

  expect(container).toBeEmptyDOMElement();
});

test("one instance in one take is said in the singular", () => {
  render(
    <Sounds
      sounds={[{ ...MEASURED[0], instances: 1, takes: 1 }]}
      caveat={CAVEAT}
    />,
  );

  expect(screen.getByText("1 time across 1 take, mean score -3.8")).toBeInTheDocument();
});
