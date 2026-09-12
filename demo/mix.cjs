/**
 * The soundtrack and the subtitles of one take, built from its marks.
 *
 *   node mix.cjs out/portrait-short/speaklab-portrait-short.meta.json
 *
 * Writes beside the meta file:
 *
 *   <name>.mix.wav   48 kHz stereo, starting at the head cut, for to-mp4.sh's AUDIO=
 *   <name>.srt       the narration as subtitles, for a player or a post that takes them
 *
 * Every sound is placed at the moment the take made it, less the head cut, so it lines up
 * with a video cut at the same mark. The learner and the persona make one bus and the
 * narration another; the first is compressed by the second, so the app's voices dip while
 * the narrator speaks and come back when it stops. A reply that was paused fades out over
 * the last tenth of a second rather than clicking off. The result is normalised to -16
 * LUFS, the loudness feeds play at. It uses the containerised ffmpeg to-mp4.sh uses.
 */
const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const metaPath = process.argv[2];
if (!metaPath) {
  console.error('usage: node mix.cjs out/<take>/<name>.meta.json');
  process.exit(2);
}
const dir = path.dirname(path.resolve(metaPath));
const name = path.basename(metaPath, '.meta.json');
const meta = JSON.parse(fs.readFileSync(metaPath, 'utf8'));
const head = meta.head || 0;
const sounds = (meta.sounds || []).slice().sort((a, b) => a.at - b.at);
if (!sounds.length) {
  console.error(`${metaPath} lists no sounds: the take was recorded without them`);
  process.exit(1);
}

/** Seconds of audio in a PCM WAV, read from its header. */
function wavSeconds(file) {
  const b = fs.readFileSync(file);
  if (b.toString('ascii', 0, 4) !== 'RIFF' || b.toString('ascii', 8, 12) !== 'WAVE') {
    throw new Error(`${file} is not a WAV file`);
  }
  let offset = 12;
  let byteRate = 0;
  while (offset + 8 <= b.length) {
    const id = b.toString('ascii', offset, offset + 4);
    const size = b.readUInt32LE(offset + 4);
    if (id === 'fmt ') byteRate = b.readUInt32LE(offset + 16);
    if (id === 'data') {
      if (!byteRate) throw new Error(`${file}: data before its format`);
      return Math.min(size, b.length - offset - 8) / byteRate;
    }
    offset += 8 + size + (size % 2);
  }
  throw new Error(`${file} has no data chunk`);
}

const FADE = 0.12;
const inputs = [];
const chains = [];
const bus = { app: [], narration: [] };
const cues = [];
let end = 0;

for (const s of sounds) {
  const file = path.join(dir, s.file);
  if (!fs.existsSync(file)) throw new Error(`missing ${file}`);
  const length = wavSeconds(file);
  let from = s.from || 0;
  const to = s.to == null ? length : Math.min(s.to, length);
  let at = s.at - head;
  // Started before the head cut: only the part after it is heard.
  if (at < 0) {
    from -= at;
    at = 0;
  }
  if (to - from < 0.05) continue;

  const k = inputs.length / 2;
  inputs.push('-i', `/data/${s.file}`);
  const filters = [
    'aresample=48000',
    'aformat=sample_fmts=fltp:channel_layouts=stereo',
    `atrim=start=${from.toFixed(3)}:end=${to.toFixed(3)}`,
    'asetpts=PTS-STARTPTS',
  ];
  if (s.to != null && s.to < length - 0.05) {
    filters.push(`afade=t=out:st=${Math.max(0, to - from - FADE).toFixed(3)}:d=${FADE}`);
  }
  filters.push(`adelay=delays=${Math.round(at * 1000)}:all=1`);
  chains.push(`[${k}:a]${filters.join(',')}[s${k}]`);
  (s.kind === 'narration' ? bus.narration : bus.app).push(`s${k}`);
  end = Math.max(end, at + (to - from));
  if (s.kind === 'narration') cues.push({ start: at, end: at + (to - from), text: s.text || '' });
}

// Both buses padded to the same length, so neither ends the other.
const total = (end + 0.5).toFixed(3);
function mixBus(labels, out) {
  if (!labels.length) return false;
  const joined = labels.map((l) => `[${l}]`).join('');
  const sum = labels.length === 1 ? `${joined}anull` : `${joined}amix=inputs=${labels.length}:normalize=0`;
  chains.push(`${sum},apad=whole_dur=${total}[${out}]`);
  return true;
}
const hasApp = mixBus(bus.app, 'app');
const hasNarration = mixBus(bus.narration, 'narration');
if (hasApp && hasNarration) {
  chains.push('[narration]asplit=2[voice][key]');
  chains.push('[app][key]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=500[ducked]');
  chains.push('[ducked][voice]amix=inputs=2:normalize=0:duration=first[sum]');
} else {
  chains.push(`[${hasApp ? 'app' : 'narration'}]anull[sum]`);
}
chains.push('[sum]loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000[out]');

const output = `${name}.mix.wav`;
const run = spawnSync('docker', [
  'run', '--rm', '-v', `${dir}:/data`, 'linuxserver/ffmpeg',
  '-hide_banner', '-loglevel', 'error',
  ...inputs,
  '-filter_complex', chains.join(';'),
  '-map', '[out]', '-c:a', 'pcm_s16le', '-y', `/data/${output}`,
], { stdio: 'inherit' });
if (run.status !== 0) process.exit(run.status || 1);

// ── the subtitles: one cue per sentence, timed in proportion to its length ──
const stamp = (t) => {
  const ms = Math.round(t * 1000);
  const hh = String(Math.floor(ms / 3600000)).padStart(2, '0');
  const mm = String(Math.floor(ms / 60000) % 60).padStart(2, '0');
  const ss = String(Math.floor(ms / 1000) % 60).padStart(2, '0');
  return `${hh}:${mm}:${ss},${String(ms % 1000).padStart(3, '0')}`;
};
/** At most two lines of 42 characters, the usual limit for subtitles. */
function wrap(text) {
  const words = text.split(' ');
  const lines = [''];
  for (const w of words) {
    const line = lines[lines.length - 1];
    if (line && line.length + 1 + w.length > 42) lines.push(w);
    else lines[lines.length - 1] = line ? `${line} ${w}` : w;
  }
  return lines;
}
const srt = [];
for (const cue of cues) {
  const sentences = cue.text.match(/[^.;:!?]+[.;:!?]*/g).map((x) => x.trim()).filter(Boolean);
  const pieces = [];
  for (const sentence of sentences) {
    const lines = wrap(sentence);
    for (let i = 0; i < lines.length; i += 2) pieces.push(lines.slice(i, i + 2).join('\n'));
  }
  const chars = pieces.reduce((n, p) => n + p.length, 0);
  let t = cue.start;
  for (const piece of pieces) {
    const d = (cue.end - cue.start) * (piece.length / chars);
    srt.push(`${srt.length + 1}\n${stamp(t)} --> ${stamp(t + d)}\n${piece}\n`);
    t += d;
  }
}
fs.writeFileSync(path.join(dir, `${name}.srt`), srt.join('\n'));

const count = (kind) => sounds.filter((s) => s.kind === kind).length;
console.log(
  `${output}: ${total} s — ${count('narration')} narrated lines, ${count('learner')} learner clips, ` +
  `${count('reply')} stretches of the persona`);
console.log(`${name}.srt: ${srt.length} cues`);
