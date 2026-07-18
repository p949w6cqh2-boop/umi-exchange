// Demo-gallery shoot + axe WCAG-AA pass (Stage-8 close-out).
//
// Boots against a seeded DEBUG=0 server (see docs/demo-walkthrough.md "Before
// the demo") and captures the walkthrough gallery at phone width, then runs
// axe-core (wcag2a/wcag2aa/wcag21aa tags) on every screen it visits — the
// gallery and the accessibility pass see the exact same pages.
//
//   python manage.py seed_demo_parish
//   DEBUG=0 python manage.py collectstatic --noinput && DEBUG=0 python manage.py runserver 8123
//   node docs/demo/shoot-demo.mjs [BASE]
//
// Writes docs/demo/NN-name.png and docs/demo/axe-report.json (+ a console table).

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { AxeBuilder } from "@axe-core/playwright";

const BASE = process.argv[2] || "http://127.0.0.1:8123";
const OUT = path.dirname(fileURLToPath(import.meta.url));
const PASSWORD = "demo-parish";
const AXE_TAGS = ["wcag2a", "wcag2aa", "wcag21aa"];

// The walkthrough, in order. `as` names the signed-in demo account (null = a
// visitor); `shot` is the gallery filename (null = axe-only screen).
const SCREENS = [
  { url: "/", as: null, shot: "01-landing" },
  { url: "/join/", as: null, shot: "02-join" },
  { url: "/hub/st-brigids/", as: "nuala", shot: "03-hub" },
  { url: "/c/st-brigids/needs/new/", as: "nuala", shot: "04-post-ask" },
  { url: "/c/st-brigids/", as: "nuala", shot: "05-board" },
  { url: "/c/st-brigids/needs/{LIFT}/", as: "nuala", shot: "06-ask-detail" },
  { url: "/c/st-brigids/matches/{PROPOSED}/", as: "nuala", shot: "07-match" },
  { url: "/c/st-brigids/matches/{ACCEPTED}/", as: "aggie", shot: "08-connected" },
  { url: "/c/st-brigids/p/", as: null, shot: "09-front-door" },
  { url: "/c/st-brigids/p/our-story/", as: null, shot: "10-page" },
  { url: "/protocol/", as: null, shot: "11-protocol" },
  // axe-only: the rest of the new Layer C surfaces, member/coordinator/admin sides.
  { url: "/c/st-brigids/p/", as: "nuala", shot: null },
  { url: "/c/st-brigids/p/our-story/", as: "nuala", shot: null },
  { url: "/c/st-brigids/p/old-bulletin/", as: "nuala", shot: null }, // tombstone
  { url: "/c/st-brigids/settings/", as: "marta", shot: null }, // identity section
  { url: "/c/st-brigids/p/manage/", as: "tom", shot: null },
  { url: "/c/st-brigids/p/manage/new/", as: "tom", shot: null },
  { url: "/c/st-brigids/p/manage/{MINISTRIES}/edit/", as: "tom", shot: null },
  { url: "/c/st-brigids/moderation/", as: "tom", shot: null },
];

// UUIDs differ per seed run. Pass them explicitly (fast path):
//   LIFT=… PROPOSED=… ACCEPTED=… MINISTRIES=… node docs/demo/shoot-demo.mjs
// or let the script walk real links to find them (an accepted match's need
// leaves the open feed, so the walk goes via the requester's own screens).
async function resolveIds(page) {
  const fromEnv = ["LIFT", "PROPOSED", "ACCEPTED", "MINISTRIES"].every((k) => process.env[k]);
  if (fromEnv) {
    return {
      LIFT: process.env.LIFT,
      PROPOSED: process.env.PROPOSED,
      ACCEPTED: process.env.ACCEPTED,
      MINISTRIES: process.env.MINISTRIES,
    };
  }
  return resolveIdsByWalking(page);
}

async function resolveIdsByWalking(page) {
  const ids = {};
  await login(page, "nuala");
  await page.goto(`${BASE}/c/st-brigids/`);
  const lift = await page.locator('a[href*="/needs/"]', { hasText: "9:30 Mass" }).first().getAttribute("href");
  ids.LIFT = lift.match(/needs\/([0-9a-f-]{36})\//)[1];
  await page.goto(`${BASE}/c/st-brigids/needs/${ids.LIFT}/`);
  const match = await page.locator('a[href*="/matches/"]').first().getAttribute("href");
  ids.PROPOSED = match.match(/matches\/([0-9a-f-]{36})\//)[1];
  await logout(page);

  await login(page, "aggie");
  await page.goto(`${BASE}/c/st-brigids/`);
  const tap = await page.locator('a[href*="/needs/"]', { hasText: "leaky kitchen faucet" }).first().getAttribute("href");
  await page.goto(`${BASE}${tap}`);
  const accepted = await page.locator('a[href*="/matches/"]').first().getAttribute("href");
  ids.ACCEPTED = accepted.match(/matches\/([0-9a-f-]{36})\//)[1];
  await logout(page);

  await login(page, "tom");
  await page.goto(`${BASE}/c/st-brigids/p/manage/`);
  const edit = await page.locator('a[href*="/manage/"][href*="/edit/"]').nth(2).getAttribute("href");
  ids.MINISTRIES = edit.match(/manage\/([0-9a-f-]{36})\/edit\//)[1];
  await logout(page);
  return ids;
}

async function login(page, username) {
  await page.goto(`${BASE}/auth/login/`);
  await page.fill('input[name="username"]', username);
  await page.fill('input[name="password"]', PASSWORD);
  await Promise.all([page.waitForLoadState("networkidle"), page.click('button[type="submit"], input[type="submit"]')]);
}

async function logout(page) {
  await page.context().clearCookies();
}

const browser = await chromium.launch();
const context = await browser.newContext({
  viewport: { width: 390, height: 844 },
  deviceScaleFactor: 2,
  reducedMotion: "reduce", // settle reveals so full-page shots never catch mid-animation
});
const page = await context.newPage();

const ids = await resolveIds(page);
const sub = (u) => u.replace(/\{(\w+)\}/g, (_, k) => ids[k]);

let currentUser = null;
const report = [];
for (const screen of SCREENS) {
  if (screen.as !== currentUser) {
    await logout(page);
    if (screen.as) await login(page, screen.as);
    currentUser = screen.as;
  }
  const url = sub(screen.url);
  const resp = await page.goto(`${BASE}${url}`, { waitUntil: "networkidle" });
  if (!resp.ok()) throw new Error(`${url} → HTTP ${resp.status()}`);
  // axe audits the page as users get it — including the fixed bottom bar.
  const axe = await new AxeBuilder({ page }).withTags(AXE_TAGS).analyze();
  if (screen.shot) {
    // The fixed thumb bar is viewport chrome; painted mid-page it would lie
    // on a fullPage capture (and cover the content beneath). Hide it for the
    // shot only, after the audit.
    await page.addStyleTag({ content: ".umi-bottomnav{display:none!important}" });
    await page.screenshot({ path: path.join(OUT, `${screen.shot}.png`), fullPage: true });
  }
  report.push({
    url,
    as: screen.as || "visitor",
    violations: axe.violations.map((v) => ({
      id: v.id,
      impact: v.impact,
      help: v.help,
      nodes: v.nodes.length,
      targets: v.nodes.slice(0, 3).map((n) => n.target.join(" ")),
    })),
  });
  const n = report.at(-1).violations.length;
  console.log(`${n === 0 ? "ok " : "!! "}${url} [${screen.as || "visitor"}] — ${n} violation(s)`);
}

fs.writeFileSync(path.join(OUT, "axe-report.json"), JSON.stringify(report, null, 2));
const total = report.reduce((s, r) => s + r.violations.length, 0);
console.log(`\naxe (${AXE_TAGS.join(",")}): ${total} violation(s) across ${report.length} screens → axe-report.json`);
await browser.close();
process.exit(total === 0 ? 0 : 2);
