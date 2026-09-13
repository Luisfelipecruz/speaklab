# 0014 — The rule layer

Status: accepted

Decision 0006 measured the error detector and found a specific failure: `gemma3:4b` lands
on roughly the right words and files them under the wrong category — three of six scored
proposals had the right span and the wrong label, and none had the right label. It named
the way out as a rule layer for the categories a parse can decide on its own, and
`language_errors.detector` has allowed `'rule'` since the first migration. Grammar
practice is built on the corrections, and a drill built on a detector that is right
half the time teaches the wrong thing half the time — so the rule layer comes first, and
is measured before anything is built on it.

This records what was built, what it was measured against, what it cannot be measured
against yet, and one defect that verifying it end to end found somewhere else.

## What was decided

1. **Two categories, proposed from the parse with a confidence of 1.0 and no model.**
   Subject–verb agreement (`third_person_s`, `there_is_are`) and a missing article
   (`missing_indefinite`, `missing_definite`). `services/rules.py`.
2. **Narrow on purpose.** A rule fires only where the parse leaves no doubt, and is silent
   wherever the same words have a grammatical reading.
3. **The model's copy of a rule's correction is superseded, not stored twice** — and not
   counted against the model's rejection rate.
4. **Each detector is scored on its own**, and the model on everything it proposed, so its
   figure is its own.
5. **A second measurement that needs no model**: errors planted in native English.
6. **A rule's correction is marked like a model's on the transcript; its row names the
   source.**
7. **The report says the category mix is partly a property of the detector**, on the
   session report and on the progress page.

---

## 1. What the rules are

Both families read one spaCy parse, the one `services/grammar.py` already makes for the
forms a learner used — the analysis job now parses each turn once and hands the same parse
to both.

**Agreement.** For every verb with exactly one subject, the word that carries the tense —
the first auxiliary, or the verb itself — is compared with the subject's person and
number: `she work`, `the people is`, `they works`, `I has`, `do the train leave`, `we was`.
"There" agrees with the noun after the verb, or its first conjunct: `there is many
people`, `there are a problem`.

**A missing article.** A singular countable noun with no determiner, in two shapes only:
after `be` with a personal subject — `I am engineer`, `it is very good apartment` — and
after `as` with a verb of working — `I work as teacher`. Both are where a Spanish first
language drops the article most predictably. A superlative or a unique adjective takes
"the": `it is best option` becomes `the best option`.

The correction is built from the parse, not written by anybody: the verb re-inflected, or
the article inserted before the noun phrase's first word, `a` or `an` by the sound the word
starts with. The quote runs from the subject to the verb, or from the subject to the noun,
so it reads as a phrase rather than an underlined word.

## 2. Silence, and what each silence is for

A proposal from here reaches a learner's history with no gate in front of it, so every
false positive is a false statement made with full confidence. The rules therefore say
nothing when the same words have a grammatical reading, and each of these is a sentence in
`tests/test_rules.py`:

| Stays silent on | Because |
|---|---|
| `the team are playing` | Collective nouns take a plural verb in British English |
| `a lot of people are here`, `one of my friends lives` | A partitive agrees with what it measures |
| `two years is a long time` | A number and a unit are one amount — but `three people passes` is still an error |
| `my brother and my sister live`, `fish and chips is` | Coordinated subjects, and the singular idioms among them |
| `let him go`, `I suggest that he go` | A causative complement and the subjunctive are bare on purpose |
| `yesterday she go`, `I finished and she send it` | A bare verb in a past context is a missing past marker, not a missing -s — and a rule that cannot tell which error it is looking at says nothing |
| `there's two bedrooms` | Ordinary spoken English from native speakers |
| `it is good news`, `it is hard work`, `it is good training` | Uncountable nouns, and gerunds |
| `I am part of the team`, `she is president` | A share, and an office held by one person |

The past-context rule is the one that needs care in both directions. Its first version
silenced a verb whenever any past verb appeared anywhere in the sentence; the planted
measurement (§5) showed it also silenced `the user have described what went wrong`, where
the error is on an auxiliary and cannot be a tense error, and `I still thinks we were
interrupted`, where the past verb is inside a reported clause. It now applies only to the
main verb, and only to past verbs in a clause joined to this one. Two other silences were
narrowed by the same measurement: the subjunctive now needs a `that`-clause, so `when the
user disagree` is proposed, and a number silences a plural only in front of a unit, so
`three thousand people passes` is too. Together the three took agreement recall on planted
errors from 75 of 126 to 100 of 126. They also uncovered one false positive in the native
text the old past rule had been hiding — `the letter L. Collect the flowers` — which §3's
capital-letter rule now keeps silent.

**What cannot be done with a parse, and so is not done.** Whether a bare noun after a
preposition or as an object is missing its article depends on whether it can be counted —
`I need visa` against `I need privacy`, `with possible renewal` against `in good
condition` — and a parse does not know. Deciding it with a word list is the very thing the
layer exists not to do, so those shapes are left to the model. The price is measured in
§5, and it is most of the article family.

## 3. Found on text the rules had never seen

The fixtures in `tests/test_rules.py` were written before the rules, and none of them is
from the golden set. That keeps the rules honest against their own tests and says nothing
about text nobody thought of. So the layer was run over English it had never seen: the
persona's own stored replies, and the long descriptions of the Python packages installed
in the API image — 204 paragraphs of native technical prose, 5 647 words.

The first pass made ten proposals there, and every false one was a shape the fixtures had
missed. With them, one found in the repository's own reading passages once §2's past rule
was narrowed:

| Shape | Example | Now |
|---|---|---|
| A capitalised plural is a name | `Requests is available`, `PyYAML supports` | Silent |
| A proper noun with "the" is modifying the next noun | `The Linux build files need` | Silent |
| An adjective the tagger read as a noun | `It's super lightweight` | Silent |
| A comma or a conjunction between subject and verb | `…new terminal, the classic terminal is limited` | Silent |
| A capital on a verb after its subject is a new sentence | `the letter L. Collect the flowers` (a reading passage) | Silent |
| A curly apostrophe is a contraction | `I’m` | Silent |

And in the stored learner turns, one: `Can I have pets in my? Unit or do I need a special
license` — the recogniser's question mark and capital split a sentence, and the parse made
"Unit" the subject of "do". Two subjects on one verb, or a conjunction between the subject
and its verb, now mean silence.

One of the ten was right: `we only supports` in a package's own README. It is still
proposed.

**That prose is a development set, not a held-out one.** It was consulted four times
while the rules were being fixed, and a figure measured on it would be a figure measured
on the data the rules were shaped against. The only text the layer has not been shaped
against is speech nobody has recorded yet.

## 4. The model and the rules together

Where the model proposes the same correction on the same words, one mistake would be
counted twice. So a model proposal is **superseded** when it overlaps a rule's proposal
and either names the same category or makes the rule's change under another one — `she
work` corrected to `she works` and filed as a tense error, which is the model's commonest
failure. A model proposal on the same words that makes a *different* correction is kept:
`work in a bank` corrected to `work at a bank` is about a preposition.

A superseded proposal is not stored as a row and is not dropped. It goes onto
`turns.analysis_rejects` with the reason `superseded_by_rule`, beside the taxonomy's
refusals, and it is **kept out of the model's rejection rate**: it passed the gate and lost
to a rule, which is not a failure by the model. The report counts it separately.

The rules do not depend on the model. A turn whose model was down still gets its rule
rows, as it already got its fluency and its forms.

## 5. The measurement

**On the golden set, the rule layer proposes nothing.** `make error-precision`,
seven turns, `gemma3:4b` at temperature 0, load average 9.7:

| | Scored | Detection precision | Labelling precision | Recall |
|---|---:|---|---|---|
| The product — what a learner is shown | 6 | 0.500 [0.188, 0.812] | 0.000 | 0.333 |
| `gemma3:4b` alone | 6 | 0.500 [0.188, 0.812] | 0.000 | 0.333 |
| The rules alone | 0 | — | — | 0.000 |

The model's figures reproduce decision 0006 exactly — sixteen proposals, four refused, the
same six scored — which is what temperature 0 is for. The rules make no proposal because
there is nothing for them to find: the eleven labelled errors include **no agreement error
at all**, and one article error, `with possible renewal`, in exactly the shape §2 leaves
alone. Across every learner turn in the database — eleven turns, 428 words — the layer
proposes nothing, and nothing is wrong with that.

So of what the layer was built to show — its precision reported separately, and above the
model's — half is shown. It is reported separately. Whether it is above cannot be decided on
this corpus, and S5 stays undecidable for the reason it was before.

**Planted errors, which need no model.** The golden set can say nothing about the rules, so
the rules are given the errors they claim to catch: every piece of native English in the
repository — the reading passages, the persona briefs, the LibriSpeech references, the
persona calibration replies, 56 texts and 2 454 words — with one verb put out of agreement
or one indefinite article removed at a time. The error forms are spelled out by the test
rather than borrowed from the rules, so the layer is not grading its own inflection.

| | Planted | Caught | Wrong fix | Missed | Proposed elsewhere |
|---|---:|---|---:|---:|---:|
| Agreement | 126 | **100 — 0.794 [0.715, 0.855]** | 0 | 26 | 0 |
| Missing article | 93 | 2 — 0.022 [0.006, 0.075] | 0 | 91 | 0 |

**When the layer speaks it is right** — no wrong fix and no stray proposal in 219 planted
errors, and no proposal on any of the 2 454 unplanted words, which `test_rules.py` asserts.
A caught error whose fix does not restore the original words would fail the suite.

**Agreement recall is an upper bound.** A planted error sits in otherwise clean English;
in a learner's speech the parse is worse. The 26 misses are mostly the silences of §2
doing their job — a collective, a relative pronoun, a verb the tagger read as a noun.

**Article recall is the price of §2, stated.** Most indefinite articles in native text sit
after a preposition or on an object — `found a seat`, `in a house` — and that is the shape
left to the model. The article rule covers the predicate noun and the role after `as`,
which is 2 of 93 in this text. In a learner's speech that shape may be commoner — `I am
engineer` is the article error a Spanish first language makes most predictably — and
nothing here can say by how much until one is recorded.

## 6. What a learner sees

Rule rows are stored with `detector='rule'` and reach the report like any other. The
session report now says that agreement and missing articles are found by grammar rules and
the rest is proposed by a model, and — on reports written after the rules existed — that
the two covered categories are therefore found more reliably than the rest. The progress
page's accuracy caveat says the same.

**A rule's correction is marked on the transcript exactly as a model's is, and its row
carries a "grammar rule" badge.** The mark answers *where*; a second colour of solid
underline would read as a second severity, which it is not. The row answers *what and why*,
so that is where the source goes.

**Stored reports are not rewritten.** A report is written once, when a session ends, so
a report written before the rule layer existed has no `detector` on its rows. The frontend treats a missing
detector as the model's — which is what it was — and shows neither the badge nor the note.

**Seen end to end** on a throwaway account: a sentence synthesised by the `tts` service —
*"My sister work in a bank near the station. It is very good job for her."* — posted as a
turn, heard verbatim by `small.en`, and analysed. Two rule rows, `My sister work` → `My
sister works` and `it is very good job` → `it is a very good job`, both counted; the model
proposed both too, under the right categories this time, and both were superseded; the
model's rejection rate read 0.0. The server-rendered session page carried the badge on both
rows. The session and the account were deleted afterwards, and the corpus is eleven
sessions and eleven learner turns, as it was.

## 7. A defect found on the way, not fixed here

The first end-to-end run produced a report with **no corrections in it**. Two things were
wrong, and neither was the rule layer:

1. **Ending a session did not wait for a turn the live job had already claimed.**
   `ensure_session_analysed` analysed the turns that were `pending` or `failed`; the last
   turn was usually `analyzing`, because the live job took it the moment the reply went
   back. Speak, then press End straight away — the ordinary way to finish — and the report
   was written without that turn, though it did say a turn was outstanding.
2. **The promise the report then made was not kept.** It said *"Open this session again to
   finish them."* Opening the session is `GET /sessions/{id}`, which returns the stored
   report. What rebuilds an incomplete report is a second `POST /sessions/{id}/end`, and no
   page called it once the session had ended.

So the last thing a learner said was missing from the report, and from the corrections
marked on the transcript, which are read from the report. Calling `POST /end` again
rebuilt it correctly in the run above. It touched `services/analysis.py` and the session
page, not the rule layer, so it is fixed as a change of its own.

**How it is fixed.** Ending waits for a claimed turn — a job in the API's process is
awaited, a claim held by a backfill in another process is polled — within the same budget,
and a job cut off by the deadline is left running rather than cancelled. The session page
finishes a short report when it is opened, once, and then offers a button. A job cancelled
by the server stopping puts its turn back in the queue. Measured on the stack, ended
straight after one synthesised turn: the code before, **3 of 3** reports without the turn
and no corrections; after, **3 of 3** complete with both, the end taking 4.15–4.80 s. A
report left short by the old code was opened in a browser and finished by the page with one
request.

## 8. What is not settled

- **Precision on learner speech.** The rules have never proposed an error in a real
  learner's turn, because the corpus has none of the two kinds they cover. The first real
  proposal is the first real measurement.
- **Other first languages.** The article shapes are chosen for a Spanish first language;
  the agreement rules are not language-specific, and the silences are English.
- **The word lists are closed and will be wrong at the edges.** Each list is a set of words
  on which a rule would be wrong, so a missing word costs a false positive; the countable
  -ing list runs the other way, so a missing word there costs a missed one. The native-text
  test and the planted measurement are what catches a list that has gone wrong.
- **The recogniser leans towards grammatical English.** A speech model's language prior
  can turn `she work` into `she works` before this code sees it — a recall cost the
  planted measurement cannot see, because it starts from text. The turn above was heard
  verbatim, which is one turn.
