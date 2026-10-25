// Renders an SVG into a macOS .iconset with the app's own Electron, offscreen, so that
// making the icon installs nothing: every size from 16 to 1024 points, at 1x and 2x.
// Electron's profile is kept beside the iconset rather than in ~/Library.
//   electron scripts/render-icon.mjs <icon.svg> <out.iconset>

import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";

import { app, BrowserWindow } from "electron";

const [svgPath, out] = process.argv.slice(-2);
const SIZES = [16, 32, 128, 256, 512];

app.setPath("userData", join(dirname(out), "icon-profile"));
app.dock?.hide();
// One window per size, each closed before the next: closing them is not the end of the run.
app.on("window-all-closed", () => {});
app.whenReady().then(async () => {
  const svg = readFileSync(svgPath, "utf8");
  mkdirSync(out, { recursive: true });
  const render = async (pixels) => {
    const win = new BrowserWindow({
      show: false,
      width: pixels,
      height: pixels,
      transparent: true,
      frame: false,
      webPreferences: { offscreen: true },
    });
    const page = `<html><body style="margin:0;background:transparent">${svg.replace("<svg ", `<svg width="${pixels}" height="${pixels}" `)}</body></html>`;
    await win.loadURL(`data:text/html;base64,${Buffer.from(page).toString("base64")}`);
    await new Promise((resolve) => setTimeout(resolve, 150));
    const image = await win.webContents.capturePage({ x: 0, y: 0, width: pixels, height: pixels });
    win.destroy();
    const size = image.getSize();
    return size.width === pixels ? image : image.resize({ width: pixels, height: pixels, quality: "best" });
  };
  for (const points of SIZES) {
    writeFileSync(join(out, `icon_${points}x${points}.png`), (await render(points)).toPNG());
    writeFileSync(join(out, `icon_${points}x${points}@2x.png`), (await render(points * 2)).toPNG());
  }
  app.quit();
});
