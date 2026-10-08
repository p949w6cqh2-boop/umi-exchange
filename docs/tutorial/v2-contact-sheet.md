# Tutorial v2 — contact sheet

> STATUS: delivered 2026-10-06 for Jasiah's watch. **The gate is closed:** the fourth gate ran two
> consecutive green passes of all three cycles in both aspects. Numbers come from those final takes via a
> probe script:
> - **Durations:** from each file's last video packet (Playwright's webm carries no duration in its header).
> - **Head trims:** the first 4-fps frame whose luminance stddev exceeds 12 once the header band is cropped
>   off.
> - **Frames:** first and last frames are extracted to `out/v2/frames/<aspect>/`, and the load-bearing ones
>   eyeballed.
>
> Spec: `v2-shot-list.md`. Script: umi-brain `presence/drafts/video/tutorial-v2/script.md`.

## Gate evidence

`GATE-BOTH-RUNS-GREEN 19:26:06`: 12 cycles, 0 reds, 2026-10-06 18:43–19:26.

| Pass | Aspect | Main (15 clips) | Communion (2) | Idle (1) |
|---|---|---|---|---|
| 1 | 16:9 | 18:43:22–18:49:44 rc=0 | 18:50:45–18:51:35 rc=0 | 18:52:36–18:53:22 rc=0 |
| 1 | 9:16 | 18:54:23–19:00:41 rc=0 | 19:01:42–19:02:30 rc=0 | 19:03:31–19:04:15 rc=0 |
| 2 | 16:9 | 19:05:16–19:11:38 rc=0 | 19:12:39–19:13:28 rc=0 | 19:14:29–19:15:14 rc=0 |
| 2 | 9:16 | 19:16:15–19:22:32 rc=0 | 19:23:33–19:24:21 rc=0 | 19:25:22–19:26:06 rc=0 |

- **36 clips** on disk: 18 per aspect, matching the shot list.
- **The August footage is untouched:** all 14 files in `out/16x9` and `out/9x16` were listed with size and
  mtime before the first dry run, listed again after the gate, and the two listings diff empty.

## The clips (final takes)

| Clip | 16:9 s | 16:9 head | 9:16 s | 9:16 head | Eyeballed | Shorts B-roll |
|---|---|---|---|---|---|---|
| `01-landing` | 9.96 | 0.0 | 13.08 | 3.25 | hero, today's look | ✅ |
| `02-join` | 12.60 | 3.25 | 12.48 | 3.25 | invite code typed, never submitted | ✅ |
| `03-signin-hub` | 18.92 | 3.0 | 15.68 | 0.0 | the hub's stream, relative times only | ✅ |
| `04-post-ask` | 26.28 | 3.25 | 26.68 | 3.25 | the promise on the posted ask | ⚠️ date on the ask |
| `05-board` | 14.84 | 3.25 | 14.84 | 3.25 | cards read "Posted Oct 6" | ⚠️ dated |
| `06-07-ask-to-connect` | 25.16 | 3.0 | 22.04 | 0.0 | ✔ "You're connected." + "Dan Murphy, Phone: 555-0131", both aspects | ⚠️ timeline dates |
| `08-close` | 13.08 | 3.0 | 12.92 | 3.0 | footer, "Built on the UMI Protocol v0.1. Build your own." | ⚠️ footer line (below) |
| `v2-10-signup-no-email` | 37.00 | 3.0 | 37.00 | 3.0 | ✔ the eye; "Your recovery code"; "One more step before you can post" | ✅ |
| `v2-11-vouch` | 15.28 | 3.25 | 15.40 | 3.25 | ✔ form + "Vouched for maura — they can now join and post." | ✅ |
| `v2-12-recovery-redeem` | 36.72 | 3.0 | 36.56 | 3.0 | ✔ "Your new recovery code" → "Password Reset Complete" | ✅ |
| `v2-13-coordinator-reset` | 18.12 | 0.0 | 21.40 | 3.25 | ✔ "Reset code for Joe Callahan" + call-back box, "555-0144 (not confirmed by a code)" | ✅ |
| `v2-14-intake-role` | 17.88 | 0.0 | 21.28 | 3.25 | ✔ "Intake helper" in Grace's picker + the explanation line | ✅ |
| `v2-15-signup-helper` | 39.00 | 3.0 | 36.00 | 0.0 | ✔ "Sign up a neighbor" → code → "Vouched for eileen" | ✅ |
| `v2-16a-communion-helper` | 12.80 | 3.25 | 12.72 | 3.25 | ✔ "Aggie Lynch" + "A coordinator can pass a message along." | ⛪ HOLD |
| `v2-16b-communion-coordinator` | 12.28 | 3.25 | 9.04 | 0.0 | ✔ "Phone: 555-0172" | ⛪ HOLD |
| `v2-17-activity` | 13.32 | 3.25 | 13.28 | 3.0 | ✔ all five rows in frame, names + "member → intake" | ⚠️ dated rows |
| `v2-18-protocol-page` | 22.20 | 3.0 | 18.84 | 0.0 | ✔ `/protocol/` §1–§3 readable | ✅ (also the protocol video) |
| `v2-19-idle` | 30.12 | 3.25 | 31.16 | 3.25 | ✔ the warning on camera 18.5–24.0 s of the final 16:9 take (0.5 s scan), gone after the press | ✅ |

**Head 0.0** means the clip opens on content: a blank page paints no frames, so some clips start at the
first paint.

**Legibility at the native 639 px:** eyeballed on the 9:16 frames. The smallest text, the settings helper
lines and the footer small print, reads cleanly, and the pipeline upscales 1.69× from there
(`presence/video-craft-log.md` §1).

**Tail check** (the 2026-08-06 open row, "menus pop up for a split second"):
- **What was measured:** the bottom 12% of each clip's last 2 s, pixels changing by more than 40 levels
  between 4-fps frames.
- **What it found:** no menu or bar appears in any clip.
  - Most hits were **one-frame encoder dips**: the frames before and after match.
  - The rest were a **softer, greyer encode of the same content** on the last frames, and one **closing
    note**: "Vouched for maura" closes on its 5 s timer.
  - **Checked by eye:** each kind, on five occurrences: four on earlier gates' takes of the same scenes, and
    one, the largest (`v2-11` 9:16, 674 px), on the final take.
  - All sit inside the 3 s tail pad.
- **The rule for the edit:** never use a clip's tail pad.

## What the dry runs and gates changed (all disclosed)

1. **Dry run 1 went red at the eye** (`v2-10`, "Show password" never appeared).
   - Cause: a `DEBUG=0` server serves the collected `staticfiles/` folder. It held the stylesheet collected
     **2026-08-05**, and none of `password-toggle.js`, `idle-timeout.js` or `recaptcha-submit.js`.
     **Every recording since August carried that August stylesheet.**
   - Fix: `runserver --insecure`, which serves static files from the source tree, plus a pre-flight check.
     It refuses to record unless both scripts match the source byte for byte.
2. **Communion moved to its own cycle.** Its staged, accepted match tops every hub feed
   (`apps/hub/selectors.py:114-161`). The chapter waits on a priest's read, so it must not ride into the core
   scenes or the Shorts.
3. **`v2-15` was extended:** Grace vouches for Eileen after signing them up. The activity page never lists a
   sign-up (`apps/audit/coordinator_activity.py:24-36`), but it does list a vouch.
4. **`v2-14` returns to the picker after saving,** because a headless recording never shows a native
   dropdown open.
5. **Sign-in budget.** The board allows 5 sign-in POSTs a minute per IP, shared across sign-in, sign-up,
   recovery and set-password (`apps/accounts/ratelimit.py`). The rig now counts its own POSTs and waits for
   room before any scene that makes one on camera.
6. **Gate 1 went red at `v2-19` (16:9).**
   - Cause: the board takes any tap while the idle warning shows as the answer, on pointerdown
     (`static/js/idle-timeout.js`, `touch()`). Playwright's click checks then retried until they timed out.
   - Fix: the scene glides to the button and presses the mouse the way a hand would.
   - Tested alone in both aspects, then the gate restarted from the first cycle.
7. **Gate 2 went green, then failed frame review.**
   - **The connect opened onto no contact.** Every seeded offer keeps the form's default contact choice, "in
     the app". Fix: staging sets Dan's ride offer to phone, with the invented number 555-0131.
   - **Coordinators' settings show a broken QR image.** The QR view answers admins only
     (`apps/communities/views.py:623`). Fix: tom's settings scenes jump straight to their forms, and `v2-17`
     opens the activity page directly with one short scroll.
8. **Gate 3 went green, then failed frame review.**
   - **The 16:9 connect never showed the contact box.** `glide()` doesn't scroll, and at 1280x720 the box
     sits below the fold. The August 16:9 take had the same gap. Fix: in the v2 set only (`SET === "v2"`) the
     box is scrolled into view, so v1 runs stay identical.
   - **The vouch reloaded at the top of settings,** beside the broken QR. Fix: the scene scrolls back to the
     form, and the note is pinned to the window so it stays in frame.
   - Gate 4 ran from the first cycle and is the one recorded above.
9. **Failed takes and their screenshots** (dry run 1, gate 1's `v2-19`) were moved to `out/v2/failed/`, not
   deleted.

## For the Shorts

- **What the B-roll pool gains:**
  - **9 new clips:** 8 clean (`v2-10` … `v2-15`, `v2-18`, `v2-19`) plus `v2-17`, whose rows are dated;
  - **the core seven, refreshed** onto today's look;
  - **2 held** for the priest's read (`v2-16a/b`).

  Until now every Short drew on 7 clips, used 190 times.
- **How a batch uses them:**
  - copy the 9:16 clip into the batch's own `rig/` folder;
  - **keep the August name for the core seven** (`05-board.webm` …), so `treat.py:208-212` picks it over the
    August default;
  - give the new ones their own names;
  - add each head trim to that batch's `cliptrims.json`.
- **Proposed `cliptrims` entries (9:16, final takes):**
  ```json
  {"01-landing": 3.25, "02-join": 3.25, "03-signin-hub": 0.0, "04-post-ask": 3.25, "05-board": 3.25,
   "06-07-ask-to-connect": 0.0, "08-close": 3.0, "v2-10-signup-no-email": 3.0, "v2-11-vouch": 3.25,
   "v2-12-recovery-redeem": 3.0, "v2-13-coordinator-reset": 3.25, "v2-14-intake-role": 3.25,
   "v2-15-signup-helper": 0.0, "v2-17-activity": 3.0, "v2-18-protocol-page": 0.0, "v2-19-idle": 3.25}
  ```
  The trims are floors, not targets. Frame-match against the approved cut when replacing a clip
  (`presence/video-craft-log.md` §9).
- **Dated screens** (marked ⚠️ above) break the evergreen rule for Shorts: "Posted Oct 6", the match
  timeline, the activity rows. Crop or skip those seconds.
- **`v2-16a/b` are held** until the priest's read of the Communion chapter.
- The scratch-database reset codes and recovery codes on screen are throwaway. Each cycle deletes its
  database, so no code shown works anywhere.

## Seen on screen that is not ours to fix here (reported to the founder, not changed)

- The footer on every page says "United Moral Infrastructure, a non-profit being established as a 501(c)(3)"
  (`templates/base.html:169`). The founder's recorded sequencing is that the 501(c)(3) is not in motion until
  the pilot runs. It shows in every clip that reaches the footer.
- Coordinators see a broken join-code QR in settings: the view is admin-only (`apps/communities/views.py:623`)
  while the page shows the QR to every coordinator (`templates/communities/settings.html:36-38`).
- On the live demo, the connect opens onto "They prefer to arrange things through the community" for every
  seeded offer (default contact choice, "in the app").
