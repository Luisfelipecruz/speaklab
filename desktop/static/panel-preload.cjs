// The panel page's only bridge to the app: the state to show and the recording to start
// or stop come in; the recording, a typed text, a choice and a few actions go out, each
// checked here before it is sent. A sandboxed preload, so CommonJS and Electron's own
// modules only.
const { contextBridge, ipcRenderer } = require("electron");

const VERSIONS = ["direct", "organized", "corrected", "polished", "rough"];
const ACTIONS = ["dismiss", "open", "edit", "done", "switch", "speak", "over", "out"];

contextBridge.exposeInMainWorld("panel", {
  onState: (callback) => ipcRenderer.on("panel:state", (_event, view) => callback(view)),
  onRecord: (callback) => ipcRenderer.on("panel:record", (_event, command) => callback(command)),
  sendAudio: (bytes, mimeType, durationMs) => {
    if (bytes instanceof Uint8Array && typeof mimeType === "string" && typeof durationMs === "number") {
      ipcRenderer.send("panel:audio", bytes, mimeType, durationMs);
    }
  },
  sendText: (text) => {
    if (typeof text === "string") ipcRenderer.send("panel:text", text);
  },
  choose: (choice) => {
    if (choice && VERSIONS.includes(choice.version)) ipcRenderer.send("panel:choose", { version: choice.version, again: Boolean(choice.again) });
    else if (choice && typeof choice.edited === "string") ipcRenderer.send("panel:edited", choice.edited);
  },
  act: (action) => {
    if (ACTIONS.includes(action)) ipcRenderer.send("panel:act", action);
  },
  resize: (height) => {
    if (Number.isFinite(height)) ipcRenderer.send("panel:size", Math.round(height));
  },
});
