# 0016 — The grammar page

Status: accepted

Grammar practice needs a place where a learner sees which grammar they get wrong, in their
own sentences, and what to practise: their categories and sentences, the forms they use and
how correctly, and the scenario that draws out the weakest one. Three questions decide its
shape: whether it is a tab of the progress page or a section of its own; whether it shows a
percentage at all while the detector's precision is 0.500; and what floor naming the
weakest form needs. Decision 0015 §6 is the background to all three: on the live corpus the
only two corrections that joined a verb form are the model's false positives.

It depends on a fix. Every correction a learner is shown comes from the session report, and
ending a session straight after speaking waits for the last turn before it writes that
report (0014 §7).

## What was decided

1. **A section of its own, `/grammar`, read from the corrections rather than the
   snapshots.** One new operation, `GET /grammar`.
2. **Evidence first.** Every correction in the sentence it was said in, marked on the
   transcript's own words, with what was proposed instead, which detector proposed it, and
   a link to the conversation.
3. **No percentage on any screen.** Not here, and not beside the tenses on the
   progress page either. Counts, with the corrections behind them.
4. **A form is named for practice at ten contexts and five corrections**, the one right
   least often among those, with a scenario at the learner's level that asks for it.
5. **The caveat says none of it was checked by a person**, and names both halves of the
   detector's measured quality.

---

## 1. Its own section, and why not a tab of progress

The progress page answers *am I getting better?* and it reads materialised snapshots,
because a trend recomputed from raw rows on every page load gets slower every week the
learner practises. A snapshot holds counts and no sentences. This page's whole content is
sentences, so it reads the stored corrections for the window — every row, without its
transcript — and the transcripts of the few it quotes.

It computes its counts the way the snapshots do: the same rule for which corrections count
(`is_counted` — a correction on words the recogniser was unsure of, or one the model hedged
on, is shown and not counted), and the same tally per verb form. The two pages cannot
disagree about the same speech.

The window is the progress page's, 30 days by default, with the same `?days=`.

## 2. What is on it

- **One line of totals**: corrections, words, turns, conversations.
- **The caveat.**
- **The form to practise**, or why none is named yet (§4).
- **Your corrections, by kind** — each category the learner has a correction in, most
  counted first, with the category's one-line description (the same gloss the labelling
  model is given, so the two cannot drift), the counted rate per hundred words, how many
  were shown and not counted, and the newest five in full. Each is the sentence around it,
  cut at its own full stops or 90 characters either side — the recogniser often writes a
  turn as one unpunctuated sentence — with the correction's words marked as they are on
  the transcript: amber and solid when it counts, grey and dotted when it does not. A
  correction whose stored offsets do not hold its words is shown on its own, never marked
  on the wrong words, by the same check the transcript uses.
- **The verb forms you used** — each tense and modal said or needed, as *right 9 of 13*
  or *needed 2, never said*, with what the count is made of (*said 12 times · corrected
  once · needed once where you said something else*) and the corrections behind it.

Categories with no correction are not listed, and an account whose speech was analysed and
flagged nothing is told that *nothing was flagged* is not *no mistakes*: the detector finds
about a third of what a person marks.

## 3. No percentage, anywhere

0015 put a percentage beside a verb form from ten contexts, where the 95 % interval around
0.8 is 0.49 to 0.94. That floor is about the size of the sample. It does nothing about the
corrections the count is made from, and those are the larger error: on the hand-checked set
half the model's corrections are wrong and it finds a third of the mistakes. A wrong
correction counts against a form used correctly; a missed one counts as right. The
percentage carries both errors and shows neither.

The end-to-end run in §6 is what that looks like. Of the model's four verb-tense
corrections on sentences written for the run, three pointed at a past simple that was
right and asked for a past perfect — so the past simple read *right 4 of 8* and the past
perfect *needed 3, never said*, and every one of those seven figures moved for the
detector's mistake rather than the speaker's. As counts, with the corrections listed under
them, a learner can see that and disagree. As *50 %*, they cannot.

So the pages show counts. **The progress page shows the same**: *right 9 of 13* is what the
repertoire shows too, not *right 9 of 13 · 69 %*, because the same
figure presented two ways on two pages is worse than either. The API still sends the
proportion above its floor, in the report's `form_accuracy` and in every snapshot; no
screen renders it. It comes back when detection precision is measured at or above the
0.70 bar on enough proposals to decide it — twenty, by the rule the evaluation harness
already applies — and then the change is to the two components, not to the data.

## 4. Naming a form to practise

A form is **eligible** once it has come up at least **10** times — said, or needed where
something else was said, the same floor 0015 set for a proportion — **and** been corrected
at least **5** times, said wrongly or needed and not said (`GRAMMAR_MIN_FORM_CORRECTIONS`).
Among the eligible, the one right least often is named: its counts, and a sentence saying
it is the lowest of those with enough behind them.

**Why five.** The corrections are the uncertain part, so the floor is on them. If half the
model's corrections were wrong, five all wrong would happen about one time in thirty; three
all wrong, one in eight — too often for a recommendation that decides what somebody spends
their practice on. It is reasoned from the measured precision and not measured itself;
revisit it with the precision.

**Why also ten contexts.** Five corrections in five uses is a sample of five.

**The scenario.** An active scenario whose declared target grammar includes the form — at
the learner's self-assessed band where one exists, the first by name otherwise. A B1
learner weakest on the present perfect is sent to the doctor's appointment, not the
airport rebooking that comes first alphabetically. A form no scenario is written to draw
out is still named, and the page says so.

**Below the floor**, nothing is named and the page says which form is nearest and how far
it is: *the form with the most corrections so far is the future will: 2 corrections, from
the 2 times it was said or needed* — and what the floor is and why. An empty card would read
as *nothing to work on*, which nothing measured.

The progress page's own recommendations do not use this. They rank corrected categories,
unused forms and weak sounds; a fourth source with its own floor would be a change to that
ranking.

## 5. On the live corpus

Computed read-only for the one account with practice on it, over 30 days and over a year
(the same, because the corpus is two calendar days): 11 turns, 428 words, three
conversations, **17 corrections of which 8 count** — five categories, word order first (3
counted, 7 not). Seven verb forms. **No form is named**: the nearest is the future *will*,
with two corrections — both the model's false positives from 0015 §6, `is going to be long
term` and `we can test` rewritten as futures. This is the floor doing the one thing it is
for.

## 6. Seen end to end

On a throwaway account with a self-assessed band of B1: three sentences synthesised by the
`tts` service, posted as turns in two scenarios, heard by `small.en`, analysed, and both
sessions ended through the API. Both reports complete; 13 corrections — 8 from the model, 5
from the rules. The page, server-rendered in a browser at 1440 and 375 px, light and dark:
no horizontal scroll, no console error, no percent sign in the page. The present simple
reached the floor exactly — corrected 5 times in 10 — and was named, with *Apartment
viewing*, the B1 scenario that asks for it.

Three findings on the way, none of them the page's, recorded here because this page is
where a learner meets them:

- **The model rewrote three correct past simples as past perfects** (`I finished the
  report` → `I had finished the report`), and filed three real agreement or tense errors
  under number, pronoun and omission. §3 is about exactly this.
- **The agreement rule proposed `she says` for `she say`** in a narrative whose past is set
  a sentence earlier (`Yesterday I finished…`); `she said` was needed. The rule's silence on
  a past context reads only the sentence it is in. It is the first rule proposal on speech
  a person could have said, and it is a wrong fix; `tests/test_rules.py` does not hold the
  shape.
- **The recogniser heard `I fix two bugs` as `I fixed two bugs`** — the language prior
  0014 §8 warned would erase errors before any detector sees them.

The account and both sessions were deleted afterwards; the corpus is eleven sessions and
eleven learner turns, as before.

## 7. What is not settled

- **When the percentage comes back** — §3 names the condition, and it is not met.
- **Both floors are reasoned, not measured.** Five corrections is an argument from a
  precision measured on six proposals.
- **The rule layer's past context is one sentence wide** (§6). Widening it spends the
  planted-error measurement's credibility unless a new held-out set is written first.
- ~~**The drill.**~~ *Settled by 0017: it starts from this page, on a page of its own, with
  no pass mark.*
