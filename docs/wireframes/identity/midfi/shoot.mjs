// Stage 7 shot runner — greyscale mid-fi, 390px-first + desktop.
// Screens 02–10 shoot from the static mockups in this directory; screen 01 shoots the REAL
// /protocol/ page (Layer P, slice/platform-floor) from a live DEBUG=0 server and walks the
// keyed verification: footer line → /protocol/ → TOC jump.
//
// Rebuild:
//   python3 -m http.server 8124 -d docs/wireframes/identity/midfi &   # static base
//   DEBUG=0 DATABASE_URL=sqlite:///<scratch>.db3 .venv/bin/python manage.py runserver 8123 &
//   npm i --no-save playwright && node docs/wireframes/identity/midfi/shoot.mjs

import { chromium } from "playwright";
import { fileURLToPath } from "node:url";
import path from "node:path";

const STATIC = process.env.STATIC_BASE || "http://127.0.0.1:8124";
const LIVE = process.env.LIVE_BASE || "http://127.0.0.1:8123";
const OUT = path.join(path.dirname(fileURLToPath(import.meta.url)), "shots");

const MOBILE = { width: 390, height: 844 };
const DESK = { width: 1280, height: 900 };

// Variant states are the Stage-5 keyed ones — named, never improvised.
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
const shots = [];

const SHOT = { fullPage: true, animations: "disabled", timeout: 60000 };

async function shoot(url, file, viewport) {
  const page = await browser.newPage({ viewport, deviceScaleFactor: 2 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto(url, { waitUntil: "networkidle" });
  // Full-page captures smear a fixed bottom nav across the scroll; let it sit in flow.
  await page.addStyleTag({ content: ".bnav{position:static}" });
  await page.screenshot({ path: path.join(OUT, file), ...SHOT });
  await page.close();
  shots.push(file);
}

// --- 01: the real /protocol/ page + the keyed click-walk --------------------
{
  const page = await browser.newPage({ viewport: MOBILE, deviceScaleFactor: 2 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto(`${LIVE}/`, { waitUntil: "networkidle" });
  await page.locator("footer a", { hasText: "Built on the UMI Protocol" }).click();
  await page.waitForURL("**/protocol/");
  await page.screenshot({ path: path.join(OUT, "01-protocol-390.png"), ...SHOT });
  shots.push("01-protocol-390.png");

  // TOC jump: §13 — Conformance (the spec's own hand-written anchor slug).
  await page.locator('#protocol-toc a[href="#13--conformance"]').click();
  const y = await page.evaluate(() => window.scrollY);
  if (y < 500) throw new Error(`TOC jump failed: scrollY=${y}`);
  console.log(`VERIFY footer→/protocol/ OK; TOC jump OK (scrollY=${Math.round(y)})`);
  await page.close();

  const desk = await browser.newPage({ viewport: DESK, deviceScaleFactor: 2 });
  await desk.emulateMedia({ reducedMotion: "reduce" });
  await desk.goto(`${LIVE}/protocol/`, { waitUntil: "networkidle" });
  await desk.screenshot({ path: path.join(OUT, "01-protocol-desktop.png"), ...SHOT });
  shots.push("01-protocol-desktop.png");
  await desk.close();
}

// --- 02–10: static mid-fi mockups -------------------------------------------
for (const s of SCREENS) {
  const url = `${STATIC}/${s.id}.html`;
  await shoot(url, `${s.id}-390.png`, MOBILE);
  await shoot(url, `${s.id}-desktop.png`, DESK);
  for (const v of s.variants || []) {
    await shoot(`${url}?v=${v}`, `${s.id}--${v}-390.png`, MOBILE);
  }
}

await browser.close();
console.log(`${shots.length} shots →`, OUT);
