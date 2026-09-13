# 0017 — The spoken drill

Status: accepted

Grammar practice has one exercise: given one of the learner's own corrected sentences,
record it, transcribe it, and compare it with the correction using the word error rate
code — deterministic, no model call, measurable. Two questions decide its shape: where the
drill lives, and what its pass mark is, if it has one. And 0016 §3 sets a condition on it:
a drill on a correction that was wrong teaches the wrong thing, so the learner must be able
to see the correction and skip it.

## What was decided

1. **A page of its own, reached from the grammar page.** *Say it again* beside every
   correction placed in its sentence opens `/grammar/drill/{id}`. Two operations,
   `GET /corrections/{id}/drill` — the sentence to say — and `POST` — a recording of it,
   compared.
2. **The sentence is the one said, corrected — all of it.** Cut as the grammar page cuts
   it, with every correction stored inside it applied, not only the one being practised.
3. **Compared per correction, not per sentence.** Each correction gets what was heard where
   its words belong; the sentence gets its word counts.
4. **No pass mark, no percentage, and nothing stored.**
5. **The correction comes first, and skipping it is one step.** The page opens on the
   correction as said, what was proposed and by what, and a link to the next one of the
   same kind, before the button.
6. **The recogniser's blind spot is measured, in the speech recognition suite**, and the
   page says what it found.

---

## 1. Where it lives

The grammar page lists the sentences, so the drill starts there: each placed correction
carries *Say it again*. It opens a page rather than a recorder in place, for three reasons.
A drill is one sentence with the microphone open, and a page with twenty corrections and a
microphone for each is twenty chances to record against the wrong one. The drill needs room
to show the correction before the button, which is the point of §5. And a page of its own
has an address, so *Skip* can be a link to the next correction rather than state held in a
list.

*Skip* goes to the next correction **of the same kind**, newest first, over every analysed
turn rather than the grammar page's thirty days — a learner who opened a verb-tense
correction is practising verb tenses. Corrections already in the sentence just said are
skipped, since they were in it. After the last, the page says so.

The session page does not link to drills. It is where a conversation is read back; one way
in keeps the order of *Skip* meaningful.

## 2. The sentence

The sentence is the one the correction was made in, cut at its own full stops or 90
characters either side — the same function the grammar page cuts with,
`corrections.sentence_bounds`, so the two pages quote the same words.

**Every correction inside it is applied.** Applying only the one being practised would ask
the learner to say, aloud, a mistake that was flagged a few words away — and, because the
recogniser often writes a turn as one unpunctuated sentence, the sentence is regularly long
enough to hold several. In the end-to-end check below it held three. Corrections that
overlap are not both applied: the one being practised wins, then the first by position.

The cost is real and the page carries it: a wrong correction elsewhere in the sentence is in
the sentence to say. So the card above the button lists every correction the sentence
carries, each with its original, its replacement and its badges, and the line under the
card says to practise a correction only if you agree with it.

Two corrections cannot be practised aloud, and the page says why instead of offering the
button: one whose stored offsets do not hold its words — the same check the transcript and
the grammar page make — and one that changes only capitals or punctuation, which a
recording of somebody speaking cannot show. The `POST` refuses both with a 409.

## 3. What is compared, and why not the sentence's word error rate

The sentence's word error rate is the wrong number. A thirteen-word sentence said again with its one mistake
intact has a word error rate of one in thirteen — which reads as nearly right, while the
drill's one question went unanswered.

So what is compared is the alignment behind the rate. `services/wer.py` exposes it —
`align`, which heard word stood for which reference word — and `wer()` counts from it, with
its tests holding its figures. The drill aligns the recogniser's words
against the sentence's, normalised exactly as the word error rate normalises them, and for
each correction reads what stood where its words belong:

- **heard as corrected** — the correction's words, in place;
- **heard the way you first said it** — the words the correction replaced;
- **something else** — anything else;
- **nothing** — no word was heard there.

"In place" has two readings, and both are needed. From the correction's first word to its
last catches *she say* for *she said*; but a correction that removes a word — *I agree* for
*I am agree* — has to be read between the words either side, where the removed word is
heard if it is said anyway. A correction is heard as first said on either reading, and as
corrected on the first only when nothing extra was heard around it that would make it the
original.

A word heard there below the recogniser's confidence floor — the per-word floor every
correction is gated on — marks the outcome as possibly a mishearing. The sentence as a
whole is counted: words heard as written, heard as something else, not heard, and heard
that are not in it.

The normalisation is inherited, decisions included: capitals and punctuation are not
heard, numbers are not turned into words, and a contraction is not expanded — so the
recogniser writing *he's* where *he is* was said reads as something else. That last one is
a cost for the drill, recorded in §8.

## 4. No pass mark

Two machines stand between the learner and a verdict. The corrections: on the hand-checked
set the model's are right half the time, and a pass mark on a wrong correction rewards
saying a mistake. The recogniser: trained on fluent English, it can hear the correct form
where the wrong one was said — rarely for a clear voice (§6), and for a learner's, nobody
knows yet. A pass would be those two opinions presented as the learner's grammar.

So the page shows what was heard, per correction and word by word, and the outcomes are
drawn in the same neutral colour: a red cross beside a correction that was never right
would be the product grading the learner on its own mistake. There is no percentage,
consistently with 0016 §3.

## 5. Nothing stored

The recording is transcribed, compared and dropped, and so is the comparison — whatever the
account's audio retention setting. There is no table, no migration, and no page that counts
drills. A repetition is not a conversation: nothing is rescored later, and the grammar page
already holds the sentences. The recording is sent the way a turn is — the connection goes
back to the pool before the recogniser runs — and the audio never touches the volume.

It is the cheapest decision here to reverse, and it should be reversed only for a reason
that §6 can survive: a drill result on a trend would be a number that moves when the
recogniser's prior does.

## 6. The recogniser's blind spot, measured

The drill can be fooled in one direction the learner cannot see: a mistake said aloud and
heard as its correction. The grammar page's check found one — *I fix two bugs* heard as *I
fixed two bugs* — and 0014 §8 had predicted the effect. How often it happens decides what
*heard as corrected* can be taken to mean, so it was measured before the page said
anything about it.

**Method.** The 89 hand-labelled learner sentences of `tests/form_labels.py` — the forms
join's development and held-out sets: 57 verb tense, 16 agreement, 9 omission and 7 of four
other kinds, half of the held-out set written the way the recogniser writes — each spoken twice
by the `tts` voice (`en_US-lessac-medium`): as the learner said it, and with the correction
applied. Each recording heard by `small.en`, compared by the drill exactly as a learner's
would be. No model is asked anything. It runs in the speech recognition suite —
`make asr-wer`, and `make eval` — and records its counts for the evaluation report.

**Results.** Synthesis is not deterministic, so the same sentences were measured four
times, the third through the evaluation harness (`eval/run.py --only asr`) and the fourth
by a full `make eval`:

| Run | Mistake heard as the correction | Mistake heard as said | Something else | Correct heard as corrected | Correct heard as the mistake |
|---|---:|---:|---:|---:|---:|
| 1 | 2 | 81 | 6 | 88 | 0 |
| 2 | 3 | 78 | 8 | 87 | 0 |
| 3, the harness | 2 | 81 | 6 | 88 | 0 |
| 4, `make eval` | 1 | 77 | 11 | 89 | 0 |

**What it means for the page.** *Heard the way you first said it* is strong evidence: no
correct sentence was heard as the mistake, in 356 tries — 0.000 [0.000, 0.041] over each
run's 89. *Heard as corrected* is weaker: a few mistakes in a hundred were heard that way —
0.022 [0.006, 0.078] on the first harness run, 0.011 [0.002, 0.061] on the fourth, 8 of 356
over all four. The page says both, with the figures, and says the voice was synthetic.

**The mistakes that did not come back as said**, from the second run, read one by one:

- heard as the correction — *He can speaks* → *He can speak*; *You must to wear* → *You
  must wear*; *yes i finish the migration last week* → *Yes I finished the migration*;
- made grammatical another way — *I been to Paris* → *I've been to Paris*; *my manager say*
  → *My managers say*; *She don't like* → *you don't like*; *She is agree* → *She does
  agree*;
- not a repair — *he is* written *he's*, *rain* heard as *rained*, *should* as *showed*,
  and *30* spoken and written back as *thirty*.

And of the correct sentences, two were heard otherwise: *We arrived in Madrid* as *We
arrive*, and *the flat* as *The flight*. The third run found the same shapes — *She going*
came back as *Is she going…?* and *We waiting* as *We're waiting*.

**It is a finding beyond the drill.** In the second run 7 of 89 mistakes came back from the
recogniser as grammatical English — 3 as the correction, 4 another way — and in the third
6, 2 and 4. Those never reach
the detector at all. It is one reason detection finds a third of what a person marks; it
belongs to the recogniser, and no change to
the detector can recover it.

**What it is not.** One clear, native, synthetic voice gives the recogniser the most to go
on there is. A learner's voice gives it less, and that is when a recogniser leans on what it
expects. The rate for a learner is not measured and cannot be without a person's
recordings — the same recordings criterion S4 has been waiting for.

## 7. Seen end to end

On a throwaway account with a self-assessed band of B1: one turn synthesised by the `tts`
service and posted in the stand-up scenario, the session ended, and the grammar page read
through the API. The recogniser heard *I finish the report* as *I finished the report* — the
blind spot again, before anything was drilled — and the analysis found four corrections,
two of them the rules'.

**Through the API**, the rule's *I am engineer* → *I am an engineer*: said corrected, heard
as corrected, 4 of 4 words; said as first said, heard the way it was first said, 3 of 4 and
one not heard. The long sentence carried three corrections, and each drill on it applied
all three.

**In a browser.** Chromium with a synthesised WAV standing in for the microphone, driving
the browser's own recorder. From the grammar page's *Say it again* to a result, four times, at 1440 and
375 px in light and dark: the short sentence heard as corrected, and as first said; the long
one said corrected, where the recogniser heard *why sister works* for *my sister works*,
marked it as unsure, and the page said *something else — may be a mishearing*; and the long
one said with two of its three mistakes, each named. No horizontal scroll, no console error, no
percent sign.

The account and its session were deleted afterwards; the corpus is six accounts, eleven
sessions and eleven learner turns, as before.

## 8. What is not settled

- **The rate for a learner's voice** (§6). It needs recordings of a person.
- **Contractions.** *he's* for *he is* reads as something else. Expanding contractions would
  change the word error rate's normalisation, which is a published figure's; the drill could
  expand them on its own, and does not, because *he's* is also *he has*.
- **A wrong correction elsewhere in the sentence is in the sentence to say** (§2). The page
  lists it; it does not let the learner leave it out.
- **Nothing is stored** (§5). Revisit if a drill should reach the progress page, and then with
  the recogniser's rate for learner speech in hand.
- **The read-aloud page's button says *Sending your turn*.** The drill names what it sends;
  the reading does not.
