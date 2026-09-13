# 0015 — Accuracy per form

Status: accepted · the percentage in §7 superseded by [0016](0016-the-grammar-page.md)

Decision 0007 said there was no accuracy figure per grammatical form, and why: errors are
filed under a taxonomy category, forms are counted by a parser, and nothing in the schema
linked one to the other. "Your present perfect is right seven times in ten" could not be
computed from anything stored. The grammar page needs that sentence, so the join has to
exist first — and it is a design decision rather than a formality, because a join done
carelessly is an invented number with decimal places on it.

This records how a correction is joined to a verb form, what accuracy per form is computed
as, what the parser had to be fixed for before either could be trusted, what it was
measured against, and what a learner is shown.

## What was decided

1. **A correction is joined to a form by parsing it.** The correction is applied to the
   transcript, the corrected text is parsed, and the verb phrases under the correction are
   compared before and after. `services/forms.py`.
2. **Both sides are kept**: the form the words were said in, and the form the correction
   needs. Two columns on `language_errors`, migration `0005`.
3. **Three categories join**: verb tense, subject–verb agreement, and a missing auxiliary
   or copula. Not only verb tense.
4. **Accuracy is target-like use**: right, over used plus needed-and-not-said.
5. **The parser's count of forms is fixed first**, in three places, because the join can
   be no more right than the forms it joins to.
6. **The count is shown from the first observation; the percentage from ten**, and the
   panel carries its own caveat about the corrections underneath.
7. **`make reparse`** re-derives the counts and the links for turns already analysed,
   with no model call.

---

## 1. The join

A correction arrives as a span of the transcript and the words to put there. The span says
*where*; it does not say *which verb*. `I never went to London` corrected to `I have never
been to London` has one verb under the span on each side, but `think that she go`
corrected to `think that she goes` has two under it and only one changes, and `enjoy to
swim` corrected to `enjoy swimming` has a verb under it that no correction touched.

So the join is a comparison, not an overlap. The verb phrases under the span in the
original and under the replacement in the corrected text are listed — each phrase being
the verb, its auxiliaries and, for a `going to` future, its complement — and every phrase
whose words are the same on both sides is struck out. What is left is what the correction
changed: `went` on one side and `have been` on the other, so `past_simple` said and
`present_perfect` needed.

Overlap alone — the error's span against the parser's verb-phrase spans — is not enough: it would file `think that she go` under the present simple twice, once
for a verb that was right, and `enjoy to swim` under the present simple once, for a verb
nothing corrected. Both are in the development set.

**One phrase, one correction.** When two corrections change the same verb phrase — a rule
and the model disagreeing about the same words — the first links and the second does not.
Otherwise one phrase is counted wrong twice. Rule rows come first, so where the two
disagree the rule's reading is the one counted.

**A correction that rewrites two phrases links to the first.** `go and see` corrected to
`went and saw` counts one present simple wrong, not two. A list per row would fix it. None
of the 93 labelled corrections in §5 and neither of the two live ones in §6 changes more
than one phrase, and a test pins the behaviour.

## 2. Both sides, and why not one

| Kept only | What it gets wrong |
|---|---|
| The form said | `I never went to London` counts against the past simple, and a learner who never attempts the present perfect never sees it fail — which is the learner who most needs to |
| The form needed | A present perfect said where the past simple belonged is not counted as a present perfect that went wrong |

So each correction carries both, and each can be empty: `She going` said no finite form,
and `enjoy to swim` corrects a complement no tense lives in. Per form, from the corrections
allowed to reach a rate (`is_counted`, the same rule every other rate uses):

- **used** — the parser's count, the same number the breadth chart shows;
- **wrong** — uses a correction changed;
- **missed** — times it was the form needed and another was said;
- **right** — used minus wrong;
- **accuracy** — right ÷ (used + missed).

That last is what second-language research calls target-like use: correct use over every
context that required the form plus every context the learner put it where it did not
belong. A form said five times correctly and needed twice more where something else was
said is five of seven.

## 3. Which categories join

Not only verb tense: the other two categories are about a verb's form too.

- **Agreement.** `she work` is a present simple built wrongly. Leaving it out would let a
  learner who drops the third-person *-s* in every sentence read *present simple: right
  every time* — the chart would be wrong in the flattering direction.
- **A missing auxiliary or copula.** `She going` is the commonest way to miss a present
  continuous; `I been to Paris` the commonest way to miss a present perfect.

Every other category is refused however close to a verb it sits. `did a mistake` corrected
to `made a mistake` changes a verb's words and not its form; filing it under the past
simple is exactly the invented join 0007 warned against.

## 4. The parser, fixed first

Writing the dev set turned up three places where the counter of forms was wrong, and a
join to a wrongly counted form is a wrong join.

| What it did | Example | Now |
|---|---|---|
| Read the tense from the head, which is a participle in every passive | `Is parking included?` — past simple; `has been cancelled` — past perfect | The tense is on the first finite auxiliary: present simple, present perfect |
| Never counted a do-supported verb | `I didn't go`, `Do you have…?` — no form at all | Past or present simple from `do`; an imperative (`Don't worry`, no subject) still not |
| Called `had been waiting` a *present* perfect continuous | — | `past_perfect_continuous`, a new name in the closed vocabulary |

And three narrower ones: a perfect or continuous with no tense (`having finished`, `being
told`) is not counted as one; `been` is never a finite verb, whatever the tagger says
(`I been to Paris` was a present simple); and a lexical verb the tagger labels an auxiliary
(`enjoy` in `I enjoy swimming`) still heads its own phrase.

**Measured on text the fixes were not written against** — every stored learner turn, the
repository's native English, and 2 791 words of package descriptions the counter had never
seen, old counter against new:

| | Texts | Words | Verb phrases | Changed | All of them corrections? |
|---|---:|---:|---:|---:|---|
| Stored learner turns | 11 | 428 | 48 | 4 | yes — 4 do-support |
| Native English in the repository | 56 | 2 454 | 288 | 12 | yes — 8 do-support, 3 present passive, 1 perfect passive |
| Package descriptions | 81 | 2 791 | 271 | 39 | yes — 28 present passive, 7 do-support, 4 perfect passive |

Fifty-five phrases changed and each was read: no change made a count wrong. One clause count
moved with them — `do not bother run detection`, a garbled imperative, is now one main
clause rather than none.

**One fix was tried and not made.** In `I complete the user story` from a real turn, the
corrected `completed` is tagged as a participle and the join finds no form on either side.
A participle with its own subject and no auxiliary is, in English, almost always a finite
past — so promoting it was tried against the same three sets. It would have changed seven
phrases; three were wrong (`get it put right`, a conjunct sharing `had`, a passive with
`garbage` in it). Three wrong in seven is worse than the gap it closes, and an overcount
tells a learner they practised something they did not.

## 5. The measurement

`make error-precision` runs it with the golden set; it needs no model and runs in CI.

| | Corrections | Both forms right | One side found | Wrong form |
|---|---:|---|---:|---:|
| Development set — the join was built against it | 55 | 55 — 1.000 [0.935, 1.000] | 0 | 0 |
| Held out — never changed the join | 34 | **32 — 0.941 [0.809, 0.984]** | 2 | **0** |
| Golden set, seven real turns | 4 | 2 — 0.500 [0.150, 0.850] | 2 | 0 |

**The held-out set was written after the join and the parser fixes were frozen**, half of
it the way the recogniser writes — lower case, no punctuation, sentences run together. The
two it half-found:

- `Tomorrow I will to call you` — a `will` that is the head of its phrase, rather than an
  auxiliary, is never counted as the future. The breadth counter has the same gap.
- `the flat have two bedrooms` — in lower case the tagger does not read `have` as a verb.

Neither was fixed: fixing either now would make this set a second development set.

**On real speech the parse is the limit.** Two of the four golden labels are in one
unpunctuated standup turn, where the tagger reads `complete` as an adjective and the
corrected `completed` as a participle. The join then finds nothing — or, for the label
whose correction adds `that`, only the needed side.

**What is asserted is the property that matters most:** no correction on any set is linked
to a form it was not in. A missing side leaves that side out of accuracy per form; a wrong
one would count a mistake against a form the learner did not get wrong, and the suite
fails on one.

## 6. What it cannot be more right than

The join is measured against corrections a teacher would make. In the product it is given
the corrections the detector made, and on the hand-checked set the model's are right half
the time (0.500 precision over six) and find a third of the mistakes a person marked.

On the live database that is exactly what happened. After `make reparse`, two of the
seventeen stored corrections joined to a form — `is going to be long term` corrected to
`will be long term`, and `we can test` corrected to `we will test` — and both are the
model's false positives: nothing was wrong with either. The join placed both correctly;
the learner's `going to` future and `can` each read one wrong, and `future_will` reads
needed twice, for mistakes that were never made. The other way round, the snapshot for the
week with the standup in it holds *present simple: right 14 of 14*, and `we request`, one
of those fourteen, is a present simple the golden labels mark as wrong — the model filed it
under prepositions.

So accuracy per form is a count of what the detector said, joined honestly. It is shown,
because a count is a measurement, with a caveat that names both halves: a wrong correction
counts against a form used correctly, and a missed one counts as right.

## 7. What a learner sees

On the progress page, under *How much you reach for*, each tense and modal in the
repertoire carries a line beside its count:

- **right 3 of 5** — below the floor, a count and nothing else;
- **right 9 of 13 · 69 %** — from ten times said or needed in the period
  (`PROGRESS_MIN_FORM_CONTEXTS`), where the 95 % interval around 0.8 is 0.49 to 0.94,
  about as wide as a figure worth reading gets. *Withdrawn by 0016 §3: the floor is on the
  sample, and the corrections under the count are the larger error; the page now shows
  the count alone;*
- **needed 2, never said** — a form the learner did not use and should have. It is listed
  even with a use count of zero, because avoidance is what the breadth panel exists to
  show.

Structural features — clauses, the passive, comparatives — keep their count and get no
accuracy: no one verb phrase is in them. The caveat is rendered on the panel whenever it
carries accuracy, because it is read away from the error-rate chart that carries the other.

The session report's JSON carries the same figures (`form_accuracy`) and each correction's
two forms. The session page shows neither; the grammar page (0016) shows the forms over
the window, with the corrections behind each count.

**Seen end to end** on a throwaway account, with two TTS-synthesised turns through the real
pipeline, heard verbatim. The first had three corrections — `I visit` → `I visited` from
the model, `My sister work` and `she have` from the rules — and every one was joined to the
form a teacher would name. The second added two more of the model's, both wrong (`I never
went` → `I had never gone`; a `going to` future that was fine), joined as faithfully. The
server-rendered progress page showed *right 3 of 5*, *needed 1, never said* and the caveat.
Both sessions and both accounts were deleted after; the corpus is eleven sessions and
eleven learner turns, as before.

## 8. What is not settled

- ~~**Whether a percentage belongs on the page at all while detection precision is
  0.500.**~~ Decided in 0016 §3: not on any page, until precision is measured at the bar.
- **`will` as the head of its phrase**, and every other gap §5 names, in the counter and the
  join alike.
- **A correction that rewrites two verb phrases** counts one.
- **The progress page's recommender does not read accuracy per form.** The grammar page
  names the weakest form, with a floor of its own (0016 §4); the ranking on the progress
  page is unchanged.
