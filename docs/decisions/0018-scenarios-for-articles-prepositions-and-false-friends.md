# 0018 — Scenarios for articles, prepositions and false friends

Status: accepted · 2026-09-12

Every scenario the product shipped with was written around a tense, a modal or a
conditional, and nothing in the catalogue was written to draw out articles, prepositions or
false friends — the last of which the taxonomy gives a subcategory of its own because, for
a Spanish first language, it is the signal most worth surfacing. The plan asked for two or
three scenarios that do, each with a band, and set the test: the new seeds exist and elicit
what they declare. Two things stood between that sentence and a scenario file. A scenario had no way to declare a kind of mistake at
all. And whether a scenario draws a mistake out is shown, as far as this product can see,
only by the corrections it produces — which need the mistake to survive the recogniser and
then to be found and filed under its kind by the detector (0017 §6).

## What was decided

1. **A second declaration, `target_errors`**, in the error taxonomy's category names,
   required on every scenario like `target_grammar`. The eight scenarios there were
   declare `VERB_TENSE`.
2. **Three scenarios**, one per kind, at three bands: *Lost property office* (A2,
   articles), *A courier who cannot find your door* (B1, prepositions) and *Applying for a
   training programme* (B2, false friends, which the taxonomy files under
   `LEXICAL_CHOICE`).
3. **The declaration is read where a learner acts on a kind of mistake**: a category on
   the grammar page links to a scenario that declares it, at the learner's band where one
   does; an error-category recommendation links to one; the catalogue and the scenario page
   show what each is built to draw out.
4. **What "elicits what it declares" can mean without a person is measured** as the two
   links a correction needs, on sixty hand-labelled sentences written for the three
   scenarios: whether the mistake, said aloud, reaches the transcript as it was said; and
   whether the detector then finds it and files it under its kind. And the three new
   personas are held to the same probes as the eight.
5. **A wrong fix by the rule layer was found in the new scenarios' own text**, and fixed.

---

## 1. Why a second declaration

`target_grammar` is in the parser's vocabulary — the tenses, modals and clause types
`services/grammar.py` counts — and that vocabulary is closed so that "declared but never
produced" is a set difference (0006). It has no word for an article, a preposition or a
false friend, and it should not gain one: a form is something a speaker produces and the
parser counts, and these are things a speaker gets wrong and the detector files. Counting
every "the" as a form used would put a number in the breadth chart that means nothing.

So `scenarios.target_errors` (migration `0006`) holds names from the other closed
vocabulary, the nine categories of `services/taxonomy.py`. The seed loader rejects a name
the taxonomy does not have, and a list declared twice or empty — the reason `target_grammar`
must not be empty holds here too: a scenario that declares nothing can never fail the check
that it drew out what it declared.

**Category, not subcategory.** False friends are `LEXICAL_CHOICE/false_friend`, and the
scenario written for them declares `LEXICAL_CHOICE`. Everything that reads the declaration
— the grammar page, the recommendation, the snapshots — groups by category; a declaration
at a finer grain than anything reads would be a promise nothing keeps. The labelled
sentences below are all `false_friend`, so the measurement is at the finer grain.

**The eight declare `VERB_TENSE`.** Each was written around a contrast of tenses, modals or
conditionals, all of which the taxonomy files there. It is the claim their `target_grammar`
already made, in the detector's words.

## 2. The three scenarios

Each is built so the thing it draws out is the thing the speaker cannot avoid saying.

**Lost property office** (A2, articles). A clerk with several bags like yours on the shelf,
who hands one over only when the description fits no other. Describing an object means a
string of single countable things — *a black backpack, a laptop, a sticker* — and telling it
apart from the others means *the one with the*: the choice between *a* and *the* is the whole
task. It is the catalogue's first A2 scenario; describing an object is an A2 task.

**A courier who cannot find your door** (B1, prepositions). A driver on your street who
cannot see the entrance, who says what they can see whenever a direction is vague, and then
needs a day and a time to come back. Directions are place and movement — *at the back, next
to, on the second floor, across* — and the second delivery is time — *on Tuesday, in the
morning, at six, by five*. Spanish says *en* where English says *in*, *on* or *at*, and *a*
where English says *to* or *at*, so these are where the wrong one comes out.

**Applying for a training programme** (B2, false friends). A coordinator asking what you
do now, what you studied, what courses and events you have been to, and one thing you want
to do better. Those are the questions whose natural answers use the words with Spanish
look-alikes that mean something else: *currently / actualmente*, *attended / asistí*, *degree
/ carrera*, *course / formación*, *summary / resumen*. **The persona is told to ask in everyday
words and let the speaker name things** — "what do you do these days", not "what is your
current role" — because a speaker handed *current* repeats it, and the scenario would
measure the persona's vocabulary instead of the speaker's.

**The rubrics do not give the answers away.** The eight rubrics name the forms they look
at, and so does the article one, as a rule. The preposition and false-friend rubrics say
what is looked at without listing the words: a learner told beforehand that it is *attend*
and not *assist* will say *attend*, and the scenario would have taught the answer before it
was asked.

Each persona follows the conventions `services/conversation.py` reads — "You are {name},"
first, its sentence count in the brief's own words — and each carries the sentence every
persona carries, never to comment on the speaker's English. That sentence matters more here
than anywhere: these three personas are handed mistakes they are there to draw out, and a
persona that answers *a black backpack, you mean?* has corrected the speaker.

## 3. Where the declaration is read

- **The grammar page.** Each kind of correction links to a scenario that declares it — at
  the learner's own band where one does, as the named verb form already did — as *Practise
  these in A courier who cannot find your door*. It is a way to practise, not a claim
  about weakness, so it has no floor. A kind no scenario declares links nowhere.
- **The recommendation.** An error category is ranked as it was, and now carries a scenario
  that declares it, so *What to practise next* offers *Practise this* on it — until now only
  forms and sounds had somewhere to go.
- **The catalogue and the scenario page** show the kinds of mistake, dashed, beside the
  forms.

**Not in the session report.** The report says which declared forms were never produced,
and that is honest because a form not produced is a form not used. A kind of mistake that
produced no correction is not a kind not drawn out: the speaker may have said every article
right. So the report does not say "not elicited" for a kind of mistake, and the measurement
below is the only place the declaration is checked.

## 4. What "elicits what it declares" can be shown to mean, and what it cannot

A scenario draws out a kind of mistake, as far as the product can tell, when its sessions
produce corrections of that kind. Between the speaker's mistake and a correction on the
grammar page stand two machines: the recogniser has to write the mistake down as it was
said, and the detector has to find it and file it under its kind. Whether a learner in the
lost property office actually drops more articles than elsewhere needs a learner; those two
links do not, and they are the ceiling on what any scenario can show.

**Sixty hand-labelled sentences** (`tests/category_labels.py`), twenty per kind, each
something a learner could say in the scenario that declares its kind, with one mistake in
it and nothing else wrong: *I lost black backpack*, *my flat is in the second floor*, *I
assisted to a conference*. Written before any was spoken or detected, like the verb-form
sentences of 0017 §6, and subject to the same limit on who wrote them.

### 4.1 Said aloud

In the speech recognition suite, beside the drill's measurement and by the same comparison:
each sentence spoken by the `tts` voice with its mistake and corrected, heard by
`small.en`, and read where the correction belongs. Three runs, because synthesis is not
deterministic:

| Kind | Mistake heard as said | Heard as the correction | Something else | Corrected heard as corrected |
|---|---|---|---|---|
| Articles | 18, 19, 18 of 20 | 0, 0, 0 | 2, 1, 2 | 20, 20, 20 |
| Prepositions | 18, 18, 17 | 1, 1, 2 | 1, 1, 1 | 19, 19, 19 |
| False friends | 18, 18, 18 | 0, 0, 0 | 2, 2, 2 | 20, 20, 20 |

**Prepositions are the kind the recogniser repairs**: *depends of* came back as *depends on*
in two runs, *next of* as *next to* and *in home* as *at home* in the third — 4 of 60
tries, 0.067 [0.026, 0.159] — and *next of* was repaired again in the live session of §6.
**No article mistake and no false friend came back as its correction** in 60 tries each. A
false friend is a whole word with its own sound, as expected; that a dropped or wrong *a*
survived every time was not certain, and in this voice it did.

"Something else" is mostly the comparison's normalisation rather than the recogniser:
*five* written *5* (the one correct preposition sentence not heard as corrected, every run),
*realised* written *realized*, and once *there is* written *there's* (0017 §3 and §8 — numbers,
spellings and contractions are not unified). The rest are mishearings: *a Apple one* came
back as *Apple One* every run — the article gone, which is neither what was said nor the
correction — *in attention to the client* as *and attention*, and once *took train* as *took
Tring*.

### 4.2 Found

In the error detection suite: each sentence handed to both detectors as written, then the
corrected sentence. Found means a proposal on the mistake's words filed under its kind;
the labelled correction is counted apart, because a proposal on the right words can put
the wrong words in. Three runs, identical to the line — the labelling call runs at
temperature zero:

| Kind | Found and filed under it | With the labelled correction | Under another kind | Missed | Proposed on the corrected sentence |
|---|---|---|---:|---:|---:|
| Articles | 6 of 20, 0.300 [0.145, 0.519] — rules 2, model 4 | 4 | 8 | 6 | 9 of 20 |
| Prepositions | 12 of 20, 0.600 [0.387, 0.781] — model 12 | 9 | 7 | 1 | 7 of 20 |
| False friends | 6 of 20, 0.300 [0.145, 0.519] — model 6 | 2 | 9 | 5 | 6 of 20 |

**The weak link is filing, and it is the model's.** The words were found far more often than
they were filed: an article mistake went under countability four times and word order
twice, a missing preposition after *wait* or *listen* under pronouns three times, and a false
friend under prepositions or verb tense six times — *assisted to* became *assisted at*, a
preposition fix that leaves the false friend in. That is the finding the golden set has
shown since the detector was built (0006), now per kind. The rule layer found the two
article mistakes in the shape it covers — a noun after *be* with a pronoun subject — and was
silent on the other eighteen, as designed.

**And the model proposes on English that is right**: 22 of the 60 corrected sentences drew a
proposal, 0.367 [0.256, 0.493]. Some put the learner's mistake back — *arrive at the corner*
made *arrive to the corner*, *come in the afternoon* made *come to the afternoon* — and some
break what was right — *a big project* made *a big projects*. The grammar page's caveat says
the model's corrections point at a real mistake half the time on the hand-checked set;
these sentences show the same thing from the other side.

### 4.3 What the two links say about the scenarios

For prepositions, in a clear voice, most of what is said wrong reaches the transcript and
more than half of it is filed as a preposition. For articles and false friends, almost all
of it reaches the transcript and less than a third is filed under its kind — and of twenty,
four articles and two false friends carried the labelled correction. **So the courier can
be expected to show much of what it draws out; the lost property office and the training
intake, as the product counts, mostly cannot** — not because of the scenario, but because
of the detector the corrections come from. Their declared kind on the grammar page will be
sparse, and some of what appears there wrong.

That is what can be measured without a person, and it is not the question the plan asked.
Whether a learner makes more article mistakes describing a bag than giving a stand-up
update needs a learner holding both conversations.

### 4.4 The personas

Three probes, one per new persona, written by reading those personas before any had
replied (`eval/golden/personas`), each handing its persona a mistake of the kind it is
there for, inside an answer too vague to accept. One run of the whole suite, now nine
probes:

- the clerk asked what makes the bag different from the others and let *black backpack*
  pass — in three sentences against its cap of two;
- the driver said what it could see — a gate, a car park — and then moved on to the floor
  instead of asking again where the entrance was;
- the coordinator asked for one example, as told — and in doing so said *attended*, the word
  the speaker had just got wrong. It did not comment on the speaker's English, and no
  guardrail counts it, but it handed the answer over.

Across the nine, 6 of 9 replies were clean of the deterministic rules — 4 of the first six,
where the three runs before this one had 4 or 5, and 2 of the new three — and the judge
placed all nine in character. The fifteen spoken instructions gave the instructions away 6 times in
150; nothing in this change touched the prompt they measure.

## 5. Found on the way: an imperative given a subject

The planted-error measurement (0014) takes every piece of native English the repository
carries — the persona briefs among it — knocks one verb out of agreement at a time, and
asserts that when the rule layer catches the error it puts back exactly what was there. The
courier's brief says *say your shift ends soon*. With *ends* planted as *end*, the parser read
*end* as a noun and made *your shift end* the subject of the imperative *say*, which comes
before it; the agreement rule proposed *says your shift end*. A correction of a word nobody
got wrong, with full confidence — the one failure the rule layer is built never to make, and
the suite failed on it.

A learner makes this shape — *tell her the bus leave at six* — so the fix is to the rule, not
to the brief. **Only an auxiliary or `be` comes before its subject** — *does she*, *is it* — so a
lexical verb with its subject after it is now left alone. Counted, not assumed, before and
after:

| Planted errors | Agreement caught | Wrong fix | Articles caught |
|---|---|---:|---|
| The 2 454 words there were, before the guard | 100 of 126 | 0 | 2 of 93 |
| The same, after | 100 of 126 | 0 | 2 of 93 |
| With the three new scenarios, 3 111 words, before | 130 of 172 | 1 | 2 of 129 |
| The same, after | 130 of 172 | 0 | 2 of 129 |

The guard cost nothing on the text there was, and the one wrong fix became a miss. A test
holds the sentence and fails without the guard. It costs recall on a shape nobody has
planted: *here come the bus*, a real agreement error after a lexical verb that inverts, is
now left to the model.

The sentence that found it is now also the sentence the guard was written against, so the
new text is development data for the rule layer, not held out.

## 6. Seen end to end

On a throwaway account with a band of B1: one spoken session in each new scenario, two
turns each, synthesised by the `tts` service with mistakes of the scenario's kind — ten in
all — the sessions ended, and the reports, the grammar page and the catalogue read through
the API and in Chromium at 1440 and 375 px, light and dark.

**Each persona opened in character and pursued its goal**: the clerk said it had quite a
few black backpacks and asked the size and the train; the driver said the number on its
screen matched no door; the coordinator asked what the speaker does these days.

**And each recast the speaker's mistakes.** *Right, a black backpack*; *so you attended a
conference … and you also did a course in project management*. The coordinator's first line
asked what the speaker is *currently* involved in — the word the scenario is built to leave
to the speaker, in the persona's mouth before the speaker had said anything. The brief asks
it to let the speaker name things; the model did not.

**The chain held as measured, and worse.** The recogniser heard *next of the bins* as *next to
the bins*, and *Hi* as *High*, which the driver answered — *okay, high up then!* Of the ten
mistakes spoken, the detector filed one under the scenario's kind, and its correction was
wrong: *Actually, I work in a bank* became *Actually, I am working in a bank* under lexical
choice, which leaves the false friend where it was. The one other correction in a declared
kind was on English that was right — *come at 10* made *come to 10*. The others were found
and filed elsewhere — *in Tuesday* → *on Tuesday* under word order, *black backpack* → *a
black backpack* under countability — or not found.

The grammar page linked *Practise these in A courier who cannot find your door* under
prepositions and the intake under lexical choice, and nothing under word order or
countability, which no scenario declares. Eleven cards in the catalogue, the kinds dashed
among the forms; no horizontal scroll, no console error, and no persona text on any
scenario page.

The account, its sessions and its fifteen recordings were deleted afterwards; the corpus is
six accounts, eleven sessions and eleven learner turns, as before.

## 7. What is not settled

- **Whether the scenarios draw these mistakes out of a learner.** It needs a person holding
  the new conversations and the old ones; the corrections those sessions produce, per kind
  per hundred words, is the measurement, and §4 says how far to trust it.
- **The detector files articles and false friends elsewhere** (§4.2). The rule layer's
  article rule is narrow on purpose (0014); a rule for false friends — a list of words and
  the meanings they are mistaken for — would be a new rule with its own held-out set.
- **The personas recast.** Nothing counts it: the guardrail looks for comments on the
  speaker's English, and a recast is not one. A probe that does would need a way to tell a
  recast from a persona using a word it was always going to use.
- **The session report does not check the declaration** (§3), and cannot until a kind of
  mistake has something like a form's count of times it could have been made.
- **A lexical verb that inverts** — *here come the bus* — is no longer proposed by the rules
  (§5).

