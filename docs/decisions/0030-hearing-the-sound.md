# 0030 — Hearing the sound

Status: accepted · narrows §2 of "Two deliberate choices" in [0002](0002-tts-model-choice.md)

That section refused a browser-facing synthesis route. It is narrowed here rather than
reversed, and the reason it can be narrowed is that the route added is not the route that
was refused.

A screen that names a sound can now play it. *The "z" at the end of "is"* tells a speaker
which sound to attend to and nothing about what it should sound like, and the distance
between those two is most of the distance between a measurement and something a person
can practise. This records the route, why the word it speaks is not the caller's to
choose, and the two things that had to be measured before any of it could ship.

## What was decided

1. **`GET /speak/{word}` speaks one word, from a closed set.** The set is the example
   words in `services/phone_names.py`, the words of the shipped passages, and the words
   of the requester's own scripts. Anything else is **404 rather than 400**: the caller is
   not owed the difference between *that is not a word* and *that is not a word you may
   hear*, and a 400 would confirm the shape of the set to somebody probing it. Somebody
   else's script is not in the set, so the same request is a 200 for one account and a 404
   for another.

   The earlier refusal stands where it was aimed. What was declined was a general
   text-to-speech endpoint, on the grounds that no requirement asked for one; the
   requirement that exists now is *let me hear this sound in a word I have to say*, and it
   is served by a vocabulary rather than a text box. `POST /synthesize` remains unreachable
   from the browser.

2. **The word is checked with the tokeniser that compares a script with what was heard.**
   `services/wer.normalise`, not a second idea of what a word is. The words offered to
   hear are then exactly the words the differences screen shows. A request that
   normalises to two words, or to none, is refused before the set is consulted; a figure
   is governed by the same rule as any other word rather than by a special case.

3. **This synthesis is repeatable, and it is the only one that is.** The voice draws
   noise in two places, so the same text comes back a different length and a different
   waveform every call. That is right for a persona's reply, which is speech, and wrong
   for a word held up to be imitated, which is a specimen. The route passes zero for both
   noise settings; `POST /synthesize` keeps the voice's own defaults, so nothing about
   ordinary speech changes. Pinning them globally would have flattened every reply in the
   product to fix a button.

4. **Nothing is stored, and the browser is still not made to wait twice.** Because the
   audio is a pure function of the voice, the word and those two settings, the response
   carries an `ETag` computed from exactly those — which means a caller that already holds
   the word is answered **before anything is synthesised**. The alternative considered was
   an audio asset keyed by voice and word, shared between accounts; it was rejected
   because `audio_assets` rows are reached through an ownership check that folds existence
   and ownership into one `WHERE`, and rows belonging to nobody would have needed that
   check to learn an exception. A word costs 23 ms, which is not worth an exception.

5. **The button appears wherever a sound is named, and says what it plays.** On the sounds
   list it sits on each of the speaker's own words, because a sound is worth hearing in the
   words they have to say rather than in a specimen. In the confusion table it sits on the
   first column only. The second column is the acoustic model's own symbol for whatever
   won the segment, and synthesising it would be asserting an English sound nothing in
   this system ever claimed. The label reads *hear "is"* and never *hear the correct
   pronunciation*: what plays is one synthetic reading by one voice, and a screen that
   promoted it to a standard would be making a claim about English this project has not
   measured.

## Measured

Everything here was run on the live stack rather than recalled.

- **The voice was judged by ear before any of it was built.** Ten recordings of the five
  words the feature speaks — alone, and inside a carrier phrase — were listened to, and
  the voice was judged fit to stand under the button. It had never been judged before:
  earlier work measured its latency, its size and its format, and nothing about how it
  sounds.
- **The voice does not say a word the same way twice.** Eight renderings of each of the
  five words: the spread between the shortest and the longest is **18 % to 59 %**, with
  *think* ranging 0.39 s to 0.63 s. Zeroing the duration noise alone pins the length and
  still yields three different waveforms in three runs; zeroing both gives one identical
  output every time. Over five consecutive requests to the live route the audio is
  byte-identical.
- **One word costs 23 ms** — median of eight, 21 to 24 — against 320 ms measured for an
  eighty-token reply. The first call to a word not spoken before is 22 to 38 ms.
- **A word the caller already holds costs 1.9 ms** — median of five, 1.5 to 2.7 — and is
  answered with no synthesis at all.
- **The closed set refuses what it should.** A real word, correctly spelled, sitting in a
  script this system holds, is a 404 for an account that does not own that script and a
  200 for the account that does.
- **Thirty-nine sounds, thirty-nine words.** Every phone in the inventory has an example
  word, and every one of them can be spoken.

## Costs

- **A second route that reaches the voice.** It is narrow — one word, from a set the
  system chose, for a signed-in caller — but it is a second door, and the argument for
  the first one staying shut now rests on that narrowness rather than on there being no
  door at all.
- **Two synthesis settings the product had never used.** Silencing the voice's noise is
  the setting most likely to sound flat, and what ships under the button is therefore not
  the rendering that was judged when the voice was first listened to. Recordings of the
  pinned rendering of all five words were produced and are what the decision to pin was
  taken against, but the judgement that matters is the one made on a screen, which is why
  it is the first thing under *Revisit if*.
- **A button that can fail in place.** A word that cannot be played marks itself and
  leaves the rest of the list working, which means a broken voice degrades quietly rather
  than loudly. The service's own health check is what says it is broken.
- **A per-account answer to a per-word question.** The same URL is a 200 or a 404
  depending on who asks, which is correct and is also the kind of thing that confuses a
  shared cache. The response says `private` for that reason.

## Revisit if

- **The pinned rendering is judged flat in use**, on a screen rather than in a sample
  folder. The fallback is to store the first natural rendering per word instead, which
  buys stability without changing how the voice sounds and costs the ownership argument
  above.
- **The voice is swapped.** A voice that is not stochastic makes the whole pinning
  question disappear, and a voice with a different character would need judging again
  before it could stand under a button that means *listen to this*.
- **The closed set stops being cheap to check.** It is two narrow queries against small
  tables today. A corpus large enough to make that a page-load cost would justify an
  index or a materialised vocabulary, neither of which is worth building now.
