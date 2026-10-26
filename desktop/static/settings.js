// Say it in English's settings: shows what the app holds and what the Mac says about the
// key, and sends every change back at once. SpeakLab changes no setting of the Mac's; the
// buttons open the pane where the person changes it.

const $ = (id) => document.getElementById(id);
let settings = null;

function radio(name, value) {
  for (const input of document.querySelectorAll(`input[name="${name}"]`)) input.checked = input.value === value;
}

function render(state) {
  settings = state.settings;
  $("enabled").checked = settings.enabled;
  radio("key", settings.key);
  radio("fromOwn", settings.fromOwn);
  radio("fromEnglish", settings.fromEnglish);
  $("save").checked = settings.save;
  $("openAtLogin").checked = settings.openAtLogin;
  const access = $("access");
  if (settings.key === "shortcuts") {
    // No helper runs without fn, so there is nothing to ask the Mac about.
    access.textContent = "not needed for ⌃⌥Space";
    access.className = "";
  } else {
    access.textContent = state.access === null ? "checking…" : state.access ? "✓ Allowed" : "Not allowed";
    access.className = state.access === null ? "" : state.access ? "granted" : "denied";
  }
  $("globe-state").textContent =
    state.globe === 0
      ? "✓ Set to Do Nothing."
      : state.globe === null
        ? "Not set on this Mac, so macOS's default applies, which acts on release."
        : "Set to something other than Do Nothing.";
}

function changed() {
  if (!settings) return;
  const picked = (name) => document.querySelector(`input[name="${name}"]:checked`)?.value;
  window.settings.save({
    ...settings,
    enabled: $("enabled").checked,
    key: picked("key") ?? settings.key,
    fromOwn: picked("fromOwn") ?? settings.fromOwn,
    fromEnglish: picked("fromEnglish") ?? settings.fromEnglish,
    save: $("save").checked,
    openAtLogin: $("openAtLogin").checked,
  });
}

window.settings.onState(render);
for (const input of document.querySelectorAll("input")) input.addEventListener("change", changed);
$("open-access").addEventListener("click", () => window.settings.open("input-monitoring"));
$("open-keyboard").addEventListener("click", () => window.settings.open("keyboard"));
