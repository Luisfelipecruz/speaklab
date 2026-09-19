# 0028 — Rehearsing a script somebody wrote

Status: accepted

A learner pastes the script of a talk, it is split into sections of about a paragraph, and
each section is said as often as they like: every take is compared with the script word by
word, timed and counted like a spoken answer, and scored sound by sound like a reading.
This records why the split is arithmetic and shown before it is saved, why the words no
converter can turn into phones are named rather than skipped, why a take is not refused on
an account that keeps no recordings, and why none of it reaches the progress page.

## What was decided

1. **A section is at most 120 words, a script at most 3 000.** The twelve seeded passages
   are 73 to 79 words and a 34-second reading is scored in about 7.5 s, against a
   ten-second budget. 120 words is roughly fifty seconds of speech and stays in the same
   order of work; it is also about as much as anybody rehearses as one piece. A script
   over 3 000 words — twenty-five sections — is refused with its own word count in the
   message, because a split that long is no longer something a person looks over before
   saving. The three numbers are `REHEARSAL_SECTION_MAX_WORDS`,
   `REHEARSAL_SECTION_MIN_WORDS` and `REHEARSAL_SCRIPT_MAX_WORDS`.
2. **The split is arithmetic, and it is shown before anything is saved.** Blank lines
   first, because a writer who left one meant it; a paragraph over the cap is cut at
   sentence ends, greedily, which for pieces that must stay in order is also the fewest
   that fit; a piece under the minimum is joined to the one before it unless that would
   break the cap. A sentence longer than a section on its own is left whole — the only
   place to cut it is inside a sentence, and a section that stops mid-clause is worse to
   rehearse than a long one. A model asked to divide a talk would answer differently on
   Tuesday, could not say why, and would be the one piece of this feature able to reword
   somebody's script. The learner can join sections before saving, and what is saved is
   checked against the script word for word: a boundary moves, a sentence cannot be
   quietly rewritten.
3. **Which words can be scored is decided when the script is saved, per word.** Scoring
   needs one group of phones per word. A number, a symbol or an abbreviation breaks that —
   `2026` is no word to the tokeniser and two to the converter, `12%` is none and one —
   and inside a passage it does not fail on its own: it shifts every phone after it onto
   the wrong word, and the whole text is then refused, naming none of the words
   responsible. So the pronunciation service gained `POST /phonemize`, which converts each
   word on its own and reports the ones where the two counts disagree, and the section
   carries them. That section still gets its comparison, its timings and its counts; only
   its sounds are missing, and the words are named on screen with what to do about them.
   A word silently dropped would be a sound never scored, with nothing on screen to say so.
4. **A pronunciation service that is not running is not an answer.** With it down the
   question cannot be asked, so every section is saved scorable and the page says the check
   did not happen. The alternatives are both worse: a section wrongly marked unscorable is
   never scored again, and one wrongly marked scorable fails at every take with no reason a
   reader can act on.
5. **Audio retention is honoured, not required.** Read-aloud refuses without it, because a
   reading can be scored again later and that needs the waveform. A take is scored once, as
   it arrives, from the bytes in the request — so `rehearsals.audio_asset_id` is nullable,
   the scoring job is handed the recording rather than reading it back from disk, and an
   account that keeps nothing loses only the replay. The page says so above the record
   button rather than after the take. There is no rescore: a take recorded while the
   scorer was down has no sounds and no way to get them but recording again.
6. **Nothing a take produces reaches the progress snapshots.** The same decision spoken
   answers got, for a stronger reason: a script the learner wrote and said forty times is
   practice of one text, not a sample of how they speak unprepared, and the phone trends
   are built from passages every speaker reads. Mixing in text somebody chose would let
   them move their own baseline by choosing what to write, which is why the take's phones
   are a table of their own rather than rows beside a reading's. Take-over-take movement is
   shown on the script's own page, computed live.
7. **What to rehearse next is four counts, each printing its measurement.** The section
   whose latest take is furthest from its script and by how many words; the phone with the
   lowest mean score among those scored in two or more takes; a section whose latest take
   is over the target the learner set; and the filler said most often across the script's
   takes. Nothing from a model, no readiness score, and no pass mark — an item that cannot
   show what it counted is advice, which is the one thing this product does not give.
   "Confident" stays the learner's word.
8. **A script is the account's own writing, so deletion and export treat it as such.**
   `DELETE /presentations/{id}` removes the sections and takes by cascade, then deletes any
   recording nothing else still points at and unlinks the files after the rows are
   committed — the order `DELETE /sessions/{id}` uses. The export copies the script, its
   sections and every take whole, where scenarios, passages and prompts are named by slug:
   those are the project's content, a talk is not.
9. **The listener who asks questions is not built here, and when it is, its brief is the
   model's to draft and the learner's to change.** It is written down now because it
   decides the shape of what is stored: `presentations.audience_brief` exists and is null.

`PRD.md` §15 keeps user-authored scenarios out of scope, and a pasted script is
user-authored content. It is not a scenario: no persona, no goal, no grammar targets, and
nothing a model is asked to be. The tension is recorded rather than hidden, and the day a
listener is built from a script it is this record that has to be superseded.

## Measured

- All **12 of 12** seeded passages are scorable word by word, which is the regression test
  for the per-word check against the whole-text conversion the scorer actually uses.
  `Revenue grew 12% in Q3 2026, per the API.` names `12%` and `2026` and nothing else —
  `Q3` converts in one group and scores, against the phones of *q-three* — and the same
  text is refused by the scorer with a desync, which is what the naming predicts. Written
  as `twelve percent` and `twenty twenty-six`, nothing is named.
- Converting a 120-word section word by word costs **3 ms**, against 2 ms for the same text
  converted whole.
- One take on the live stack, a human recording of a nine-word line rehearsed against that
  line: **9 of 9 words matched**, 191 words a minute, no pauses, **35 phones scored**,
  median GOP 0.0, the three weakest all inside *curiosity*. Deleting the script took the
  take and its recording with it — the audio's own address answered 404 afterwards.
- A script saved with the scorer unreachable keeps every section scorable and reports the
  check as not made.

## Costs

- **A section over the cap is possible and not warned about.** One sentence of 200 words is
  saved whole; it is compared and counted, and its sounds take longer to score than a
  section's budget assumes.
- **A take cannot be scored again.** That is the price of not refusing accounts that keep
  no recordings.
- **Scorability is decided once.** A script saved while the pronunciation service was down
  keeps that answer until it is saved again.
- **Four more tables and nine more operations**, and an export that carries scripts and
  takes.

## Revisit if

- A reader pastes a script whose sections are wrong often enough to be worth a better
  split: the boundary editor is the cheap fix, a model is not.
- Somebody wants a take scored after the fact: that needs the waveform, which means
  refusing accounts without retention or keeping one recording per take for a while, and
  both are decisions this record did not take.
- Rehearsals are wanted on the progress page: that needs an argument for why practice of a
  chosen text belongs in a trend about unprepared speech.
