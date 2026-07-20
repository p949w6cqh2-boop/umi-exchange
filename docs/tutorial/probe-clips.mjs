// Contact-sheet probe: true duration + first/last frame PNG per clip, using a
// <video> element in Chromium (no ffmpeg on this box). Frames land in
// out/frames/ (inside the gitignored out/). Read-only over the clips.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.join(HERE, "out");
const FRAMES = path.join(OUT, "frames");
fs.mkdirSync(FRAMES, { recursive: true });

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
const rows = [];

for (const aspect of ["16x9", "9x16"]) {
  const dir = path.join(OUT, aspect);
  for (const f of fs.readdirSync(dir).filter((x) => x.endsWith(".webm")).sort()) {
    // about:blank pages can't load file:// media in Chromium — the runner
    // serves out/ on 8765 (see run command in header) and we probe over http.
    const url = `http://127.0.0.1:8765/${aspect}/${f}`;
    await page.setContent(
      `<body style="margin:0;background:#000"><video id="v" muted preload="auto" src="${url}" style="max-width:100%;max-height:100vh"></video></body>`,
    );
    // Own medicine: everything a media element does gets a deadline.
    const dur = await page.evaluate(
      () =>
        new Promise((res) => {
          const v = document.getElementById("v");
          const bail = setTimeout(() => res(-1), 10_000);
          const settle = () => {
            if (v.duration && v.duration !== Infinity) {
              clearTimeout(bail);
              res(v.duration);
            } else if (v.readyState >= 1) {
              v.currentTime = 1e9; // MediaRecorder webm: duration appears after far-seek
              v.addEventListener(
                "seeked",
                () => {
                  clearTimeout(bail);
                  res(v.duration);
                },
                { once: true },
              );
            }
          };
          v.addEventListener("loadedmetadata", settle, { once: true });
          v.load();
          if (v.readyState >= 1) settle();
        }),
      { timeout: 15_000 },
    ).catch(() => -1);
    if (dur === -1) console.log(`  (metadata timeout on ${f} — duration falls back to rig elapsed)`);
    const seekShot = async (t, tag) => {
      await page
        .evaluate(
          (tt) =>
            new Promise((res) => {
              const v = document.getElementById("v");
              const bail = setTimeout(res, 8_000);
              v.addEventListener(
                "seeked",
                () => {
                  clearTimeout(bail);
                  setTimeout(res, 150);
                },
                { once: true },
              );
              v.currentTime = tt;
            }),
          t,
        )
        .catch(() => {});
      await page.locator("#v").screenshot({ path: path.join(FRAMES, `${aspect}-${f.replace(".webm", "")}-${tag}.png`), timeout: 8000 }).catch(() => {});
    };
    await seekShot(0.4, "first");
    if (dur > 0) await seekShot(Math.max(0.5, dur - 0.4), "last");
    const secs = dur > 0 ? Number(dur.toFixed(1)) : null;
    rows.push({ aspect, clip: f, seconds: secs, kb: Math.round(fs.statSync(path.join(dir, f)).size / 1024) });
    console.log(`${aspect}/${f}: ${secs ?? "n/a"}s ${Math.round(fs.statSync(path.join(dir, f)).size / 1024)}KB`);
  }
}
fs.writeFileSync(path.join(FRAMES, "probe.json"), JSON.stringify(rows, null, 2));
await browser.close();
