# Tutorial video — Stage 4: raw-clip contact sheet

> STATUS: delivered for Jasiah's Stage-4 watch + key. Clips are the gate's final (second
> consecutive green) run: 7 scenes × 2 aspects, `docs/tutorial/out/<aspect>/`. Durations
> probed from the files themselves; first/last frames extracted and the load-bearing ones
> eyeballed (renders, not captions). Raw = includes ~3s head/tail padding per clip; the
> edit trims to the ~90s script.

## Gate evidence (Stage 3 closed)

Two consecutive full runs × both aspects, 28 scene recordings, zero reds
(`GATE-BOTH-RUNS-GREEN`, 2026-07-19 00:09–00:23). Per-scene watchdogs armed throughout.

## The clips

| Scene | 16:9 | 9:16 | First frame | Last frame |
|---|---|---|---|---|
| 01-landing | 13.2s · 996KB | 13.0s · 615KB | Hero: "Need a hand? Lend one." | "How it works" rows in view |
| 02-join | 12.6s · 402KB | 9.4s · 198KB | The two doors | Invite-code field holding `BRIGID-1928`, unsubmitted |
| 03-signin-hub | 16.0s · 1164KB | 15.7s · 669KB | Login form, typing | The pulse (crib fulfilled, neighbour stepped up) |
| 04-post-ask | 23.2s · 1011KB | 26.2s · 649KB | Category grid | ✔ EYEBALLED: her posted ask + full promise panel ("Nothing about you is shared until you accept a match.") + locked contact box |
| 05-board | 11.5s · 614KB | 11.3s · 270KB | ✔ EYEBALLED: board with her ask on top, "2 answered · 3 hands raised this week" | Cursor resting on "Retired teacher, happy to tutor" |
| 06-07-ask-to-connect | 21.8s · 826KB | 21.9s · 496KB | The 9:30 ask up close, Dan's offer waiting | ✔ EYEBALLED both aspects: "You're connected." ceremony art + "Contact details are open below, shared between the two of you alone" + timeline Proposed → Accepted live |
| 08-close | 13.3s · 768KB | 9.7s · 457KB | Landing fresh (signed out) | Footer, "Built on the UMI Protocol" |

Raw totals: ~111.6s (16:9), ~107.2s (9:16) — pads off ≈ the 90s target.

> ⚠ **2026-08-02 annotation (rows stay verbatim — they record what was captured):** clip
> 06-07's eyeballed string "shared between the two of you alone" is the **pre-#136** page copy,
> since retracted; the live page reads "between the two of you and your coordinator." The clip
> owes a re-shoot against the corrected screen before assembly ships.

## Legibility floor (Stage-0 goal #5)

Checked on the 9:16 frames at native 405px: smallest text in frame (board meta rows,
"Nuala Doyle · 0 minutes ago") is cleanly readable; the 1080×1920 assembly upscale is a
2.67× integer-ish scale of already-legible text. PASS.

## Deviations from the keyed Stage-2 spec (all disclosed, none silent)

1. **S2 records as an off-camera-signed-in member** — `/join/` is auth-gated for visitors;
   the clip still opens on the two doors. Cut order preserves the narrative.
2. **S4 ends one click deeper** — the promise string renders on the posted ask
   (`needs/detail.html`), not on the form; the scene posts, lands on the board, clicks into
   her ask, dwells on the promise. Story got better: the ask visibly reaches the board.
3. **Reduced motion** — full-motion hub animation wedges the headless renderer; footage uses
   `reduce`, same as the still gallery. Calmer, text legible sooner.
4. **9:16 hides the bottom nav** — still-gallery convention for viewport chrome, and at phone
   width the nav z-orders over the fixed form submit (real stacking bug, queue candidate).

## Script amendment needed (your key)

Beat 4 says "there's a promise printed **right where you type**" — the promise actually
appears on the posted ask, one click later. Truthful replacement, same breath:
"and the promise is printed **right on your ask**: nothing about you is shared until you
accept a match." One phrase; everything else in the keyed script stands.

## Queue candidates surfaced by this stage (NOT queued — your call)

- Bottom-nav z-orders over the fixed "Post This Need" submit at phone width; tab links
  intercept the whole strip.
- `docs/demo-walkthrough.md` §4 wording ("printed right on the form") overstates the
  promise's location by one click.
