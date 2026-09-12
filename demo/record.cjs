/**
 * The SpeakLab walkthrough — one capture, driven against the running stack, and narrated.
 *
 *   npm install && npx playwright install chromium
 *   ./piper.sh up                the learner's voice and the narrator's, beside the stack
 *   ./voices.sh                  the learner's lines, synthesised, into voice/
 *   VOICE=voice node record.cjs
 *   CUT=short      …          about eighty seconds: one turn and its report
 *   FORMAT=square  …          1:1 instead of the 4:5 default
 *   FORMAT=wide    …          1280x720 for the README
 *   NARRATOR=      …          no narration
 *   KEEP=1         …          leave the account's sessions in the database afterwards
 *
 * A take writes into out/<format>-<cut>/, and empties only that folder when it starts:
 *
 *   speaklab-<format>-<cut>.webm          the capture, which has no sound
 *   speaklab-<format>-<cut>-poster.png    the thumbnail — a native render, not a video frame
 *   speaklab-<format>-<cut>.meta.json     the marks: where the dead opening ends, every
 *                                         measured latency, and every sound and its moment
 *   narration/  voice/  app/              those sounds, as files
 *
 * It prints the two commands that finish it: mix.cjs builds the soundtrack and the
 * subtitles from the marks, and to-mp4.sh encodes the video with that soundtrack.
 *
 * ── The microphone ────────────────────────────────────────────────────────
 *
 * A headless browser has no microphone, and this product is a microphone. The recorder
 * therefore replaces `getUserMedia` with a stream played from a WAV file — and the WAV
 * files are lines written for the take and spoken by a synthetic voice that is not the
 * persona's (`voices.sh`), with the mistakes and hesitations the take is meant to show
 * written into them. Nothing downstream of the stream is touched: the clip goes through
 * MediaRecorder, the upload, Whisper, the persona model and Piper exactly as a live turn
 * does, and the stopwatch measures exactly that path.
 *
 * The caption says so on screen. A demo that presents a synthetic voice as a learner is
 * making a claim the take does not support; one that says "a synthetic voice, reading
 * lines written for it" is making one it does. It also means the pronunciation scores in
 * the take show the pipeline working, not how anybody's accent scores: the acoustic
 * model is out of its domain on synthetic speech, which is why no golden set in this
 * repository is synthesised. Point VOICE at a directory holding the clips named in CLIPS,
 * READING and ANSWER below; the recorder refuses to start without them.
 *
 * ── The sound ─────────────────────────────────────────────────────────────
 *
 * A browser recording is pictures only. The soundtrack is rebuilt from what the take did,
 * at the moment it did it: each learner clip from the instant the replaced microphone
 * started playing it; each persona reply from the instant its <audio> element began
 * playing to the instant it paused or ended, cut from the file fetched afterwards from
 * the address it played from; and each narrated line from the instant its scene started
 * it.
 *
 * The narrator is a third synthetic voice, and its first line says so. Its lines are in
 * narration.cjs and are synthesised before the take, because a scene is held for as long
 * as its line lasts; none of them quotes a figure from the take. The persona's opening
 * and the learner's turns are not talked over. The replies and the long recordings are,
 * and the mix lowers them while the narrator speaks.
 *
 * ── The stopwatch ─────────────────────────────────────────────────────────
 *
 * Runs on requestAnimationFrame off the real wall clock. It starts the moment the
 * record button is released — that is when the clip is sent — and stops when the reply
 * (or the scored reading) is actually on the page. Speed-ramp the file afterwards and
 * the clock visibly jumps instead of counting: the edit declares itself, and the true
 * elapsed time stays in frame. Do not remove it to make the video look faster. The app
 * prints its own "heard / thought / spoke" line under the button as well; the two
 * numbers should agree to within the network round trip.
 *
 * ── What is created, and what is deleted ─────────────────────────────────
 *
 * A fresh account per take, so the take never touches anybody's practice. Its sessions
 * are deleted at the end unless KEEP=1, because a replayed turn is real speech through
 * the real pipeline and would count in `make corpus` as though somebody had practised
 * twice. The account row itself stays, and so does its spoken answer; there is no
 * endpoint that removes either. The replies are fetched before the sessions go.
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const LINES = require('./narration.cjs');

const WEB = process.env.WEB || 'http://localhost:3003';
const API = process.env.API || 'http://localhost:8002';
const VOICE = process.env.VOICE;
const KEEP = process.env.KEEP === '1';
// The narrator's Piper, where piper.sh starts it. Empty for a take without narration.
const NARRATOR = process.env.NARRATOR ?? 'http://localhost:8113';

// The learner's lines by file stem inside VOICE, as voices.sh writes them: two turns of
// the apartment viewing, a reading of the passage, and one spoken answer to the prompt.
const CLIPS = (process.env.CLIPS || 'turn1,turn2').split(',');
const READING = process.env.READING || 'reading';
const ANSWER = process.env.ANSWER || 'answer';
const SCENARIO = process.env.SCENARIO || 'apartment-viewing';
const PASSAGE = process.env.PASSAGE || 'the-ship-and-the-sheep';
const PROMPT = process.env.PROMPT || 'explain-a-missed-deadline';

// `full` films every section. `short` films one turn and its report: a reading alone is
// half a minute of speech and scoring, and a take is never cut to hide how long things take.
const CUTS = ['short', 'full'];
const CUT = process.env.CUT || 'full';
if (!CUTS.includes(CUT)) throw new Error(`CUT must be one of ${CUTS}`);
const FULL = CUT === 'full';

const FORMATS = {
  portrait: { W: 864, H: 1080, OUT_W: 1080, OUT_H: 1350 },
  square: { W: 864, H: 864, OUT_W: 1080, OUT_H: 1080 },
  wide: { W: 1280, H: 720, OUT_W: 1280, OUT_H: 720 },
};
const FORMAT = process.env.FORMAT || 'portrait';
if (!FORMATS[FORMAT]) throw new Error(`FORMAT must be one of ${Object.keys(FORMATS)}`);
const { W, H, OUT_W, OUT_H } = FORMATS[FORMAT];
const DSF = OUT_W / W;

const NAME = `speaklab-${FORMAT}-${CUT}`;
const OUT = path.join(__dirname, 'out', `${FORMAT}-${CUT}`);

// How long a persona reply is heard before it is paused: to its end in the full cut,
// within a bound because its length is the model's choice, and its opening in the short.
const REPLY_MS = FULL ? 15000 : 4000;

if (!VOICE) throw new Error('VOICE must point at a directory of WAV clips — see the header');
for (const stem of [...CLIPS, READING, ANSWER]) {
  const f = path.join(VOICE, `${stem}.wav`);
  if (!fs.existsSync(f)) throw new Error(`missing clip ${f}`);
}

// ── the overlay: caption, cursor, click ripple, stopwatch ──────────────────
function overlay() {
  const install = () => {
    if (!document.body || document.getElementById('__c_layer')) return;
    const st = document.createElement('style');
    st.textContent = `
      nextjs-portal{display:none!important}
      #__c_layer{position:fixed;inset:0;z-index:2147483647;pointer-events:none;
        font-family:ui-sans-serif,-apple-system,"Segoe UI",sans-serif}
      #__c_lab{position:absolute;left:50%;bottom:72px;transform:translateX(-50%) translateY(10px);
        padding:12px 26px;border-radius:999px;background:rgba(12,20,24,.93);color:#fff;
        font-size:21px;font-weight:600;letter-spacing:-.01em;max-width:80vw;text-align:center;
        line-height:1.3;box-shadow:0 14px 44px rgba(0,0,0,.4);
        opacity:0;transition:opacity .32s ease,transform .32s ease}
      #__c_lab.on{opacity:1;transform:translateX(-50%) translateY(0)}
      #__c_lab em{font-style:normal;color:#5eead4;font-weight:700}
      #__c_clk{position:absolute;top:22px;right:26px;padding:8px 16px;border-radius:10px;
        background:rgba(12,20,24,.9);color:#fff;font-variant-numeric:tabular-nums;
        font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:19px;font-weight:600;
        opacity:0;transition:opacity .25s ease}
      #__c_clk.on{opacity:1}
      #__c_clk.stopped{color:#5eead4}
      #__c_cur{position:absolute;width:20px;height:20px;margin:-10px 0 0 -10px;border-radius:50%;
        background:rgba(13,148,136,.28);border:2px solid #0d9488;box-shadow:0 0 0 5px rgba(13,148,136,.14);
        opacity:0;transition:opacity .25s ease;will-change:transform}
      #__c_cur.on{opacity:1}
      #__c_cur.held{background:rgba(220,38,38,.28);border-color:#dc2626;box-shadow:0 0 0 7px rgba(220,38,38,.16)}
      .__c_rip{position:absolute;width:18px;height:18px;margin:-9px 0 0 -9px;border-radius:50%;
        border:2.5px solid #0d9488;animation:__c_r .55s ease-out forwards}
      @keyframes __c_r{to{transform:scale(3.4);opacity:0}}`;
    document.head.appendChild(st);
    const l = document.createElement('div');
    l.id = '__c_layer';
    l.innerHTML = '<div id="__c_lab"></div><div id="__c_clk">0.0 s</div><div id="__c_cur"></div>';
    document.body.appendChild(l);
    document.addEventListener('mousemove', (e) => {
      const c = document.getElementById('__c_cur');
      if (!c) return;
      c.classList.add('on');
      c.style.transform = `translate(${e.clientX}px,${e.clientY}px)`;
    }, true);
    document.addEventListener('mousedown', (e) => {
      const L = document.getElementById('__c_layer');
      if (!L) return;
      const r = document.createElement('div');
      r.className = '__c_rip';
      r.style.transform = `translate(${e.clientX}px,${e.clientY}px)`;
      L.appendChild(r);
      setTimeout(() => r.remove(), 650);
      document.getElementById('__c_cur')?.classList.add('held');
    }, true);
    document.addEventListener('mouseup', () => {
      document.getElementById('__c_cur')?.classList.remove('held');
    }, true);
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install);
  else install();

  window.__lab = (html) => {
    install();
    const e = document.getElementById('__c_lab');
    if (!e) return;
    e.innerHTML = html || '';
    e.classList.toggle('on', !!html);
  };
  window.__cur = (on) => {
    const c = document.getElementById('__c_cur');
    if (c) c.classList.toggle('on', !!on);
  };
  window.__clock = (cmd) => {
    install();
    const e = document.getElementById('__c_clk');
    if (!e) return;
    if (cmd === 'start') {
      const t0 = performance.now();
      e.classList.add('on');
      e.classList.remove('stopped');
      cancelAnimationFrame(window.__cf || 0);
      const tick = () => {
        e.textContent = ((performance.now() - t0) / 1000).toFixed(1) + ' s';
        window.__cf = requestAnimationFrame(tick);
      };
      tick();
    } else if (cmd === 'stop') {
      cancelAnimationFrame(window.__cf || 0);
      e.classList.add('stopped');
    } else if (cmd === 'hide') {
      cancelAnimationFrame(window.__cf || 0);
      e.classList.remove('on');
    }
  };

  // ── the soundtrack's log: every clip started, every reply played and stopped ──
  // Media events do not bubble, so they are caught on the way down.
  const log = (entry) => {
    if (window.__audioLog) window.__audioLog(entry).catch(() => {});
  };
  for (const type of ['playing', 'pause', 'ended']) {
    document.addEventListener(type, (e) => {
      const el = e.target;
      if (el instanceof HTMLMediaElement) {
        log({ type, src: el.currentSrc, pos: el.currentTime, t: Date.now() });
      }
    }, true);
  }

  // ── the microphone: a WAV played into a MediaStream, chosen per press ──
  // `window.__clip` names the clip the NEXT getUserMedia call will play. Everything
  // the app does with the stream — MediaRecorder, the analyser behind the waveform,
  // stopping the tracks on release — is unchanged; only the source is.
  const real = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
  navigator.mediaDevices.getUserMedia = async (constraints) => {
    const name = window.__clip;
    if (!name) return real(constraints);
    const ctx = new AudioContext({ sampleRate: 48000 });
    const bytes = await (await fetch(`/__voice/${name}.wav`)).arrayBuffer();
    const audio = await ctx.decodeAudioData(bytes);
    const src = ctx.createBufferSource();
    src.buffer = audio;
    const dest = ctx.createMediaStreamDestination();
    src.connect(dest);
    src.start();
    log({ type: 'clip', name, t: Date.now() });
    window.__clipMs = Math.round(audio.duration * 1000);
    return dest.stream;
  };
}

const t0 = Date.now();
const at = () => ((Date.now() - t0) / 1000).toFixed(1);
const wait = (p, ms) => p.waitForTimeout(ms);
const lab = (p, html) => p.evaluate((h) => window.__lab(h), html);
const clock = (p, cmd) => p.evaluate((c) => window.__clock(c), cmd);
const glide = (p, x, y, s = 24) => p.mouse.move(x, y, { steps: s });

async function centre(loc) {
  const b = await loc.boundingBox();
  if (!b) throw new Error('no bounding box for ' + loc);
  return { x: b.x + b.width / 2, y: b.y + b.height / 2 };
}
async function tap(page, loc, pause = 400) {
  await loc.scrollIntoViewIfNeeded();
  const { x, y } = await centre(loc);
  await glide(page, x, y);
  await wait(page, pause);
  await page.mouse.down();
  await wait(page, 90);
  await page.mouse.up();
}

/** Bring an element into frame at the top and hold. The camera follows the caption. */
async function show(page, loc, settle = 900) {
  await loc.first().waitFor({ timeout: 20000 });
  await loc.first().evaluate((el) => el.scrollIntoView({ block: 'start', behavior: 'smooth' }));
  await wait(page, settle);
}

let vt0 = 0;
const MARKS = {};
const markNow = (name) => { MARKS[name] = +((Date.now() - vt0) / 1000).toFixed(2); };
const since = (t) => +((t - vt0) / 1000).toFixed(3);

// What the page reported playing, as it arrived, and the sounds the soundtrack is built from.
const PLAYED = [];
const SOUNDS = [];
const NARRATION_MS = {};

/** Every narrated line, synthesised and measured before the take. Returns the voice. */
async function prepareNarration() {
  const health = await fetch(`${NARRATOR}/health`).then((r) => r.json()).catch(() => null);
  if (!health || !health.voice_loaded) {
    throw new Error(`no narrator at ${NARRATOR}: ./piper.sh up, or NARRATOR= for a take without one`);
  }
  const dir = path.join(OUT, 'narration');
  fs.mkdirSync(dir, { recursive: true });
  for (const [id, text] of Object.entries(LINES)) {
    const res = await fetch(`${NARRATOR}/synthesize`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ text }),
    });
    if (!res.ok) throw new Error(`narration ${id}: ${res.status} ${await res.text()}`);
    fs.writeFileSync(path.join(dir, `${id}.wav`), Buffer.from(await res.arrayBuffer()));
    NARRATION_MS[id] = Number(res.headers.get('x-duration-ms'));
  }
  return health.voice;
}

/** Start one narrated line. Resolves once it has been said. */
function narrate(id) {
  if (!NARRATOR) return Promise.resolve();
  const ms = NARRATION_MS[id];
  if (ms === undefined) throw new Error(`no narration line "${id}"`);
  SOUNDS.push({ kind: 'narration', id, text: LINES[id], file: `narration/${id}.wav`, at: since(Date.now()) });
  return new Promise((resolve) => setTimeout(resolve, ms + 250));
}

/** Hold the scene for a narrated line, and for at least `ms` with or without narration. */
async function hold(page, id, ms) {
  await Promise.all([narrate(id), wait(page, ms)]);
}

async function poster(page, file) {
  await lab(page, '');
  await page.evaluate(() => window.__cur(false));
  await wait(page, 360);
  await page.screenshot({ path: file });
  await page.evaluate(() => window.__cur(true));
  markNow('poster');
  console.log(`   poster ${file} ${OUT_W}x${OUT_H} at ${MARKS.poster}s`);
}

/**
 * Hold the record button for the length of one clip, release, and time what follows.
 * `until` resolves when the thing the clip produced is on the page. Returns elapsed ms
 * from release to that moment — the figure on the stopwatch. `sayDuring` is narrated once
 * the clip's first words have been heard, and `sayAfter` from the release, after it.
 */
async function speak(page, clip, { during, sayDuring, after, sayAfter, until, mark }) {
  await page.evaluate((c) => { window.__clip = c; }, clip);
  const button = page.getByRole('button', { name: 'Hold to speak' });
  await button.waitFor({ timeout: 60000 });
  await button.scrollIntoViewIfNeeded();
  const { x, y } = await centre(button);
  await glide(page, x, y);
  await wait(page, 500);

  await page.mouse.down();
  markNow(`${mark}_hold`);
  // getUserMedia resolves inside the press; read the clip length it measured.
  await page.waitForFunction(() => window.__clipMs > 0, null, { timeout: 15000 });
  const clipMs = await page.evaluate(() => { const v = window.__clipMs; window.__clipMs = 0; return v; });
  const lead = during || sayDuring ? Math.min(sayDuring ? 4000 : 3000, clipMs / 3) : 0;
  let saying = Promise.resolve();
  if (lead) {
    await wait(page, lead);
    if (during) await lab(page, during);
    if (sayDuring) saying = narrate(sayDuring);
  }
  await wait(page, Math.max(0, clipMs + 350 - lead));
  await page.mouse.up();
  await page.evaluate(() => { window.__clip = null; });
  markNow(`${mark}_sent`);

  await clock(page, 'start');
  const started = Date.now();
  if (after) await lab(page, after);
  // One narrator at a time: the line after the release waits for the one during the clip.
  if (sayAfter) saying = saying.then(() => narrate(sayAfter));
  await until();
  await clock(page, 'stop');
  const elapsed = Date.now() - started;
  MARKS[`${mark}_ms`] = elapsed;
  markNow(`${mark}_done`);
  console.log(`   ${mark}: clip ${clipMs} ms, answered in ${elapsed} ms`);
  await saying;
  return elapsed;
}

/** The persona's reply autoplays and the microphone is closed while it speaks. */
async function pauseReply(page) {
  const pause = page.getByRole('button', { name: /^Pause/ }).last();
  if (!(await pause.count())) return;
  await pause.scrollIntoViewIfNeeded();
  const { x, y } = await centre(pause);
  await glide(page, x, y);
  await wait(page, 250);
  // A click that checks the button is still where the pointer is: the transcript scrolls
  // itself as a reply arrives, and a press on a button that has moved lands on nothing.
  await pause.click();
  const paused = await page.waitForFunction(
    () => ![...document.querySelectorAll('audio')].some((a) => !a.paused), null, { timeout: 2000 },
  ).then(() => true, () => false);
  if (!paused) console.log('   the reply did not pause');
}

/** Let the persona's reply be heard — to its end, or for `ms` — and then pause it. */
async function hearReply(page, ms) {
  const playing = () => [...document.querySelectorAll('audio')].some((a) => !a.paused);
  await page.waitForFunction(playing, null, { timeout: 2000 }).catch(() => {});
  await page.waitForFunction(() => ![...document.querySelectorAll('audio')].some((a) => !a.paused),
    null, { timeout: ms }).catch(() => {});
  await pauseReply(page);
}

async function register() {
  const email = `demo-${Date.now()}@speaklab.dev`;
  const password = `Take-${Math.random().toString(36).slice(2, 10)}-${Date.now() % 9973}`;
  const res = await fetch(`${API}/auth/register`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ email, password, native_language: 'es' }),
  });
  if (res.status !== 201) throw new Error(`register: ${res.status} ${await res.text()}`);
  const raw = res.headers.getSetCookie ? res.headers.getSetCookie().join('\n') : res.headers.get('set-cookie');
  const m = /speaklab_session=([^;]+)/.exec(raw || '');
  if (!m) throw new Error('no session cookie on register');
  return { email, cookie: m[1] };
}

/**
 * The learner's clips and the persona's replies, as sounds on the take's clock. A reply is
 * the stretch between its <audio> element starting to play and pausing or ending, cut
 * from the file it was playing.
 */
async function collectSounds(cookie) {
  fs.mkdirSync(path.join(OUT, 'voice'), { recursive: true });
  fs.mkdirSync(path.join(OUT, 'app'), { recursive: true });
  const files = new Map();
  const fetched = async (src) => {
    if (!files.has(src)) {
      const res = await fetch(src, { headers: { cookie: `speaklab_session=${cookie}` } });
      if (!res.ok) throw new Error(`reply audio ${src}: ${res.status}`);
      const file = `app/reply-${files.size + 1}.wav`;
      fs.writeFileSync(path.join(OUT, file), Buffer.from(await res.arrayBuffer()));
      files.set(src, file);
    }
    return files.get(src);
  };
  const open = new Map();
  for (const e of [...PLAYED].sort((a, b) => a.t - b.t)) {
    if (e.type === 'clip') {
      const file = `voice/${e.name}.wav`;
      fs.copyFileSync(path.join(VOICE, `${e.name}.wav`), path.join(OUT, file));
      SOUNDS.push({ kind: 'learner', file, at: since(e.t) });
    } else if (e.type === 'playing') {
      if (!open.has(e.src)) open.set(e.src, e);
    } else if (open.has(e.src)) {
      const start = open.get(e.src);
      open.delete(e.src);
      SOUNDS.push({
        kind: 'reply', file: await fetched(e.src), at: since(start.t),
        from: +start.pos.toFixed(3), to: e.type === 'ended' ? null : +e.pos.toFixed(3),
      });
    }
  }
  // Still playing when the take ended: it runs to the end of its file.
  for (const [src, start] of open) {
    SOUNDS.push({ kind: 'reply', file: await fetched(src), at: since(start.t), from: +start.pos.toFixed(3), to: null });
  }
  SOUNDS.sort((a, b) => a.at - b.at);
}

async function cleanup(cookie) {
  const headers = { cookie: `speaklab_session=${cookie}` };
  const list = await (await fetch(`${API}/sessions`, { headers })).json();
  const rows = Array.isArray(list) ? list : list.items || list.sessions || [];
  for (const s of rows) {
    const r = await fetch(`${API}/sessions/${s.id}`, { method: 'DELETE', headers });
    console.log(`   deleted session ${s.id}: ${r.status}`);
  }
  return rows.length;
}

(async () => {
  fs.rmSync(OUT, { recursive: true, force: true });
  fs.mkdirSync(OUT, { recursive: true });

  if (NARRATOR) {
    MARKS.narrator = await prepareNarration();
    const said = Object.values(NARRATION_MS).reduce((a, b) => a + b, 0);
    console.log(`narration: ${Object.keys(NARRATION_MS).length} lines, ${(said / 1000).toFixed(1)} s, ${MARKS.narrator}`);
  }

  const account = await register();
  console.log('account', account.email, 'cut', CUT);

  const browser = await chromium.launch({
    headless: true,
    args: [
      '--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader',
      '--ignore-gpu-blocklist', '--force-color-profile=srgb', '--hide-scrollbars',
      '--autoplay-policy=no-user-gesture-required',
    ],
  });

  const cookies = [
    { name: 'speaklab_session', value: account.cookie, domain: 'localhost', path: '/', httpOnly: true },
  ];

  // Warm the ROUTES: the frontend runs `next dev`, and the first visit to a route
  // compiles it. Filming a compile would put twenty seconds of spinner in the take
  // that a production build never shows.
  const warm = await browser.newContext({ viewport: { width: W, height: H } });
  await warm.addCookies(cookies);
  const wp = await warm.newPage();
  for (const u of ['/home', '/scenarios', `/scenarios/${SCENARIO}`, '/read', `/read/${PASSAGE}`,
                   '/sessions', '/sessions/1', '/grammar', '/answers', `/answers/${PROMPT}`,
                   '/progress']) {
    try { await wp.goto(WEB + u, { waitUntil: 'networkidle', timeout: 90000 }); } catch {}
  }
  await warm.close();
  console.log('warm-up done', at());

  const context = await browser.newContext({
    viewport: { width: W, height: H },
    deviceScaleFactor: DSF,
    colorScheme: 'light',
    permissions: ['microphone'],
    recordVideo: { dir: OUT, size: { width: W, height: H } },
  });
  await context.exposeBinding('__audioLog', (_source, entry) => { PLAYED.push(entry); });
  await context.addCookies(cookies);
  await context.route('**/__voice/*.wav', (route) => {
    const stem = path.basename(new URL(route.request().url()).pathname, '.wav');
    route.fulfill({ body: fs.readFileSync(path.join(VOICE, `${stem}.wav`)), contentType: 'audio/wav' });
  });
  await context.addInitScript(overlay);
  const page = await context.newPage();
  page.setDefaultTimeout(120000);
  vt0 = Date.now();

  const rail = (href) => page.locator(`nav a[href="${href}"]`).first();
  // Counted off the page on the day of the take, so a caption cannot fall behind the seeds.
  const distinct = (prefix) => page.$$eval(`main a[href^="${prefix}"]`,
    (links) => new Set(links.map((a) => a.getAttribute('href'))).size);

  // ── A · the scenarios ─────────────────────────────────────────────────
  await page.goto(WEB + '/scenarios', { waitUntil: 'networkidle' });
  await page.locator(`a[href="/scenarios/${SCENARIO}"]`).first().waitFor();
  // Collapse the rail to icons: at this width a full rail is a third of the frame.
  await tap(page, page.getByRole('button', { name: 'Toggle navigation' }), 200);
  await wait(page, 700);
  markNow('head');
  console.log('   HEAD', MARKS.head + 's');

  await lab(page, 'A speaking coach that runs entirely on one laptop. <em>Every voice you hear is synthetic</em>');
  await hold(page, 'intro', 3000);
  if (FULL) {
    await lab(page, `${await distinct('/scenarios/')} scenarios. Each names the grammar it is built to draw out of you`);
    await wait(page, 2400);
  }
  await lab(page, '');
  await tap(page, page.locator(`a[href="/scenarios/${SCENARIO}"]`).first(), 400);

  // ── B · the brief ─────────────────────────────────────────────────────
  await page.getByText('Your goal').waitFor();
  await wait(page, 600);
  await lab(page, 'A goal, a persona who pushes back, and the forms the scene should elicit');
  if (FULL) await hold(page, 'brief', 2800);
  else await wait(page, 1500);
  await lab(page, '');
  await tap(page, page.getByRole('button', { name: /start/i }), 400);
  console.log('B done', at());

  // ── C · the conversation ──────────────────────────────────────────────
  await page.waitForURL(/\/sessions\/\d+/);
  const sessionId = Number(/\/sessions\/(\d+)/.exec(page.url())[1]);
  MARKS.session = sessionId;
  await page.getByRole('button', { name: /Hold to speak|Playing the reply/ }).waitFor();
  if (FULL) {
    // The opening line does not play by itself, so the take presses play as a person
    // would. It is heard, not talked over: it is the first thing the persona says.
    await lab(page, 'The persona opens, out loud. Its voice is Piper, running on the CPU');
    await tap(page, page.getByRole('button', { name: /^Play\b/ }).first(), 400);
    await hearReply(page, REPLY_MS);
    await hold(page, 'persona', 1000);
  } else {
    await lab(page, 'The persona opens the scene, in character');
    await wait(page, 1800);
  }
  await lab(page, 'The learner is <em>a synthetic voice</em> reading lines written for this take, replayed into the microphone input');
  await hold(page, 'learner', 3200);
  await lab(page, '');

  const timingLine = () => page.getByText(/^last turn/);
  let seen = '';
  const replied = async () => {
    await page.waitForFunction((prev) => {
      const m = document.body.innerText.match(/last turn [\d.]+s[^\n]*/);
      return !!m && m[0] !== prev;
    }, seen, { timeout: 240000 });
    seen = await timingLine().innerText();
    await page.getByRole('button', { name: /^Pause/ }).last().waitFor({ timeout: 30000 }).catch(() => {});
  };

  await speak(page, CLIPS[0], {
    mark: 'turn1',
    during: 'Hold to speak. The waveform is the real input level',
    after: 'Whisper hears it, gemma3:4b answers in character, Piper says it. Nothing leaves this laptop',
    sayAfter: 'pipeline',
    until: replied,
  });
  await hearReply(page, REPLY_MS);
  if (FULL) {
    await lab(page, 'The app prints its own timing on every turn: heard, thought, spoke');
    await show(page, timingLine(), 600);
    await hold(page, 'timing', 3200);
  }
  await lab(page, '');
  await clock(page, 'hide');

  if (FULL && CLIPS[1]) {
    await lab(page, 'The persona never corrects you mid-conversation. That is deliberate: the report does');
    await hold(page, 'no_interrupt', 2800);
    await lab(page, '');
    await speak(page, CLIPS[1], { mark: 'turn2', until: replied });
    await hearReply(page, REPLY_MS);
    await clock(page, 'hide');
  }
  console.log('C done', at());

  // ── D · the report, and the corrections on the transcript ─────────────
  await lab(page, 'Ending runs the analysis: fluency arithmetic, a dependency parse, and a checked list of corrections');
  await wait(page, 600);
  const endButton = page.getByRole('button', { name: /End and get a report/ });
  await tap(page, endButton, 500);
  await clock(page, 'start');
  const endStarted = Date.now();
  markNow('end_click');
  const reporting = narrate('report');
  await page.getByText('Session report').waitFor({ timeout: 240000 });
  await clock(page, 'stop');
  MARKS.report_ms = Date.now() - endStarted;
  markNow('report');
  console.log(`   report in ${MARKS.report_ms} ms`);
  await reporting;
  await wait(page, 400);
  await lab(page, '');
  await clock(page, 'hide');

  const firstMine = page.getByText('You', { exact: true }).first();
  await show(page, firstMine, 1000);
  const marked = page.locator('mark');
  const nMarked = await marked.count();
  MARKS.marks = nMarked;
  if (nMarked > 0) {
    // Centred, so the marked words sit clear of the sticky header with their corrections below.
    await marked.first().evaluate((el) => el.scrollIntoView({ block: 'center', behavior: 'smooth' }));
    await wait(page, 700);
    await lab(page, 'Each correction is marked on the words it was about, and listed under the turn');
    await hold(page, 'marks', 3400);
    await poster(page, path.join(OUT, `${NAME}-poster.png`));
    await wait(page, 1200);
    if (FULL && await page.getByText('may be a mishearing').count()) {
      await lab(page, 'A correction on words the recogniser was unsure of is <em>shown, and not counted</em>');
      await hold(page, 'mishearing', 3400);
    }
  } else {
    await lab(page, 'Nothing was flagged in that turn — and the report says so rather than inventing one');
    await hold(page, 'no_marks', 3000);
    await poster(page, path.join(OUT, `${NAME}-poster.png`));
  }
  await lab(page, '');

  await show(page, page.getByText('Counted from this session'), 900);
  await lab(page, 'Counted figures sit apart from the model\'s prose, under headings that say which is which');
  await hold(page, 'figures', 3400);
  await lab(page, '');
  if (FULL) {
    await show(page, page.getByText('Written by the language model'), 900);
    await wait(page, 1800);
    await show(page, page.getByText('Not measured yet'), 900);
    await lab(page, 'What has no analyser yet is listed, not omitted');
    await hold(page, 'unmeasured', 3000);
    await lab(page, '');
  }
  console.log('D done', at());

  // ── D2 · the grammar page: the same corrections, gathered ─────────────
  if (FULL) {
    await tap(page, rail('/grammar'), 300);
    await page.getByRole('heading', { name: 'Grammar' }).first().waitFor();
    await wait(page, 900);
    const sayAgain = page.getByRole('link', { name: /Say it again/ });
    if (await sayAgain.count()) {
      await show(page, sayAgain.first(), 900);
      await lab(page, 'Every correction, in the sentence it was said in, and any of them can be <em>said again</em>');
      await hold(page, 'grammar', 3400);
    } else {
      await lab(page, 'Corrections gather here by kind, in your own sentences. This take left none to say again');
      await wait(page, 3400);
    }
    await lab(page, '');
    console.log('D2 done', at());
  }

  // ── E · read aloud ────────────────────────────────────────────────────
  if (FULL) {
    await tap(page, rail('/read'), 300);
    await page.locator(`a[href="/read/${PASSAGE}"]`).first().waitFor();
    await wait(page, 700);
    await lab(page, `${await distinct('/read/')} passages, each built to force one group of sounds`);
    await wait(page, 2400);
    await lab(page, '');
    await tap(page, page.locator(`a[href="/read/${PASSAGE}"]`).first(), 400);
    await page.getByText('Read this aloud').waitFor();
    await wait(page, 600);
    await lab(page, 'One vowel contrast, again and again: <em>ship</em> against <em>sheep</em>, <em>fill</em> against <em>feel</em>');
    await hold(page, 'reading_intro', 3200);
    await lab(page, 'The reading is the synthetic voice too: it shows the pipeline, not how an accent scores');
    await wait(page, 2400);

    await speak(page, READING, {
      mark: 'reading',
      during: 'Scoring is forced alignment and goodness of pronunciation, sound by sound, on the CPU',
      sayDuring: 'reading_during',
      after: 'Whisper checks the words first; wav2vec2 then scores every sound against the one the text asked for',
      sayAfter: 'reading_check',
      until: async () => { await page.getByText('What was heard').waitFor({ timeout: 240000 }); },
    });
    await wait(page, 600);
    await lab(page, '');
    await show(page, page.getByText('What was heard'), 900);
    await lab(page, 'Word error rate against the text comes first: a reading of the wrong passage would make the sound scores meaningless');
    await wait(page, 3600);
    await lab(page, '');
    await clock(page, 'hide');
    await show(page, page.getByText('Sounds worth practising'), 900);
    await lab(page, 'The weakest sounds in <em>this reading</em>, relative to your own median. Never a pass mark');
    await hold(page, 'reading_result', 3600);
    await lab(page, '');
    console.log('E done', at());
  }

  // ── E2 · make your point ──────────────────────────────────────────────
  if (FULL) {
    await tap(page, rail('/answers'), 300);
    const promptLink = page.locator(`a[href="/answers/${PROMPT}"]`).first();
    await promptLink.waitFor();
    await wait(page, 700);
    await lab(page, 'Make your point: a work question, answered out loud in one go');
    await hold(page, 'answer_intro', 2600);
    await lab(page, '');
    await tap(page, promptLink, 400);
    const startAnswer = page.getByRole('button', { name: 'Start answering' });
    await startAnswer.waitFor();
    await wait(page, 900);

    // Pressed to start and pressed to stop, not held: the clip plays from the first press.
    await page.evaluate((c) => { window.__clip = c; }, ANSWER);
    await tap(page, startAnswer, 400);
    markNow('answer_start');
    await page.waitForFunction(() => window.__clipMs > 0, null, { timeout: 15000 });
    const answerMs = await page.evaluate(() => { const v = window.__clipMs; window.__clipMs = 0; return v; });
    await lab(page, 'The same synthetic voice, with a filler and a phrase said twice written into the answer');
    // The filler and the repeat are in the first sentence, and are heard before the line.
    const lead = Math.min(7000, answerMs / 3);
    await wait(page, lead);
    const noting = narrate('answer_during');
    await wait(page, answerMs + 350 - lead);
    await page.evaluate(() => { window.__clip = null; });
    await lab(page, '');
    await tap(page, page.getByRole('button', { name: /^Stop/ }), 250);
    await clock(page, 'start');
    const answerStarted = Date.now();
    const counting = noting.then(() => narrate('answer_count'));
    // The result's own heading, by role and exact name: the line shown while the answer is
    // being counted also says "how you built it", and matching it stopped the clock at 0.0 s.
    const built = page.getByRole('heading', { name: 'How you built it', exact: true });
    await built.waitFor({ timeout: 240000 });
    await clock(page, 'stop');
    MARKS.answer_ms = Date.now() - answerStarted;
    markNow('answer');
    console.log(`   answer: clip ${answerMs} ms, counted and answered in ${MARKS.answer_ms} ms`);
    await counting;
    await wait(page, 600);
    await show(page, page.getByRole('heading', { name: 'How you said it', exact: true }), 900);
    await lab(page, 'How it was said and how it was built, both counted by code: fillers, repeats, reasons, examples');
    await wait(page, 3600);
    await clock(page, 'hide');
    await show(page, page.getByRole('heading', { name: 'What a language model made of it', exact: true }), 900);
    await lab(page, 'The model\'s shorter version is withheld if it brings in words the speaker never said');
    await hold(page, 'answer_model', 3600);
    await lab(page, '');
    console.log('E2 done', at());

    // ── F · progress, honest about a sample of one ──────────────────────
    await tap(page, rail('/progress'), 300);
    await page.getByText('Your progress').waitFor();
    await wait(page, 1200);
    await lab(page, 'Below the sample floor it says so, instead of drawing a line through one point');
    await hold(page, 'progress', 3400);
    await lab(page, '');
  }

  // ── G · home, where every figure is counted ───────────────────────────
  await tap(page, rail('/home'), 300);
  await page.getByText(/Your practice|Start here/).waitFor();
  await wait(page, 1000);
  await lab(page, 'Every figure on this page is counted from stored turns. Nothing is estimated');
  await hold(page, 'close', 3200);
  await lab(page, '');
  await wait(page, 1500);
  markNow('end');
  console.log('G done', at());

  await page.close();
  await context.close();
  await browser.close();

  const f = fs.readdirSync(OUT).find((x) => x.endsWith('.webm'));
  const final = path.join(OUT, `${NAME}.webm`);
  fs.renameSync(path.join(OUT, f), final);

  // Before cleanup: the replies belong to the sessions it deletes.
  await collectSounds(account.cookie);

  if (!KEEP) {
    console.log('cleanup:');
    MARKS.deleted = await cleanup(account.cookie);
  } else {
    console.log('KEEP=1 — sessions left in place on', account.email);
  }

  MARKS.cut = CUT;
  MARKS.format = FORMAT;
  MARKS.size = { w: W, h: H };
  MARKS.deliver = { w: OUT_W, h: OUT_H };
  MARKS.account = account.email;
  MARKS.wallclock = Number(at());
  MARKS.sounds = SOUNDS;
  fs.writeFileSync(path.join(OUT, `${NAME}.meta.json`), JSON.stringify(MARKS, null, 2));

  const rel = path.relative(__dirname, OUT);
  console.log('VIDEO:', final, (fs.statSync(final).size / 1e6).toFixed(1) + ' MB', 'wallclock', at() + 's');
  console.log('SOUNDS:', ['narration', 'learner', 'reply']
    .map((k) => `${SOUNDS.filter((s) => s.kind === k).length} ${k}`).join(', '));
  console.log(`NEXT:  node mix.cjs ${rel}/${NAME}.meta.json`);
  console.log(
    `       SS=${MARKS.head} SCALE=${OUT_W}:${OUT_H} POSTER=${NAME}-poster.png ` +
    `AUDIO=${NAME}.mix.wav ./to-mp4.sh ${rel}/${NAME}.webm`);
})().catch((e) => { console.error('FAILED:', e.message); process.exit(1); });
