// Tutorial-footage rig — Stage 3 of the founder-gated video pipeline.
//
// Drives the keyed Stage-2 shot list (docs/tutorial/02-shot-list.md) against a LOCAL
// seeded server and records one video per scene via Playwright's recordVideo.
// Deterministic and re-runnable: same fresh scratch DB in, same clips out.
//
// Run (from repo root; scratch DB only, NEVER the working db.sqlite3, NEVER production):
//   SCRATCH=/tmp/tutorial-scratch.sqlite3
//   rm -f "$SCRATCH"
//   DATABASE_URL="sqlite:///$SCRATCH" .venv/bin/python manage.py migrate --verbosity 0
//   DATABASE_URL="sqlite:///$SCRATCH" .venv/bin/python manage.py seed_demo_parish
//   DATABASE_URL="sqlite:///$SCRATCH" .venv/bin/python manage.py shell <<'PY' | grep ^export > /tmp/tutorial-ids.env
//   from apps.needs.models import Need
//   from apps.matches.models import Match
//   lift = Need.objects.get(title__contains="9:30 Mass")
//   print(f"export LIFT={lift.id}")
//   print(f"export PROPOSED={Match.objects.get(need=lift).id}")
//   PY
//   DEBUG=0 DATABASE_URL="sqlite:///$SCRATCH" .venv/bin/python manage.py collectstatic --noinput
//   DEBUG=0 DATABASE_URL="sqlite:///$SCRATCH" .venv/bin/python manage.py runserver 8123 --noreload &
//   source /tmp/tutorial-ids.env && node docs/tutorial/record-tutorial.mjs            # both aspects
//   source /tmp/tutorial-ids.env && node docs/tutorial/record-tutorial.mjs 16x9      # one aspect
//
// Output: docs/tutorial/out/<aspect>/NN-slug.webm  (gitignored — raw video never committed).
// The rig ABORTS if the scratch DB isn't fresh (S4's ask already present) so re-runs
// always start from the same state. Scene S6+S7 is one continuous take by design.

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const BASE = process.env.TUTORIAL_BASE || "http://127.0.0.1:8123";
const HERE = path.dirname(fileURLToPath(import.meta.url));
const PASSWORD = "demo-parish";
const PAD_MS = 3000; // head/tail padding per scene (Stage-2 spec)

const ASPECTS = {
  "16x9": { viewport: { width: 1280, height: 720 } },
  // Phone-first portrait pass at 639x1136 (9:16). Two things this buys, both from
  // his 2026-08-05 call ("the video is so zoomed in" / "its not very mobile friendly"):
  //   1. 1.58x more captured pixels than the old 405x720, so assembly upscales 1.69x
  //      instead of 2.67x — visibly less soft.
  //   2. Content reads SMALLER on a full-screen phone, because more CSS px map into
  //      the same 1080 output width. That is the "zoomed in" complaint directly.
  // 639 is deliberate: Tailwind's sm: breakpoint is 640, so this is the widest
  // viewport that still renders the true MOBILE layout (767 was tried and gives the
  // tablet layout — desktop nav appears).
  //
  // Do NOT try to fix the upscale with recordVideo.size: Playwright only ever scales
  // a recording DOWN to fit, never up. Setting size 1080x1920 with a 405 viewport
  // (tried 2026-08-05) composites the page into the top-left of a grey 1080x1920
  // canvas. deviceScaleFactor does not reach the video capture either.
  "9x16": { viewport: { width: 639, height: 1136 } },
};

for (const k of ["LIFT", "PROPOSED"]) {
  if (!process.env[k]) {
    console.error(`Missing env ${k} — resolve UUIDs first (see the run block in this file's header).`);
    process.exit(1);
  }
}
const IDS = { LIFT: process.env.LIFT, PROPOSED: process.env.PROPOSED };

const args = process.argv.slice(2);
const wanted = args.find((a) => !a.startsWith("--")) || "both";
const onlyScene = (args.find((a) => a.startsWith("--scene=")) || "").split("=")[1] || null;
const runAspects = wanted === "both" ? Object.keys(ASPECTS) : [wanted];
if (!runAspects.every((a) => ASPECTS[a])) {
  console.error(`Unknown aspect '${wanted}' — use 16x9, 9x16, or both. Optional: --scene=<slug>.`);
  process.exit(1);
}

// A hang is a red, and red must mean stop: every scene runs under a watchdog,
// and a dead browser fails the run immediately instead of waiting forever
// (observed failure mode: chromium died mid-scene, the await never settled).
const SCENE_TIMEOUT_MS = 75_000; // ~60s of action + login-throttle headroom
const PRELOGIN_TIMEOUT_MS = 100_000; // login alone can eat 2 throttle windows

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function withWatchdog(promise, ms, label) {
  let timer;
  const dog = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error(`WATCHDOG: ${label} exceeded ${ms / 1000}s — hang is a red`)), ms);
  });
  try {
    return await Promise.race([promise, dog]);
  } finally {
    clearTimeout(timer);
  }
}

// Human-feel helpers: the cursor glides, typing breathes, scrolling rolls.
async function glide(page, locator) {
  const box = await locator.boundingBox();
  if (!box) throw new Error("glide target has no box");
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2, { steps: 30 });
  await sleep(500);
}
async function glideClick(page, locator) {
  await glide(page, locator);
  await locator.click();
}
async function typeSlow(page, locator, text) {
  await glideClick(page, locator);
  await locator.pressSequentially(text, { delay: 70 });
}
async function roll(page, px, stepPx = 60, stepMs = 40) {
  for (let done = 0; done < px; done += stepPx) {
    await page.mouse.wheel(0, stepPx);
    await sleep(stepMs);
  }
}

async function login(page, username) {
  // Login is IP-throttled (5/min); with one shared session per persona we stay
  // under it, but keep the retry so a re-run inside the window still succeeds.
  // No networkidle anywhere near this: the hub we land on POLLS partials
  // ("Polled partials keep it breathing"), so networkidle is never guaranteed.
  for (let attempt = 1; attempt <= 4; attempt++) {
    await page.goto(`${BASE}/auth/login/`, { waitUntil: "load" });
    await typeSlow(page, page.locator('input[name="username"]'), username);
    await typeSlow(page, page.locator('input[name="password"]'), PASSWORD);
    await glideClick(page, page.locator('button[type="submit"], input[type="submit"]').first());
    await page.waitForURL((u) => !u.pathname.includes("/auth/login/"), { timeout: 10_000 }).catch(() => {});
    await sleep(700);
    if (!page.url().includes("/auth/login/")) return;
    console.log(`  login as ${username} throttled, retrying in 21s (${attempt}/4)`);
    await sleep(21000);
  }
  throw new Error(`login as ${username} failed after 4 attempts`);
}

// ── Scenes (Stage-2 spec; comments carry the beat sync) ──────────────────────
// Each scene fn gets a fresh recorded page; PAD_MS settle is applied around it.

const SCENES = [
  {
    slug: "01-landing",
    persona: "visitor",
    async run(page) {
      // Beats 0-1 (0-14s): hero → notice cards → How it works.
      await page.goto(`${BASE}/`, { waitUntil: "load" });
      await sleep(2500);
      await roll(page, 700);
      await sleep(1500);
      await roll(page, 900);
      await sleep(1500);
    },
  },
  {
    slug: "02-join",
    // /join/ is auth-gated (anonymous 302s to login), so this scene records in
    // a context that signed in OFF camera; the clip opens on the two doors.
    // Narrative order is safe — the edit orders clips, not the recording.
    persona: "nuala-precam",
    prelogin: "nuala",
    async run(page) {
      // Beat 2 (14-22s): the two doors; type a fictional code, NEVER submit.
      await page.goto(`${BASE}/join/`, { waitUntil: "load" });
      await sleep(1500);
      await typeSlow(page, page.locator('input[name="join_code"]'), "BRIGID-1928");
      await sleep(2000); // linger; no submit, ever
    },
  },
  {
    slug: "03-signin-hub",
    persona: "nuala", // the login IS this scene's opening shot
    timeoutMs: 90_000, // headroom for one throttle retry; the cycle's window guard makes even that rare
    async run(page, ctx) {
      // Beat 3 (22-32s): sign in on camera, then the hub breathes.
      await login(page, "nuala");
      ctx.sessionFor = "nuala";
      await page.goto(`${BASE}/hub/st-brigids/`, { waitUntil: "load" });
      await sleep(2500); // greeting + coordinators' line
      await roll(page, 500);
      await sleep(1500); // spotlight
      await roll(page, 600);
      await sleep(2000); // the pulse
    },
  },
  {
    slug: "04-post-ask",
    persona: "nuala",
    needsSession: true,
    async run(page) {
      // Beat 4 (32-45s): category → a line or two → post → the printed promise.
      await page.goto(`${BASE}/hub/st-brigids/`, { waitUntil: "load" });
      await glideClick(page, page.getByRole("link", { name: "Post a need" }).first());
      await page.waitForLoadState("load");
      await sleep(1000);
      await glideClick(page, page.locator('label:has(input[name="category"])', { hasText: "Groceries" }).first());
      await typeSlow(page, page.locator('input[name="title"]'), "A hand carrying groceries upstairs");
      await typeSlow(
        page,
        page.locator('textarea[name="description"]'),
        "Third floor, once a week would be a blessing.",
      );
      await sleep(800);
      await Promise.all([
        page.waitForLoadState("load"),
        glideClick(page, page.getByRole("button", { name: "Post This Need" })),
      ]);
      // Post redirects to the board; her fresh ask sits at the top. Click into
      // it — the enforced promise line lives on the requester's own ask page
      // (needs/detail.html), not on the form. Dwell there.
      await sleep(1200);
      await glideClick(page, page.getByText("A hand carrying groceries upstairs").first());
      await page.waitForLoadState("load");
      await sleep(800);
      const promise = page.getByText("Nothing about you is shared until you accept a match").first();
      await promise.scrollIntoViewIfNeeded();
      await glide(page, promise);
      await sleep(2500);
    },
  },
  {
    slug: "05-board",
    persona: "nuala",
    needsSession: true,
    async run(page) {
      // Beat 5 (45-54s): the board; cursor rests on the three spoken items.
      await page.goto(`${BASE}/c/st-brigids/`, { waitUntil: "load" });
      await sleep(1500);
      for (const text of ["9:30 Mass", "Two extra dinners most weeks", "Retired teacher, happy to tutor"]) {
        const card = page.getByText(text).first();
        await card.scrollIntoViewIfNeeded();
        await glide(page, card);
        await sleep(1200);
      }
    },
  },
  {
    slug: "06-07-ask-to-connect",
    persona: "nuala",
    needsSession: true,
    async run(page) {
      // Beats 6-7 (54-78s): ONE continuous take — the ask up close, the waiting
      // offer, the locked panel; then Accept → confirm → the reveal.
      await page.goto(`${BASE}/c/st-brigids/needs/${IDS.LIFT}/`, { waitUntil: "load" });
      await sleep(1500);
      await glide(page, page.getByText("I can drive Sunday mornings").first());
      await sleep(1200);
      const locked = page.getByText("Contact info will appear here").first();
      if (await locked.count()) {
        await locked.scrollIntoViewIfNeeded();
        await glide(page, locked);
        await sleep(1200);
      }
      await glideClick(page, page.locator(`a[href*="/matches/${IDS.PROPOSED}/"]`).first());
      await page.waitForLoadState("load");
      await sleep(1500);
      await glideClick(page, page.getByRole("button", { name: "Accept match" }));
      await sleep(800); // the confirm asks; the answer is yes
      await Promise.all([
        page.waitForLoadState("load"),
        glideClick(page, page.getByRole("button", { name: "Yes, Accept" })),
      ]);
      // The money shot: linger on the open contact panel.
      await glide(page, page.getByText("Reach out kindly and arrange the rest together").first());
      await sleep(6000);
    },
  },
  {
    slug: "08-close",
    persona: "visitor2", // fresh context: genuinely signed out
    async run(page) {
      // Beat 8 (78-90s): the landing again, down to the protocol line. Calm.
      await page.goto(`${BASE}/`, { waitUntil: "load" });
      await sleep(2000);
      await roll(page, 2400, 60, 30);
      await sleep(3000); // hold on the footer
    },
  },
];

// ── Runner ───────────────────────────────────────────────────────────────────

async function assertFreshScratchDb(browser) {
  const probe = await browser.newContext();
  const page = await probe.newPage();
  await login(page, "nuala");
  await page.goto(`${BASE}/c/st-brigids/`, { waitUntil: "load" });
  const stale = await page.getByText("A hand carrying groceries upstairs").count();
  await probe.close();
  if (stale) {
    console.error("Scratch DB is NOT fresh (S4's ask already exists). Re-seed and re-run — determinism gate.");
    process.exit(1);
  }
}

const browser = await chromium.launch();
let shuttingDown = false;
browser.on("disconnected", () => {
  if (shuttingDown) return; // our own browser.close() at normal end-of-run
  // A dead browser must be a red, never a silent wait (observed: chromium
  // died mid-scene and the pending await hung for hours).
  console.error("FATAL: browser disconnected mid-run — failing loud.");
  process.exit(1);
});
await withWatchdog(assertFreshScratchDb(browser), PRELOGIN_TIMEOUT_MS, "fresh-DB probe");

for (const aspect of runAspects) {
  const outDir = path.join(HERE, "out", aspect);
  fs.mkdirSync(outDir, { recursive: true });
  console.log(`\n── ${aspect} pass → ${outDir}`);

  // One context per persona so nuala logs in once (throttle budget), but each
  // scene gets its own page = its own video file.
  const contexts = {};
  const contextFor = async (persona) => {
    if (!contexts[persona]) {
      contexts[persona] = await browser.newContext({
        viewport: ASPECTS[aspect].viewport,
        ...(ASPECTS[aspect].deviceScaleFactor
          ? { deviceScaleFactor: ASPECTS[aspect].deviceScaleFactor }
          : {}),
        recordVideo: {
          dir: outDir,
          size: ASPECTS[aspect].videoSize || ASPECTS[aspect].viewport,
        },
        // "reduce", deliberately: under full motion a hub animation wedges the
        // headless renderer (mouse.wheel never acks, screenshots time out —
        // 2026-07-18 hang). The still-shoot uses reduce for the same reason;
        // calmer footage also keeps text legible sooner. Determinism > flourish.
        reducedMotion: "reduce",
      });
      contexts[persona]._state = {};
    }
    return contexts[persona];
  };

  const scenesToRun = onlyScene ? SCENES.filter((s) => s.slug === onlyScene) : SCENES;
  if (onlyScene && !scenesToRun.length) {
    console.error(`No scene named '${onlyScene}'. Slugs: ${SCENES.map((s) => s.slug).join(", ")}`);
    process.exit(1);
  }
  for (const [i, scene] of scenesToRun.entries()) {
    const ctx = await contextFor(scene.persona);
    // Off-camera session provisioning: S2's context always needs it, and any
    // needsSession scene needs it when S3 (the on-camera login) didn't run
    // first — e.g. --scene= repro runs. Throwaway page; its video is deleted.
    const needUser = scene.prelogin || (scene.needsSession ? "nuala" : null);
    if (needUser && ctx._state.sessionFor !== needUser) {
      const p = await ctx.newPage();
      await withWatchdog(login(p, needUser), PRELOGIN_TIMEOUT_MS, `prelogin ${needUser}`);
      const v = p.video();
      await p.close();
      fs.rmSync(await v.path(), { force: true });
      ctx._state.sessionFor = needUser;
    }
    const page = await ctx.newPage();
    if (aspect === "9x16") {
      // Same convention as the still-gallery shoot: the fixed bottom nav is
      // viewport chrome, and at phone width it z-orders OVER the fixed form
      // submit (tab links intercept the whole strip — queue-flagged as a real
      // mobile stacking bug). Hide it for portrait captures.
      await page.addInitScript(() => {
        const hide = () => {
          const s = document.createElement("style");
          s.textContent = ".umi-bottomnav{display:none!important}";
          document.documentElement.appendChild(s);
        };
        document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", hide) : hide();
      });
    }
    await sleep(PAD_MS);
    console.log(`  rec ${scene.slug} [${scene.persona}]`);
    const t0 = Date.now();
    try {
      await withWatchdog(scene.run(page, ctx._state), scene.timeoutMs || SCENE_TIMEOUT_MS, `scene ${scene.slug}`);
    } catch (err) {
      console.error(`  RED at ${scene.slug} after ${((Date.now() - t0) / 1000).toFixed(1)}s: ${err.message}`);
      try {
        await page.screenshot({ path: path.join(outDir, `${scene.slug}-FAILED.png`), timeout: 5000 });
        console.error(`  forensics: ${scene.slug}-FAILED.png`);
      } catch {}
      process.exit(1);
    }
    await sleep(PAD_MS);
    const elapsed = ((Date.now() - t0) / 1000).toFixed(1);
    const video = page.video();
    await page.close();
    // Free this persona's context (and its video encoder + memory) the moment
    // its last scene is done — three live recording contexts is how the box
    // ran out of headroom last time.
    const personaDone = !scenesToRun.slice(i + 1).some((s) => s.persona === scene.persona);
    const raw = await video.path();
    const named = path.join(outDir, `${scene.slug}.webm`);
    fs.renameSync(raw, named);
    console.log(`      → ${path.basename(named)} (${Math.round(fs.statSync(named).size / 1024)} KB, ${elapsed}s)`);
    if (personaDone) {
      await contexts[scene.persona].close();
      delete contexts[scene.persona];
    }
  }
  for (const ctx of Object.values(contexts)) await ctx.close();

  // In this aspect's pass, S4 mutated the scratch DB; the NEXT pass needs the
  // same fresh state. The runner re-seeds between passes — enforce it.
  if (runAspects.length > 1 && aspect !== runAspects.at(-1)) {
    console.log("\n  ⚠ 9x16 pass needs a FRESH scratch DB (S4 posted an ask). Re-seed, then run:");
    console.log("     node docs/tutorial/record-tutorial.mjs 9x16");
    break; // never record the second pass against a dirty DB
  }
}

shuttingDown = true;
await browser.close();
console.log("\nDone. Raw clips only — nothing committed, nothing uploaded, nothing posted.");
