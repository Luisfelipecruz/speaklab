// Renders what the app reports while it starts: each process, the first launch's download,
// and anything that needs the person, in words. It reads and writes nothing else.

const STATES = {
  waiting: "waiting",
  starting: "starting…",
  ready: "ready",
  done: "done",
  restarting: "starting again…",
  failed: "failed",
  stopping: "stopping…",
  stopped: "stopped",
};

const $ = (id) => document.getElementById(id);

function megabytes(bytes) {
  return bytes >= 1e9 ? `${(bytes / 1e9).toFixed(2)} GB` : `${Math.round(bytes / 1e6)} MB`;
}

function render(view) {
  const { phase, units = {}, download, problem, notice } = view;
  $("title").textContent =
    phase === "problem" ? problem.title
    : phase === "downloading" ? "Getting SpeakLab ready"
    : phase === "running" ? "SpeakLab is running"
    : "Starting SpeakLab…";
  $("message").textContent =
    phase === "problem" ? problem.body
    : phase === "downloading" ? "The first launch downloads the speech models, once. Everything after this works offline."
    : phase === "running" ? (notice ?? "")
    : "";

  $("download").hidden = !download;
  if (download) {
    const share = download.total > 0 ? download.done / download.total : 0;
    $("bar-fill").style.width = `${(share * 100).toFixed(1)}%`;
    $("download-text").textContent = `${megabytes(download.done)} of ${megabytes(download.total)}${download.file ? ` · ${download.file}` : ""}`;
  }

  const list = $("units");
  list.replaceChildren(
    ...Object.entries(units).map(([name, unit]) => {
      const item = document.createElement("li");
      const label = document.createElement("span");
      label.textContent = unit.label ?? name;
      const state = document.createElement("span");
      state.className = `state ${unit.state}`;
      state.textContent = unit.detail && unit.state !== "ready" ? `${STATES[unit.state] ?? unit.state}: ${unit.detail}` : (STATES[unit.state] ?? unit.state);
      item.append(label, state);
      return item;
    }),
  );
  // Only while starting: a problem says what failed in its own words, once.
  list.hidden = phase !== "starting" || Object.keys(units).length === 0;

  const needsPerson = phase === "problem" || (phase === "running" && Boolean(notice));
  $("actions").hidden = !needsPerson;
  $("retry").textContent = phase === "running" ? "Check again" : "Try again";
  $("close").hidden = phase !== "running";
  $("quit").hidden = phase === "running";
}

window.speaklab.onStatus(render);
for (const action of ["retry", "logs", "close", "quit"]) {
  $(action).addEventListener("click", () => window.speaklab.act(action));
}
