"""Record the golden set for Say it in English, one line at a time, in a browser.

    python3 -I eval/golden/say/record.py      # then open http://127.0.0.1:8765

A page on this machine only: it records from the browser's microphone in the format the
app records (WebM with Opus, in Chrome), and this server writes each take into `audio/`
and its texts into the manifest. A line marked private goes into `manifest.local.json`,
which git ignores, as the error set's private turns do; the audio is never tracked.

Each line is something you would really write, said in your language as you would say
it: what you said, written out exactly (the reference the recogniser is scored against),
the English you would send, and what must survive into every version — names, numbers,
links, e-mails.
"""

import hashlib
import json
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
AUDIO = HERE / "audio"
PUBLIC = HERE / "manifest.json"
PRIVATE = HERE / "manifest.local.json"
PORT = 8765
MAX_BYTES = 10 * 1024 * 1024
ID = re.compile(r"^say-\d{2,3}$")


def load(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"version": 1, "items": []}


def save(path: Path, manifest: dict) -> None:
    manifest["items"].sort(key=lambda item: item["id"])
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def every_item() -> list[dict]:
    return [
        {**item, "private": private}
        for path, private in ((PUBLIC, False), (PRIVATE, True))
        for item in load(path)["items"]
    ]


def next_id() -> str:
    taken = {item["id"] for item in every_item()}
    number = 1
    while f"say-{number:02d}" in taken:
        number += 1
    return f"say-{number:02d}"


def remove(item_id: str) -> None:
    for path in (PUBLIC, PRIVATE):
        manifest = load(path)
        kept = [item for item in manifest["items"] if item["id"] != item_id]
        if len(kept) != len(manifest["items"]):
            manifest["items"] = kept
            save(path, manifest)
    for file in AUDIO.glob(f"{item_id}.*"):
        file.unlink()


def parse_multipart(body: bytes, content_type: str) -> dict[str, bytes]:
    match = re.search(r"boundary=(?:\"([^\"]+)\"|([^;]+))", content_type)
    if not match:
        raise ValueError("no boundary")
    boundary = ("--" + (match.group(1) or match.group(2))).encode()
    fields: dict[str, bytes] = {}
    for part in body.split(boundary)[1:]:
        if part.startswith(b"--"):
            break
        # Exactly the delimiter's line breaks: the audio's own last bytes may be \r or \n.
        part = part.removeprefix(b"\r\n").removesuffix(b"\r\n")
        head, _, value = part.partition(b"\r\n\r\n")
        name = re.search(rb'name="([^"]+)"', head)
        if name:
            fields[name.group(1).decode()] = value
    return fields


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: bytes, kind: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, value) -> None:
        self._send(
            status, json.dumps(value, ensure_ascii=False).encode(), "application/json"
        )

    def log_message(self, *_args) -> None:
        pass

    def do_GET(self) -> None:
        if self.path == "/":
            self._send(200, PAGE.encode(), "text/html; charset=utf-8")
        elif self.path == "/items":
            self._json(200, {"items": every_item(), "next": next_id()})
        elif self.path.startswith("/audio/"):
            file = AUDIO / Path(self.path).name
            if file.exists():
                self._send(200, file.read_bytes(), "audio/webm")
            else:
                self._json(404, {"detail": "no such take"})
        else:
            self._json(404, {"detail": "not found"})

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BYTES:
            return self._json(413, {"detail": "too large"})
        body = self.rfile.read(length)
        if self.path == "/delete":
            item_id = json.loads(body).get("id", "")
            if not ID.match(item_id):
                return self._json(422, {"detail": "bad id"})
            remove(item_id)
            return self._json(200, {"ok": True})
        if self.path != "/save":
            return self._json(404, {"detail": "not found"})
        fields = parse_multipart(body, self.headers.get("Content-Type", ""))
        meta = json.loads(fields.get("meta", b"{}"))
        audio = fields.get("audio", b"")
        if not audio:
            return self._json(422, {"detail": "no recording"})
        for field in ("said", "english"):
            if not str(meta.get(field, "")).strip():
                return self._json(422, {"detail": f"{field} is empty"})
        item_id = meta.get("id") or next_id()
        if not ID.match(item_id):
            return self._json(422, {"detail": "bad id"})
        remove(item_id)
        AUDIO.mkdir(exist_ok=True)
        file = AUDIO / f"{item_id}.webm"
        file.write_bytes(audio)
        item = {
            "id": item_id,
            "audio": f"audio/{file.name}",
            "sha256": hashlib.sha256(audio).hexdigest(),
            "seconds": round(float(meta.get("seconds") or 0), 1),
            "device": str(meta.get("device") or ""),
            "app": str(meta.get("app") or ""),
            "language": (
                meta.get("language")
                if meta.get("language") in ("es", "en", "mixed")
                else "es"
            ),
            "said": str(meta["said"]).strip(),
            "english": str(meta["english"]).strip(),
            "keep": [
                k.strip() for k in str(meta.get("keep") or "").split(",") if k.strip()
            ],
        }
        path = PRIVATE if meta.get("private") else PUBLIC
        manifest = load(path)
        manifest["items"].append(item)
        save(path, manifest)
        self._json(201, item)


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Say it in English — the golden set</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
:root { color-scheme: light dark; --fg: #1d2327; --muted: #5d676e; --line: #d8dde0; --bg: #f7f8f8; --card: #fff; --accent: #0e7c86; --warn: #a35200; }
@media (prefers-color-scheme: dark) { :root { --fg: #e8ecee; --muted: #9aa5ab; --line: #354045; --bg: #161b1d; --card: #1e2427; --accent: #4fc0c9; --warn: #e3a35c; } }
* { box-sizing: border-box; }
body { margin: 0; font: 16px/1.5 -apple-system, system-ui, sans-serif; color: var(--fg); background: var(--bg); }
main { max-width: 52rem; margin: 0 auto; padding: 24px 16px 64px; }
h1 { font-size: 1.5rem; margin: 0 0 4px; } p.lead { color: var(--muted); margin: 0 0 24px; }
section { background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 20px; margin-bottom: 20px; }
label { display: block; font-weight: 600; margin: 14px 0 4px; } label small { font-weight: 400; color: var(--muted); }
textarea, input[type=text], select { width: 100%; font: inherit; color: inherit; background: transparent; border: 1px solid var(--line); border-radius: 8px; padding: 8px 10px; }
textarea { min-height: 4.5em; resize: vertical; }
.row { display: flex; gap: 12px; flex-wrap: wrap; align-items: center; } .row > * { flex: 1 1 12rem; }
button { font: inherit; font-weight: 600; border-radius: 999px; border: 1px solid var(--line); background: transparent; color: inherit; padding: 8px 18px; cursor: pointer; }
button.primary { background: var(--accent); border-color: var(--accent); color: #fff; } button:disabled { opacity: .45; cursor: default; }
#rec[data-on] { background: #c62828; border-color: #c62828; color: #fff; }
.meter { height: 6px; border-radius: 3px; background: var(--line); overflow: hidden; flex: 0 0 8rem; } .meter i { display: block; height: 100%; width: 0; background: var(--accent); }
.status { color: var(--muted); } .warn { color: var(--warn); }
ol { padding-left: 1.4em; } li { margin: 10px 0; } li .meta { color: var(--muted); font-size: .9em; }
</style></head><body><main>
<h1>Say it in English — the golden set</h1>
<p class="lead">Thirty things you would really write, said in your language, 3 to 20 seconds each, on this Mac's own microphone. <span id="count"></span></p>
<section>
  <div class="row">
    <div><label for="app">The app it was for</label><select id="app"><option>Mail</option><option>Slack</option><option>Messages</option><option>WhatsApp</option><option>Notes</option><option>Microsoft Teams</option><option>Other</option></select></div>
    <div><label for="language">Said in</label><select id="language"><option value="es">Spanish</option><option value="mixed">Spanish with English in it</option><option value="en">English</option></select></div>
  </div>
  <label>Record <small>— click to start and to stop</small></label>
  <div class="row"><button id="rec" type="button">Record</button><div class="meter"><i id="level"></i></div><span id="time" class="status">0.0 s</span><audio id="play" controls hidden></audio></div>
  <p id="device" class="status"></p>
  <label for="said">What you said, exactly <small>— word for word, as you said it</small></label><textarea id="said"></textarea>
  <label for="english">The English you would send</label><textarea id="english"></textarea>
  <label for="keep">What must survive <small>— names, numbers, links, e-mails, comma-separated</small></label><input id="keep" type="text">
  <label><input id="private" type="checkbox"> Private: keep this line out of the repository</label>
  <div class="row" style="margin-top:16px"><button id="save" class="primary" type="button" disabled>Save this line</button><span id="note" class="status"></span></div>
</section>
<section><h2 style="font-size:1.1rem;margin:0">Saved</h2><ol id="list"></ol></section>
</main><script>
const $ = (id) => document.getElementById(id);
let recorder, chunks = [], blob, started = 0, timer, stream, ctx, editing = null;
async function refresh() {
  const { items } = await (await fetch("/items")).json();
  $("count").textContent = `${items.length} of 30 saved.`;
  $("list").replaceChildren(...items.map((it) => {
    const li = document.createElement("li");
    li.innerHTML = `<div><strong></strong> <span class="meta"></span></div><div class="said"></div><div class="meta en"></div>`;
    li.querySelector("strong").textContent = it.id;
    li.querySelector(".meta").textContent = `${it.app} · ${it.language} · ${it.seconds} s${it.private ? " · private" : ""}`;
    li.querySelector(".said").textContent = it.said;
    li.querySelector(".en").textContent = it.english;
    const audio = document.createElement("audio"); audio.controls = true; audio.src = `/${it.audio}`; li.append(audio);
    const del = document.createElement("button"); del.textContent = "Delete"; del.onclick = async () => { if (confirm(`Delete ${it.id}?`)) { await fetch("/delete", { method: "POST", body: JSON.stringify({ id: it.id }) }); refresh(); } };
    li.append(" ", del); return li;
  }));
}
function ready() { $("save").disabled = !(blob && $("said").value.trim() && $("english").value.trim()); }
["said", "english"].forEach((id) => $(id).addEventListener("input", ready));
$("rec").onclick = async () => {
  if (recorder && recorder.state === "recording") { recorder.stop(); return; }
  stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false } });
  const track = stream.getAudioTracks()[0]; $("device").textContent = `Microphone: ${track.label}`;
  ctx = new AudioContext(); const analyser = ctx.createAnalyser(); ctx.createMediaStreamSource(stream).connect(analyser);
  const data = new Uint8Array(analyser.fftSize);
  chunks = []; recorder = new MediaRecorder(stream, MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? { mimeType: "audio/webm;codecs=opus" } : {});
  recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data);
  recorder.onstop = () => {
    clearInterval(timer); stream.getTracks().forEach((t) => t.stop()); ctx.close();
    blob = new Blob(chunks, { type: recorder.mimeType }); const seconds = (performance.now() - started) / 1000;
    $("rec").removeAttribute("data-on"); $("rec").textContent = "Record again"; $("level").style.width = "0";
    $("time").textContent = `${seconds.toFixed(1)} s`; $("time").className = seconds < 3 || seconds > 20 ? "warn" : "status";
    $("play").src = URL.createObjectURL(blob); $("play").hidden = false; $("play").dataset.seconds = seconds.toFixed(1); ready();
  };
  recorder.start(); started = performance.now(); $("rec").setAttribute("data-on", ""); $("rec").textContent = "Stop";
  timer = setInterval(() => {
    analyser.getByteTimeDomainData(data); let peak = 0; for (const v of data) peak = Math.max(peak, Math.abs(v - 128));
    $("level").style.width = `${Math.min(100, peak / 1.28)}%`; $("time").textContent = `${((performance.now() - started) / 1000).toFixed(1)} s`;
  }, 100);
};
$("save").onclick = async () => {
  const form = new FormData();
  form.append("meta", JSON.stringify({ id: editing, app: $("app").value, language: $("language").value, said: $("said").value, english: $("english").value, keep: $("keep").value, private: $("private").checked, seconds: $("play").dataset.seconds, device: $("device").textContent.replace("Microphone: ", "") }));
  form.append("audio", blob, "take.webm");
  const response = await fetch("/save", { method: "POST", body: form });
  if (!response.ok) { $("note").textContent = (await response.json()).detail; return; }
  const item = await response.json(); $("note").textContent = `Saved ${item.id}.`;
  blob = null; editing = null; ["said", "english", "keep"].forEach((id) => ($(id).value = "")); $("private").checked = false; $("play").hidden = true; $("rec").textContent = "Record"; $("time").textContent = "0.0 s"; ready(); refresh();
};
refresh();
</script></body></html>
"""


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Recording page: http://127.0.0.1:{PORT}  (Ctrl+C to stop)", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
