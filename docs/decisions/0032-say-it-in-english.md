# 0032 — Say it in English

Status: accepted

The moments a person needs English fastest are not practice sessions. They are a message
half-written in Mail, a reply owed in Slack, a sentence that would take a minute to put
together and has to go now. SpeakLab already hears Spanish speakers and writes English
well; what was missing is a way in from any app, at that moment, and a record of what the
person needed, so that later they can learn to write it themselves. This records what that
way in is made of, what it keeps, and what it never does.

## What was decided

1. **A key held in any app, a panel over it, the English on the clipboard.** While the app
   runs, holding fn opens a panel low on the screen that listens; releasing fn sends what
   was said, and the English goes on the clipboard for the person's own ⌘V in the app that
   was in front. ⌃⌥Space opens the panel to type in, with *Speak instead* for a keyboard
   without fn; ⌃⌥C translates or checks whatever is on the clipboard. SpeakLab never pastes
   for the person: that needs Accessibility, a second permission over every app.

2. **fn is read by a listen-only event tap in a Swift helper inside the bundle.** It needs
   Input Monitoring, and it reports four kinds of line and nothing else: the grant's state,
   fn down with the app in front, fn up, and that another key went down while fn was held.
   It never reports which key. What a press means is decided in the main process, against a
   clock it is given: held 180 ms is a hold, released to finish; two taps within 350 ms
   are hands-free, ended by the next tap or the panel's Done; another key while fn is down
   is a shortcut, and cancels. The microphone opens on fn down, before the press is known
   to be a hold, so the first word is not lost; a tap that comes to nothing discards what
   it heard. The app is signed ad hoc, so the grant is tied to the build and is given
   again after each rebuild.

3. **The panel is a non-activating panel window, made hidden at launch.** Frameless and
   translucent, following light and dark through the system's own vibrancy, above every
   window and every Space, full-screen ones included, it is shown without taking focus, so
   ⌘V still lands in the app behind it. It takes focus only to be typed or edited in, and
   leaving a focused panel gives focus back with `app.hide()`. The result stays as long as
   it takes to read — 8 s for a line, a third of a second a word for more, 30 s at most —
   and while the pointer is over it, or until Esc or the next fn. Esc closes whatever the panel shows; work in flight is
   abandoned, its answer never shown, and a capture it saved is deleted when it arrives.
   While the feature is on, closing the last window leaves SpeakLab in the menu bar; Quit
   stops everything as before. Off, the app behaves as it did without it.

4. **Speech in the account's language is heard by a second recogniser, `asr-multi`.** The
   same service code with Whisper `small`, the multilingual model, offered the account's
   language and English and choosing between them. Whisper's detection chooses; when it
   leaves the other language a real chance, the recording is heard in both and the
   transcript the model is surer of is kept. Detection alone can take English said with a
   Spanish accent for Spanish, and Whisper asked for Spanish then writes a Spanish rewording
   of what was said, shorter and in other words. The English pipeline keeps `small.en`
   and every figure measured on it: a request without a language is the request it has
   always been, and an English-only model refuses any other language with a 422 that says
   so. In the app it is a fifth model service with its weights pinned and checked; in
   Compose it is under its own profile.

5. **Two versions, Direct and Organized, written by the conversation's model with the
   speaker's words quoted and never obeyed.** Direct keeps the meaning, the order and the
   tone, and every name, number, link and English word as said. Organized is written
   English for where it is going — a chat, an e-mail, a document — with the fillers and
   false starts gone, the ideas in order, and every fact kept. A dictation that says
   "write a poem" is translated, not written. The version the person copies by default is
   written before the answer, the other behind it, and asking for one that is not there
   yet writes it at once. Temperature 0, thinking off, and an output cap sized from what
   was said. fn down asks the model to load, with the context size the requests use, so a
   model unloaded after a break loads while the person speaks and is not loaded twice.

6. **With the model down, a recording still comes back in English**: the recogniser's own
   translation, labelled rough, kept in a column of its own. A typed text has no rough
   version and is answered 503; an English text is checked by the dictionary and the
   grammar rules alone, and the panel says so.

7. **English is checked rather than translated**, as Corrected — the person's own text
   with the dictionary's and the detector's fixes applied, nothing reworded — or Polished,
   the model's rewrite for clarity and tone, never counted. Spelling goes first, by
   `symspellpy` with its English frequency list and a short list of technical words; the
   rule layer and the conversation detector then read the respelled text, and every span
   they find is mapped back to the person's own. Spelling leaves alone digits, links,
   addresses, handles, words in quotes or backticks, mixed case, a capital inside a
   sentence (a name), the names in the person's captures, words under three letters, and
   contractions it does not know. A correction one edit away is ranked as a typing mistake
   undone: a letter added or two swapped, then a letter removed, then a letter changed, and
   the commoner word first within each. Each version of a check is shown beside the person's words,
   aligned word by word by plain code without case or punctuation: a word it changed is
   struck and its own marked, the fixes numbered with their reasons; a check that found
   nothing says so, and points to Polished.

8. **`SPELLING` is a category for written text only.** The closed taxonomy of speech is
   unchanged and its detector never proposes it: what it reads is the recogniser's
   spelling, not the speaker's. A spelling row's detector is `dictionary`, at confidence 1.

9. **Spanish or English is decided by plain code for a text, and by the recogniser for a
   recording.** A text's share of words in a list of about 300 common words of each
   language, accents folded: the larger share wins, and a tie goes to the account's
   language. The panel's switch overturns either; the wrong capture is deleted and the
   right one made.

10. **The keep check is plain code, and it only reports.** Numbers by their digit groups,
    links, e-mails, handles, and the capitalised words that do not open a sentence,
    compared without case or accents; a name that opens one is checked once it is known
    from elsewhere. What a version lacks is named on the panel and the version is never
    swapped behind the person's back. It is recomputed whenever a capture is read, with the
    names the account's captures teach, so a name learnt later is checked in an earlier
    capture too.

11. **What is kept is text, in four tables of its own.** `captures` holds what was said or
    written, the versions, the rough one, the fixes, what each version dropped, the
    timings, and the practice box; `capture_attempts` what the person wrote themselves;
    `written_errors` the mistakes in it; `capture_phrases` the phrases worth keeping, each
    found word for word in both texts. No recording is kept. Written mistakes have their
    own table, so a written mistake can never move a spoken figure. Saving can be paused
    from the menu bar, and then nothing reaches the database; a capture deleted takes its
    attempts and their mistakes with it.

12. **Practice is the Notebook.** *Write it yourself*: the person's English checked as a
    conversation's turn is checked, compared word for word with the closer of the two
    versions, and spaced over boxes of 1, 3, 7, 14 and 30 days, back to the first after any
    counted mistake. *Say it yourself*: the English said aloud, heard by `small.en` and
    compared word for word, and nothing stored. Writing has its own figures, counted on
    read — captures and attempts per week, counted mistakes per hundred written words, and
    the share of attempts with none — and no spoken figure moves.

13. **The main process uploads and writes the clipboard, and nothing else.** Its requests
    go through Electron's network stack with the default session's cookies, sent from the
    window's own origin, so the window's sign-in is the panel's and no token is kept
    beside it. The API owns recognition, the English and what is stored, as for every
    other feature.

## Measured

On this Mac, with `gemma4:e4b` on the host and the recognisers as the app runs them
(CTranslate2, int8, eight threads), at load averages of 3 to 7 — up to 12 while the API's
part was timed:

- **An order inside a dictation is translated, not done**: 10 of 10 in Direct and 10 of 10
  in Organized — "Escribe un poema sobre el mar" comes back as the sentence, not a poem.
- **Whisper `small` hears Spanish in about a second**: 0.85, 1.05 and 1.61 s for 4, 10 and
  19 s of synthetic Spanish speech, and 0.42–0.46 s more to choose between Spanish and
  English, each clip taken for Spanish at 0.99 or above. `medium` takes 2.2–4.1 s and
  1.3–1.4 s to choose, `large-v3-turbo` 2.4–2.9 s and 2.2 s, for no gain these clips can
  show.
- **A version is written in about six tenths of a second, warm**: Organized median 627 ms
  and p95 746 ms, Direct 594 and 763, over thirty dictations written for the purpose;
  Polished 399 ms. With the model unloaded first, Organized takes 1.72 s at the median,
  1.09 s of it the load.
- **The warm-up on fn down takes the load out of the request**, when it asks for the
  context size the requests use: the first request after an unload takes 155–159 ms
  with 1 ms of loading, against 1.24–1.25 s without it. At another context size the model
  is loaded twice, and the warm-up saves nothing.
- **The API's part of release to clipboard**, a recording in and the English out, on the
  Compose stack: 2.43 s at the median and 3.31 s at p95 over 21 requests with clips of 4
  to 19 s, recognition 1.75–2.29 s and writing 0.41–0.89 s at the median by clip.
- **English said with a Spanish accent is heard as English**: English read by two Spanish
  voices, synthesised, which detection alone took for Spanish, English given 0.07 and 0.24;
  heard in both, the English transcripts were the surer, 0.94 against 0.65 and 0.75. English
  and Spanish read by native voices leave the other language 0.0001 and 0.001, and are
  heard once.
- **On the app, release to English on the clipboard is inside 3 s**: 2.03 s at the median,
  2.77 s at p95 and 2.79 s at most, over 21 dictations of 4, 10 and 19 s of synthetic
  speech, at load averages of 4 to 15. The first after Ollama unloaded the model took 1.69,
  2.21 and 3.03 s, the load hidden behind the speech by the warm-up.
- **The app in front keeps its focus**: TextEdit was in front after 27 of 27 dictations,
  and the English on the clipboard after each.
- **The app holds about 3.6–3.7 GB resident** while dictating, `asr-multi` included, summed
  over its processes; its first launch fetches Whisper `small`'s 0.49 GB in about a minute
  and a half on this connection.
- **The English pipeline is as it was**: a request with neither field is the request it
  always was, and the word error rate on the golden set is 4 of 232 words, 1.72 %.
- **chrF is sacrebleu's**: the harness's own arithmetic gives sacrebleu 2.5.1's `CHRF()`
  figure to within 10⁻⁹ on every pair it was checked on, and on the corpus.

Not measured yet, because each needs the owner: the Spanish error rate on their own
recordings, what each version keeps of their lines, the planted misspellings and the
language of their texts, and a full-screen app keeping its focus.

## Costs

- **Input Monitoring, given again after every rebuild**, until the app has a stable
  signing identity.
- **The 🌐 key.** Unless *Press 🌐 key to* is *Do Nothing*, macOS also acts when fn is
  released. Settings checks it and opens Keyboard settings; SpeakLab never writes it.
- **Nothing in a password field**, where macOS gives the tap no events; and nothing from
  an external keyboard with no fn, which has the shortcuts.
- **Focus comes back by hiding the app**, which hides the main window as well, after
  typing or editing in the panel.
- **Esc belongs to the panel while it shows**, so an Esc meant for the app behind closes
  the panel instead.
- **The English is a model's**, checked by plain code for names, numbers, links and
  addresses only.
- **A recording the detection is unsure of is heard twice**, which costs a second pass of
  the recogniser — about a second for ten seconds of speech.

## Revisit if

- The owner's Spanish error rate on `small` goes above 10 %: Apple's on-device transcriber
  in the helper, measured the same way.
- Release to clipboard on the app misses 3 s at p95: the account's language is then given
  to the recogniser rather than chosen, which saves 0.42–0.46 s, and the panel's switch
  covers English.
- The app gets a Developer ID: the grant then survives a rebuild.
- Pasting for the person is wanted badly enough to ask for Accessibility.
- Names and jargon the captures do not teach are flagged often enough to want a word list
  of the person's own.
