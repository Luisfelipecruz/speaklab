// The settings page's bridge: the settings and what the Mac says about the key come in;
// a changed setting, and which pane of System Settings to open, go out.
const { contextBridge, ipcRenderer } = require("electron");

const PANES = ["input-monitoring", "keyboard"];

contextBridge.exposeInMainWorld("settings", {
  onState: (callback) => ipcRenderer.on("settings:state", (_event, state) => callback(state)),
  save: (settings) => {
    if (settings && typeof settings === "object") ipcRenderer.send("settings:save", settings);
  },
  open: (pane) => {
    if (PANES.includes(pane)) ipcRenderer.send("settings:open", pane);
  },
});
