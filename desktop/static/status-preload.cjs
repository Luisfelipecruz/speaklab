// The status page's only bridge to the app: it receives the state and sends one of four
// actions. A sandboxed preload, so CommonJS and Electron's own modules only.
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("speaklab", {
  onStatus: (callback) => ipcRenderer.on("status", (_event, view) => callback(view)),
  act: (action) => {
    if (["retry", "logs", "quit", "close"].includes(action)) ipcRenderer.send("status-action", action);
  },
});
