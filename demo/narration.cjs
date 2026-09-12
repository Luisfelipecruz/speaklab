/**
 * What the narrator says, by the id the recorder asks for it by.
 *
 * Written ahead of the take and synthesised before it starts, because a scene is held for
 * as long as its line lasts. So no line quotes a figure from the take: the stopwatch and
 * the captions carry those, counted on the day. Spelled for the ear, since the narrator
 * reads what is written — "wav to vec", not the model's name as it is typed.
 */
module.exports = {
  intro:
    'SpeakLab is a speaking coach that runs on one laptop. ' +
    'Every voice here is synthetic: the narrator, the learner, and the character.',
  brief: 'Each scenario sets a goal, gives you a character who pushes back, and names the grammar it is built to draw out of you.',
  persona: 'The character speaks first, out loud. That voice is Piper, running on the processor.',
  learner: 'The learner reads lines written with mistakes in them: a wrong tense, and a question built the wrong way.',
  pipeline: 'Whisper writes down what was said, Gemma 3 answers in character, and Piper speaks the reply. Nothing leaves the machine.',
  timing: 'Every turn prints its own timing: how long it took to hear, to think, and to speak.',
  no_interrupt: 'The character never corrects you in the middle of the conversation. That is deliberate. The report does.',
  report:
    'Ending the session runs the analysis. Fluency is arithmetic, grammar is a dependency parse, ' +
    'and the model\'s corrections are checked before they are shown.',
  marks: 'Each correction is marked on the words it was about.',
  no_marks: 'Nothing was flagged, and the report says so rather than inventing a mistake.',
  mishearing: 'A correction on words the recogniser was unsure of is shown, but not counted.',
  figures: 'What was counted sits apart from what the model wrote, under headings that say which is which.',
  unmeasured: 'And what has no analyser yet is listed, not left out.',
  grammar: 'The grammar page gathers every correction in the sentence it was said in, and any of them can be practised again, out loud.',
  reading_intro: 'Pronunciation has its own drill. Each passage is built around one group of sounds. Here, ship against sheep.',
  reading_during: 'Forced alignment finds every sound in the recording, and a wav to vec model scores each one against the sound the text asked for.',
  reading_check: 'Whisper checks the words first. The reader is synthetic, so the scores show the pipeline working, not an accent.',
  reading_result:
    'What comes back is the weakest sounds in this reading, measured against the reader\'s own typical sound. There is no pass mark.',
  answer_intro: 'Make your point is a work question, answered out loud in one go.',
  answer_during: 'There is a filler and a repeated phrase written into this answer.',
  answer_count: 'Fillers, repeats, reasons and examples are counted by code, not by the model.',
  answer_model: 'The model\'s shorter version is held back if it brings in words the speaker never said.',
  progress: 'Below the sample floor, the progress page says so, instead of drawing a line through a single point.',
  close:
    'Every figure here is counted from stored turns. The model explains; it never measures. ' +
    'SpeakLab: open source, and entirely local.',
};
