# 0029 — What a take tells the speaker

Status: accepted

A take is measured five ways and, until now, said almost none of it. The first person to
rehearse a script of their own on this product recorded four sections, and could not tell
from the screens whether the problem was their pronunciation, their fluency, their length
or their tone — while the database already held the answer to four of those five. This
records what was added, all of it arithmetic over counts that already existed, and the two
defects the same session uncovered.

## What was decided

1. **A word that came out differently is sorted into what kind of difference it is.**
   `services/fidelity_kinds.classify` returns `figure`, `ending` or `different-word` for
   every substitution. A figure is the same number written two ways
   (`services/numbers.value_of`); an ending is one word being the other plus a final `s`,
   `es`, `ed`, `ing`, `er`, `'s`, `'re`, `'d` or `'ll`, or exactly one of the two carrying
   an apostrophe, or the two agreeing for four characters and then diverging; everything
   else is a different word. One number covering all three is correct and tells nobody
   what to do: a dropped plural is something to practise, a misheard word may be the
   microphone, and the third is not the speaker's doing at all.
2. **A number said correctly is not counted as a difference.** `services/wer.py` leaves
   numbers alone deliberately, and for a passage everybody reads that is the honest
   reading — a numeral is genuinely not the word that was said, and mapping them silently
   would hide a real difference between recognisers. For a script somebody wrote it is
   the wrong answer: a speaker who says "eleven" and is transcribed "11" said the word.
   So a take's alignment counts `figures` on their own, leaves them out of `substitutions`
   and out of the rate, and the screen lists them under a heading that says they are not
   counted. `services/wer.py` itself is unchanged, because read-aloud's published word
   error rate must stay comparable with every earlier run of it.
3. **A sound is named in words, and shown where the take is.** `services/phone_names.py`
   names all thirty-nine — *the vowel in "see"*, *the "th" in "this"* — and validates
   itself against the inventory at import, the way `infra/pron/phone_map.py` does. `/IY/`
   is the right code and useless to the person who recorded the take. Beside each name are
   up to three words of the speaker's own script the sound was scored inside, because a
   sound is practised in words and theirs are the ones they are about to say again. The
   list appears on the script's page *and* under a take, which is where somebody is
   standing when they ask.
4. **Only the weakest few sounds are offered, and each prints what it counted.** The floor
   is the one `next_up` already used — two takes and five instances — because a sound
   heard twice describes the microphone as much as the mouth. `REHEARSAL_SOUNDS_SHOWN` is
   five: a list of twenty is a list nobody practises, and below the top few the differences
   are smaller than the difference between two takes of the same words. Every row carries
   its instances, its takes and its mean, and the caveat says the score is a distance from
   what the model expected rather than a mark.
5. **Every measure of a take sits beside the same measure of the speaker's own previous
   take.** Words a minute, how long it took, the share of the time paused, the fillers, the
   differences. This is the only comparison the product can defend: no corpus of good
   presentations has been measured here, so no norm is quoted — and a target to aim at can
   be taken from a take the speaker was happy with, which is a number they chose. The
   comparison is written out ("was 91 last take") rather than drawn as an arrow, because an
   arrow has a direction and a direction reads as a verdict. A minute slower is not worse,
   and nothing on this page is in a position to say whether it is.
6. **A take gets one sentence, assembled from its own counts.** The largest group of
   differences, whether it is the closest to the script yet, and which way the pace moved
   against the last take. No model writes it, nothing is stored, and it is not allowed to
   say the speaker did well or badly — only what the numbers beside it already show. With
   one take there is nothing to compare with and it says only what that take contains: a
   comparison invented from a single reading would be a trend made of one point.
7. **What is not measured is said out loud.** Tone, intonation and stress are outside this
   product, and a page that measures five things and is silent about a sixth reads as
   "nothing found" to somebody looking for it. One line under a take says so.
8. **A finished take leads somewhere.** Previous and next section in the header, and under
   a take a button to the next section, or to the whole script on the last one. Somebody
   who has just said a section says it again or says the next one; going back through the
   script page to do either is a dead end with a detour attached.

## Measured

- **The classifier, over twenty-five real pairs.** Every substitution from four takes of
  one speaker's own 144-word script, read out of the database and labelled by hand:
  **8 endings, 15 other words, 2 figures**. `tests/test_fidelity_kinds.py` asserts each
  pair on its own as well as the split, because two mistakes that cancel produce the right
  totals and the wrong screen.
- **What excluding figures changes on that script.** 2 of the 25 substitutions are a number
  written as a digit. The first section's word error rate falls from **0.200 to 0.171** and
  the third's from **0.140 to 0.116**; the other two sections contain no figure and do not
  move.
- **The sounds that script names, live**: *the vowel in "see"* (15 instances across 4
  takes, mean −3.79), *the "th" in "this"* (16, 4, −3.43), *the "ng" at the end of "sing"*
  (6, 3, −3.29), *the "z" at the end of "is"* (14, 4, −2.72), *the vowel in "her"* (19, 4,
  −2.67). The words offered beside them are the speaker's own — *billing*, *calling*,
  *publishing* for the "ng"; *is*, *calls*, *becomes* for the "z" — and they agree with the
  endings the word-level comparison found.
- All thirty-nine phones have a name, and the table is asserted against the scorer's
  inventory in both directions.

## Costs

- **The four-character stem rule calls two long words that start alike one word with a
  changed ending.** *presentation* against *president* is an ending by this rule and is
  not one. The alternative — a stemmer — is a dependency and a table of exceptions for a
  screen that is already saying "it may be what you said, or what the recogniser heard".
- **A take recorded before this has no kinds.** Old rows keep the alignment they were
  stored with; the field is absent, which reads as null, and the screen shows those
  differences the way it did before. Nothing is re-derived, and a figure in an old take is
  still counted against its rate.
- **The sounds list repeats the script page's own "next up" item.** The same sound is named
  in two places on purpose: one is the queue, the other is where somebody is standing.
- **One more sentence and one more line of copy under every take**, on a page that was
  already long.

## Revisit if

- Somebody rehearses a script full of figures and the *ending* rule starts mis-sorting
  words the four-character stem brings together: that is the point to buy a stemmer, and
  the pairs to test it against are already in `tests/test_fidelity_kinds.py`.
- A speaker wants a take compared with something other than their own last one. That needs
  a corpus of presentations measured the way this project measures everything else, and
  until one exists there is no honest number to compare against.
- Tone, intonation or stress become measurable here: this record's line saying they are not
  is the thing that has to change first.
