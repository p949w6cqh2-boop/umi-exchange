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
//
// Version 2 (docs/tutorial/v2-shot-list.md): `--set=v2` records the August scenes again on
// today's screens, then the coordinator and recovery scenes, into out/v2/<aspect>/ so the
// August clips (which approved Shorts were cut from) are never overwritten. Use cycle.sh with
// SET=v2, which also stages what the v2 scenes need before the camera rolls. `--scene=` takes
// a comma list; a scene that depends on an earlier one says so and fails loudly when run alone.
// The idle sign-out scene only runs when named, in its own cycle: IDLE=75 SET=v2 cycle.sh
// <aspect> v2-19-idle (the server's idle limit has to be short for the warning to appear).

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const BASE = process.env.TUTORIAL_BASE || "http://127.0.0.1:8123";
const HERE = path.dirname(fileURLToPath(import.meta.url));
// A laptop seed uses the public password; a live site's is private (rotate_demo_password).
const PASSWORD = process.env.DEMO_PASSWORD || "demo-parish";
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
// COMMUNION_MATCH is staged by cycle.sh for the v2 set only; its scenes check for it.
const IDS = { LIFT: process.env.LIFT, PROPOSED: process.env.PROPOSED, COMMUNION_MATCH: process.env.COMMUNION_MATCH };

const args = process.argv.slice(2);
const wanted = args.find((a) => !a.startsWith("--")) || "both";
const onlyScene = (args.find((a) => a.startsWith("--scene=")) || "").split("=")[1] || null;
const onlyScenes = onlyScene ? onlyScene.split(",").filter(Boolean) : null;
const SET = (args.find((a) => a.startsWith("--set=")) || "").split("=")[1] || "v1";
const runAspects = wanted === "both" ? Object.keys(ASPECTS) : [wanted];
if (!runAspects.every((a) => ASPECTS[a])) {
  console.error(`Unknown aspect '${wanted}' — use 16x9, 9x16, or both. Optional: --scene=<slug>.`);
  process.exit(1);
}
if (!["v1", "v2"].includes(SET)) {
  console.error(`Unknown set '${SET}' — use --set=v1 (default) or --set=v2.`);
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

// The board throttles sign-in steps per IP: one shared bucket of 5 POSTs a minute across
// sign-in, sign-up, recovery codes and set-password (apps/accounts/ratelimit.py). A refusal
// on camera ruins a take, so every such POST is logged here and the rig waits for room first.
const authPosts = [];
function noteAuthPost() {
  authPosts.push(Date.now());
}
async function authBudget(n) {
  for (;;) {
    const now = Date.now();
    while (authPosts.length && now - authPosts[0] > 61_000) authPosts.shift();
    if (authPosts.length + n <= 4) return;
    const wait = 61_000 - (now - authPosts[0]) + 500;
    console.log(`  sign-in budget: waiting ${Math.round(wait / 1000)}s for room under the per-minute limit`);
    await sleep(wait);
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
    await authBudget(1);
    noteAuthPost();
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
      // v2 only, so a v1 re-run stays byte-for-byte the August take: glide() moves the mouse
      // without scrolling, and at 1280x720 the contact box sits below the fold, so the August
      // 16:9 take never showed it (found 2026-10-06). Bring it into view first.
      if (SET === "v2") await page.getByText("Reach out kindly and arrange the rest together").first().scrollIntoViewIfNeeded();
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

// ── Version 2 scenes (docs/tutorial/v2-shot-list.md) ─────────────────────────
// Recorded after the August scenes in the same run. Every name typed here is invented; every
// persona is a seeded St. Brigid's member. SHARED carries what one scene hands the next (the
// recovery code a neighbor wrote down), so dependent scenes declare `requires`.

const SHARED = {};
const SETTINGS = `${BASE}/c/st-brigids/settings/`;
// Invented passwords for invented neighbors on a throwaway database; shown on camera only
// where the eye is the point of the shot.
const MAURA_PW = "Garden-gate-27";
const MAURA_PW2 = "Kettle-on-at-4";
const EILEEN_PW = "Rosary-beads-19";

// The code shown on the recovery-code page (templates/accounts/recovery_code.html carries it
// in an aria-label), read so a later scene can type it the way the neighbor would.
async function readCode(page) {
  const el = page.locator('[aria-label^="Recovery code "]').first();
  await el.waitFor();
  const code = ((await el.textContent()) || "").trim();
  if (!code) throw new Error("recovery code not found on the page");
  return code;
}

const V2_SCENES = [
  {
    slug: "v2-10-signup-no-email",
    persona: "maura", // a fresh context: genuinely signed out
    authPosts: 1, // the sign-up itself
    timeoutMs: 120_000,
    async run(page) {
      // Maura has no email. She signs up anyway, and the board hands her a paper code instead
      // (accounts/views.py RegisterView: the account and its code are made together).
      await page.goto(`${BASE}/auth/login/`, { waitUntil: "load" });
      await sleep(1200);
      await Promise.all([
        page.waitForLoadState("load"),
        glideClick(page, page.getByRole("link", { name: "Create an account" })),
      ]);
      await sleep(1200);
      await typeSlow(page, page.locator('input[name="username"]'), "maura");
      await glide(page, page.locator('input[name="email"]')); // left empty, on purpose
      await sleep(1200);
      await typeSlow(page, page.locator('input[name="password"]'), MAURA_PW);
      await glideClick(page, page.getByRole("button", { name: "Show password" }).first()); // the eye
      await sleep(1800);
      await typeSlow(page, page.locator('input[name="password_confirm"]'), MAURA_PW);
      await sleep(600);
      noteAuthPost();
      await Promise.all([
        page.waitForLoadState("load"),
        glideClick(page, page.getByRole("button", { name: "Create account" })),
      ]);
      await sleep(1500);
      SHARED.mauraCode = await readCode(page);
      await glide(page, page.locator('[aria-label^="Recovery code "]').first());
      await sleep(3500);
      const written = page.getByLabel("I have written this down or printed it.");
      await written.scrollIntoViewIfNeeded();
      await glideClick(page, written); // never "Print this page": it opens the print dialog
      await sleep(800);
      await Promise.all([page.waitForLoadState("load"), glideClick(page, page.getByRole("button", { name: "Continue" }))]);
      await sleep(1500);
      const waiting = page.getByText("One more step before you can post").first();
      await waiting.waitFor({ timeout: 10_000 });
      await glide(page, waiting);
      await sleep(3000);
    },
  },
  {
    slug: "v2-11-vouch",
    persona: "tom",
    prelogin: "tom",
    requires: ["v2-10-signup-no-email"],
    async run(page) {
      // A coordinator who has met Maura in person vouches: settings, one username. Straight to
      // the form: the top of settings shows coordinators a broken join-code QR (the QR view is
      // admin-only, apps/communities/views.py:623), a bug reported to the founder, not filmed.
      await page.goto(SETTINGS, { waitUntil: "load" });
      const form = page.locator('form[action$="/members/vouch/"]');
      await form.scrollIntoViewIfNeeded();
      await glide(page, page.getByText("Vouch for a neighbour").first());
      await sleep(1500);
      await typeSlow(page, form.locator('input[name="username"]'), "maura");
      await sleep(600);
      await Promise.all([page.waitForLoadState("load"), glideClick(page, form.getByRole("button", { name: "Vouch" }))]);
      // The vouch reloads settings at the top, beside the broken QR: back down to the form. The
      // "Vouched for maura" note is pinned to the window, so it stays in frame.
      await page.locator('form[action$="/members/vouch/"]').scrollIntoViewIfNeeded();
      await sleep(3000);
    },
  },
  {
    slug: "v2-12-recovery-redeem",
    persona: "maura-later", // signed out again: the day she forgot her password
    requires: ["v2-10-signup-no-email"],
    authPosts: 2, // the code, then the new password
    timeoutMs: 120_000,
    async run(page) {
      // The paper code gets her back in. Using it hands her a fresh one, then she chooses her
      // own new password (accounts/views.py RecoveryCodeRedeemView).
      await page.goto(`${BASE}/auth/login/`, { waitUntil: "load" });
      await sleep(1500);
      await Promise.all([
        page.waitForLoadState("load"),
        glideClick(page, page.getByRole("link", { name: "Have a recovery code?" })),
      ]);
      await sleep(1200);
      await typeSlow(page, page.locator('input[name="username"]'), "maura");
      await typeSlow(page, page.locator('input[name="code"]'), SHARED.mauraCode);
      await sleep(600);
      noteAuthPost();
      await Promise.all([page.waitForLoadState("load"), glideClick(page, page.getByRole("button", { name: "Continue" }))]);
      await sleep(1500);
      await glide(page, page.getByText("Your new recovery code").first());
      await sleep(3000);
      const written = page.getByLabel("I have written this down or printed it.");
      await written.scrollIntoViewIfNeeded();
      await glideClick(page, written);
      await sleep(600);
      await Promise.all([
        page.waitForLoadState("load"),
        glideClick(page, page.getByRole("button", { name: "Set my new password" })),
      ]);
      await sleep(1200);
      await typeSlow(page, page.locator('input[name="new_password1"]'), MAURA_PW2);
      await glideClick(page, page.getByRole("button", { name: "Show password" }).first());
      await sleep(1500);
      await typeSlow(page, page.locator('input[name="new_password2"]'), MAURA_PW2);
      await sleep(600);
      noteAuthPost();
      await Promise.all([page.waitForLoadState("load"), glideClick(page, page.getByRole("button", { name: "Set Password" }))]);
      await sleep(3000);
    },
  },
  {
    slug: "v2-13-coordinator-reset",
    persona: "tom",
    prelogin: "tom",
    async run(page) {
      // Joe is locked out. The coordinator makes a 15-minute code; Joe's saved number (staged,
      // fictional) brings up the call-back box. The coordinator never sees the password.
      // Straight to the form, past the coordinator's broken QR (see v2-11).
      await page.goto(SETTINGS, { waitUntil: "load" });
      const form = page.locator('form[action$="/members/reset/"]');
      await form.scrollIntoViewIfNeeded();
      await glide(page, page.getByText("Help a neighbor reset their password").first());
      await sleep(2000);
      await typeSlow(page, form.locator('input[name="username"]'), "joe");
      await sleep(600);
      await Promise.all([page.waitForLoadState("load"), glideClick(page, form.getByRole("button", { name: "Make a code" }))]);
      await sleep(1500);
      await glide(page, page.getByText("Reset code for").first());
      await sleep(2500);
      const callback = page.getByText("You may call them back on the number saved on their account").first();
      await callback.scrollIntoViewIfNeeded();
      await glide(page, callback);
      await sleep(3000);
    },
  },
  {
    slug: "v2-14-intake-role",
    persona: "marta",
    prelogin: "marta",
    async run(page) {
      // The admin gives Grace the narrow role: vouch and help people sign up, nothing else.
      await page.goto(SETTINGS, { waitUntil: "load" });
      await sleep(1200);
      const select = page.getByLabel("Role for Grace Okafor");
      await select.scrollIntoViewIfNeeded();
      await glide(page, select);
      await sleep(800);
      await select.selectOption("intake");
      await sleep(1200);
      const form = select.locator("xpath=ancestor::form");
      await Promise.all([page.waitForLoadState("load"), glideClick(page, form.getByRole("button", { name: "Save" }))]);
      await sleep(1800); // the "role updated" note shows for 5 s at the top
      // A headless recording never shows a native dropdown opening, so come back to the
      // picker after the save: it now reads "Intake helper".
      const saved = page.getByLabel("Role for Grace Okafor");
      await saved.scrollIntoViewIfNeeded();
      await glide(page, saved);
      await sleep(2000);
      const why = page.getByText("can vouch for neighbors they have met in person").first();
      await why.scrollIntoViewIfNeeded();
      await glide(page, why);
      await sleep(3500);
    },
  },
  {
    slug: "v2-15-signup-helper",
    persona: "grace",
    prelogin: "grace",
    requires: ["v2-14-intake-role"],
    timeoutMs: 120_000,
    async run(page) {
      // Grace, now an intake helper, signs up a neighbor met after Mass. An intake helper's door
      // in is the vouch page (intake helpers cannot open settings); Eileen has no email, so the
      // paper code comes up right there (communities/views.py IntakeRegisterView).
      await page.goto(`${BASE}/c/st-brigids/vouch/`, { waitUntil: "load" });
      await sleep(1500);
      await Promise.all([
        page.waitForLoadState("load"),
        glideClick(page, page.getByRole("link", { name: "Use the sign-up helper" }).first()),
      ]);
      await sleep(1500);
      await glide(page, page.getByText("Sign up a neighbor").first());
      await sleep(1200);
      await typeSlow(page, page.locator('input[name="username"]'), "eileen");
      await typeSlow(page, page.locator('input[name="password"]'), EILEEN_PW);
      await typeSlow(page, page.locator('input[name="password_confirm"]'), EILEEN_PW);
      await sleep(600);
      await Promise.all([
        page.waitForLoadState("load"),
        glideClick(page, page.getByRole("button", { name: "Make their account" })),
      ]);
      await sleep(1500);
      await glide(page, page.locator('[aria-label^="Recovery code "]').first());
      await sleep(3500);
      // Then Grace vouches for Eileen on the spot: they have met in person, which is the whole
      // power an intake helper holds. (The sign-up never appears on "Who did what"; the vouch does.)
      const written = page.getByLabel("I have written this down or printed it.");
      await written.scrollIntoViewIfNeeded();
      await glideClick(page, written);
      await sleep(600);
      await Promise.all([page.waitForLoadState("load"), glideClick(page, page.getByRole("button", { name: "Continue" }))]);
      await sleep(1000);
      await Promise.all([
        page.waitForLoadState("load"),
        glideClick(page, page.getByRole("link", { name: /Back to vouching/ }).first()),
      ]);
      await sleep(1200);
      await typeSlow(page, page.locator('input[name="username"]'), "eileen");
      await sleep(600);
      await Promise.all([page.waitForLoadState("load"), glideClick(page, page.getByRole("button", { name: "Vouch" }))]);
      await sleep(3000);
    },
  },
  {
    slug: "v2-16a-communion-helper",
    persona: "frank",
    prelogin: "frank",
    ownCycle: true, // its staging would top every hub feed, so it records in a cycle of its own
    async run(page) {
      // Staged off camera by cycle.sh (COMMUNION=1): Aggie asked for Communion at home, Frank
      // volunteered directly (no standing offer), and the match was accepted. Frank sees her
      // name, never her number (matches/models.py get_contact_info_for).
      if (!IDS.COMMUNION_MATCH) throw new Error("COMMUNION_MATCH missing: run through cycle.sh with SET=v2");
      await page.goto(`${BASE}/c/st-brigids/matches/${IDS.COMMUNION_MATCH}/`, { waitUntil: "load" });
      await sleep(1500);
      const note = page.getByText("A coordinator can pass a message along").first();
      await note.scrollIntoViewIfNeeded();
      await glide(page, note);
      await sleep(4000);
    },
  },
  {
    slug: "v2-16b-communion-coordinator",
    persona: "tom",
    prelogin: "tom",
    ownCycle: true,
    async run(page) {
      // The coordinator, who arranges the visit, sees the number on Aggie's account.
      if (!IDS.COMMUNION_MATCH) throw new Error("COMMUNION_MATCH missing: run through cycle.sh with SET=v2");
      await page.goto(`${BASE}/c/st-brigids/matches/${IDS.COMMUNION_MATCH}/`, { waitUntil: "load" });
      await sleep(1500);
      const phone = page.getByText("Phone:").first();
      await phone.scrollIntoViewIfNeeded();
      await glide(page, phone);
      await sleep(3500);
    },
  },
  {
    slug: "v2-17-activity",
    persona: "tom",
    prelogin: "tom",
    requires: ["v2-11-vouch", "v2-13-coordinator-reset", "v2-14-intake-role", "v2-15-signup-helper"],
    timeoutMs: 90_000,
    async run(page) {
      // Who did what: the vouches, the role change and the reset code from this run, each with
      // the name of the person who did it. Nobody can edit or delete it. Opened directly (it is
      // linked from the top of settings, beside the coordinator's broken QR; see v2-11), with
      // one short scroll so the newest row stays in frame at 1280x720.
      await page.goto(`${BASE}/c/st-brigids/activity/`, { waitUntil: "load" });
      await sleep(2500);
      await roll(page, 300);
      await sleep(4500);
    },
  },
  {
    slug: "v2-18-protocol-page",
    persona: "visitor3",
    timeoutMs: 90_000,
    async run(page) {
      // The footer's promise, followed: every board serves the protocol it is built on.
      await page.goto(`${BASE}/`, { waitUntil: "load" });
      await sleep(1200);
      const link = page.getByRole("link", { name: /Built on the UMI Protocol/ }).first();
      await link.scrollIntoViewIfNeeded();
      await glide(page, link);
      await sleep(1500);
      await Promise.all([page.waitForLoadState("load"), link.click()]);
      await sleep(2500);
      for (let i = 0; i < 4; i++) {
        await roll(page, 600, 60, 45);
        await sleep(1800);
      }
    },
  },
  {
    slug: "v2-19-idle",
    persona: "nuala",
    needsSession: true,
    ownCycle: true, // needs a server started with a short idle limit (IDLE=75 in cycle.sh)
    timeoutMs: 120_000,
    async run(page) {
      // A borrowed phone left signed in: a minute before sign-out the board asks first.
      await page.goto(`${BASE}/hub/st-brigids/`, { waitUntil: "load" });
      const ask = page.getByText("Still there?").first();
      await ask.waitFor({ timeout: 60_000 });
      await sleep(1000);
      await glide(page, ask);
      await sleep(2500);
      // The board takes any tap while the warning shows as the answer, on pointerdown
      // (static/js/idle-timeout.js touch()), so the warning is gone before a click could land
      // and Playwright's click checks retry until they time out. Press where the button is,
      // the way a hand would, then confirm the warning went.
      await glide(page, page.getByRole("button", { name: "I'm still here" }));
      await page.mouse.down();
      await page.mouse.up();
      await ask.waitFor({ state: "detached", timeout: 5000 });
      await sleep(3000);
    },
  },
];

const SETS = { v1: SCENES, v2: [...SCENES, ...V2_SCENES] };

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
  // v1 keeps its August folder; any other set records beside it, never over it.
  const outDir = path.join(HERE, "out", ...(SET === "v1" ? [] : [SET]), aspect);
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

  const pool = SETS[SET];
  // A scene marked ownCycle (the idle sign-out) needs a server started for it, so it runs
  // only when named; a full pass leaves it out.
  const scenesToRun = onlyScenes
    ? pool.filter((s) => onlyScenes.includes(s.slug))
    : pool.filter((s) => !s.ownCycle);
  const unknown = onlyScenes ? onlyScenes.filter((n) => !pool.some((s) => s.slug === n)) : [];
  if (unknown.length || (onlyScenes && !scenesToRun.length)) {
    console.error(`No scene named '${unknown.join(", ") || onlyScene}'. Slugs: ${pool.map((s) => s.slug).join(", ")}`);
    process.exit(1);
  }
  const ran = new Set();
  for (const [i, scene] of scenesToRun.entries()) {
    const missing = (scene.requires || []).filter((r) => !ran.has(r));
    if (missing.length) {
      console.error(`  ${scene.slug} needs ${missing.join(", ")} earlier in the same run; add it to --scene.`);
      process.exit(1);
    }
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
    // Room for this scene's on-camera sign-in steps, made before its recording starts.
    if (scene.authPosts) await authBudget(scene.authPosts);
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
    ran.add(scene.slug);
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
