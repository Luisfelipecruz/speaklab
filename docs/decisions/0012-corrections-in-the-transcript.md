# 0012 — Corrections in the transcript

Status: accepted

Every correction the analysis stores carries character offsets into its turn's
transcript, with a column comment saying they exist so the interface can underline the
words rather than restate them. Listed in a block under the conversation, a correction
such as "look department → look at the apartment" leaves the learner to scroll up and find
the turn by eye. This records how the offsets are used, and the four ways the marking can
go wrong that the design refuses.

## What was decided

1. **The report is the source.** No new field on the turn, no new operation.
2. **The transcript's words are what is marked, not the correction's quote.**
3. **A correction that cannot be placed is listed and never marked.**
4. **Overlapping corrections are not nested.**
5. **A doubtful correction looks different and says why; an absent one says nothing.**
6. **A numbered list under the bubble, not a tooltip.**

---

## 1. Where the corrections come from

The report that `POST /sessions/{id}/end` writes already carries every accepted correction
with the id of the turn it was found in, its offsets, the quoted words, the proposed
replacement, the explanation, the category, and two flags — whether the recogniser was
unsure of the words under it, and whether it counts towards any rate. The session page
already holds that report beside the turns. Joining them in the browser is a `Map` from
turn id to corrections, built once per report, and costs nothing on the server.

The alternative was a `corrections` field on every turn in `GET /sessions/{id}`, populated
by a second query. It was rejected for two reasons. The operation count stays at 25 of 30
with nothing to explain, which is the smaller one. The larger one is a property the report
has and a per-turn field would lose: **corrections appear when the session has been ended
and analysed, and not before.** The persona is instructed never to correct the speaker,
because the conversation is the practice and a lesson interrupting it is a different
product. Analysis runs behind each turn, so a per-turn field would fill in mid-conversation,
one bubble at a time, while the person is still speaking. Reading from the report means the
transcript marks nothing until the person has asked for the report — the same moment the
report itself appears.

The cost is that a session abandoned without being ended never shows its marks. That is
already true of its report, and the fix — if it is wanted — is to end it.

## 2. Whose words are marked

The offsets were found by searching the transcript for the model's quote, case-insensitively
and with any run of whitespace matching any other. So the stored quote can be "I complete
the story" while the words at its offsets are "i  complete the story". What is marked is
the slice of the transcript — the recogniser's spelling, the speaker's punctuation — and
the check that the slice is the quote compares letters and digits only, lowercased, which
is the normalisation the server used when it accepted the proposal.

## 3. What is refused

**Offsets that do not hold the quote.** A span that is null, that runs past the end of the
transcript, that is empty or reversed, or whose slice does not match the quote once
normalised, is not marked. The correction is still listed under the bubble, numbered, with
a note that it could not be placed. An underline under the wrong words would be a
correction pointing at something the speaker got right, which is worse than no underline.
Nothing in the current pipeline should produce such a row — the server located every span
itself — but the check is cheap and the failure it prevents is the one a learner would
remember.

**Overlaps.** Two accepted corrections can quote overlapping stretches of one turn. The
first by position is marked; the later one is listed with its number and no mark. Nested
marks would need markup that reads as one word belonging to two corrections, and the row
under the bubble says the same thing more plainly.

## 4. Two kinds of mark, and no third

A counted correction is marked amber with a solid underline. A correction the system does
not count — because the recogniser was unsure of a word under it, or because the model's
own confidence was below the floor — is marked grey with a dotted underline, and its row
carries the badge the report already uses: *may be a mishearing* or *low confidence*. It is
shown because a transcript with a hole in it is worse than one with a doubtful correction
on it, and it is kept out of every rate for the same reason the report keeps it out.

There is deliberately no mark for "no correction here". A turn with nothing flagged renders
its transcript plainly and no list, because the absence of corrections on a turn does not
say the turn was analysed — the report says how many turns were not — and a heading
reading "Proposed corrections" over an empty list would say "none found".

## 5. Why a list and not a tooltip

A tooltip puts the explanation where a phone cannot reach it and a screen reader does not
announce it. Each mark carries a superscript number and a visually hidden "correction n";
each number has a row under the bubble with the original struck through, the replacement,
the category and subcategory, the doubt badge if any, and the explanation. Everyone who
can read the bubble can read the row. The report's own list is unchanged: it groups and
counts; the bubble locates.

## 6. What was seen

A synthesised learner sentence — *"Yesterday I go to the office and I have meet with my
manager about the new feature. He say me that the deadline is on next week, so today I am
finish the tests."* — was posted as a turn through the real pipeline on a throwaway
account and the session ended. The recogniser heard "he say meet that" for "he say me
that", at word-level confidence low enough to flag. The labeller proposed four
corrections: two counted, two on the misheard words and marked as possible mishearings, and
one of those filed under word order — the category error decision 0006 §6 describes. All
four were marked on the words they quoted, at 1440 and 375 px, in both modes. The session
was then deleted so the corpus the evaluation reads is unchanged.
