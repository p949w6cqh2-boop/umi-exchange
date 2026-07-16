// Stage 8 shot runner — the Wellspring final pass, 390px-first + desktop.
// Serves the REPO ROOT so the comps load the app's real fonts (static/fonts)
// and prints (static/img/scenes). Screen 01 (/protocol/) shipped real in S1 and
// was not flagged for revisit — Stage 8 covers the nine Layer C screens.
//
// Rebuild:
//   python3 -m http.server 8125 -d . &        # from the repo root
//   npm i --no-save playwright && node docs/wireframes/identity/final/shoot-final.mjs

import { chromium } from "playwright";
import { fileURLToPath } from "node:url";
import path from "node:path";

const BASE = process.env.FINAL_BASE || "http://127.0.0.1:8125/docs/wireframes/identity/final";
const OUT = path.join(path.dirname(fileURLToPath(import.meta.url)), "shots");

const MOBILE = { width: 390, height: 844 };
const DESK = { width: 1280, height: 900 };
const SHOT = { fullPage: true, animations: "disabled", timeout: 60000 };

const SCREENS = [
  { id: "02-settings-identity" },
  { id: "03-pages-manager", variants: ["empty"] },
  { id: "04-page-editor", variants: ["coordinator", "published"] },
  { id: "05-page-member-view", variants: ["draft", "hidden"] },
  { id: "06-page-anon-view" },
  { id: "07-pages-index", variants: ["anon", "coord", "empty"] },
  { id: "08-hub-personalized" },
  { id: "09-tombstone", variants: ["coord"] },
  { id: "10-queue-page-row" },
];

const browser = await chromium.launch();
let n = 0;

async function shoot(url, file, viewport) {
  const page = await browser.newPage({ viewport, deviceScaleFactor: 2 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto(url, { waitUntil: "networkidle" });
  await page.addStyleTag({ content: ".bnav{position:static}" });
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: path.join(OUT, file), ...SHOT });
  await page.close();
  n++;
}

for (const s of SCREENS) {
  const url = `${BASE}/${s.id}.html`;
  await shoot(url, `${s.id}-390.png`, MOBILE);
  await shoot(url, `${s.id}-desktop.png`, DESK);
  for (const v of s.variants || []) {
    await shoot(`${url}?v=${v}`, `${s.id}--${v}-390.png`, MOBILE);
  }
}

await browser.close();
console.log(`${n} final shots →`, OUT);
