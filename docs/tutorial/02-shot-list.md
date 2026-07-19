# Tutorial video — Stage 2: shot list / click-path spec

> STATUS: DRAFT awaiting Jasiah's Stage-2 key. Each scene names its URL (+ url-name), the
> signed-in demo user, the exact clicks in order, what's on screen, target seconds, and the
> sync point into the Stage-1 script beat. Recording runs against a LOCAL seeded server on a
> throwaway scratch DB (never the repo demo DB, never production). Every scene records with
> ~3s of head and tail padding for the edit.

## Pre-stage (rig setup, OFF camera, before any recording)

1. Fresh scratch DB: migrate + `seed_demo_parish` (12/7/6/3, coordinator `tom`).
2. **Dan's yes, staged in advance:** the ride-to-9:30 match is seeded `proposed`. Before
   recording, the rig advances Dan's side (offerer acceptance) so that on camera, Nuala's
   single **Accept** click completes the pair and the contact panel opens in the same
   navigation. If the state machine turns out to be single-step accept, even simpler: her one
   click is the reveal. (Mechanics verified when the rig is built — Stage 3 gate.)
3. Resolve UUIDs (need/match ids) the same way `docs/demo/shoot-demo.mjs` does.

## Scenes (16:9 master pass; the 9:16 pass repeats the same paths at phone width)

| # | Beat(s) | URL (url-name) | User | Clicks, in order | On screen | Secs |
|---|---|---|---|---|---|---|
| S1 | 0–1 | `/` (landing) | visitor | Load. No clicks. Slow scroll: hero → the three notice cards → "How it works" rows 01–03. | "Need a hand? Lend one." · mock cards (A ride to the 9:30 Mass / Math help, Tom B. / casserole, SVdP) · the three steps | 14 |
| S2 | 2 | `/join/` (community-join) | visitor | From landing, click **Join a community**. Click into the code field, type `BRIGID-1928` (fictional), **never submit**. | The two doors (join with a code / start a board), threshold line, code field focused with a code typed | 8 |
| S3 | 3 | `/auth/login/` → `/hub/st-brigids/` (login → hub:community) | nuala | Type `nuala`, password (masked dots), **Sign in** → hub loads. Pause on greeting, slow scroll to the pulse. | "Welcome back, Nuala." + coordinators' line · one-ask spotlight · pulse ("A crib for the new baby – fulfilled", "A neighbour stepped up…") | 10 |
| S4 | 4 | `/c/st-brigids/needs/new/` (need-create) | nuala | From hub click **Post a need**. Click category **Groceries**, type title `A hand carrying groceries upstairs`, description `Third floor, once a week would be a blessing.`, leave urgency Medium, click **Post This Need** → confirmation panel. | Category pictures, plain-words urgency, the privacy caution on the area field; then the posted ask with "It's on the board… **Nothing about you is shared until you accept a match.**" | 13 |
| S5 | 5 | `/c/st-brigids/` (community-feed) | nuala | Click through to the board. Slow scroll; brief cursor rest on, in order: the 9:30 ride ask, "Two extra dinners most weeks," "Retired teacher, happy to tutor" (Patience included visible). | Asks and offers side by side; her fresh groceries ask near the top (continuity from S4) | 9 |
| S6 | 6 | `/c/st-brigids/needs/{LIFT}/` (need-detail) | nuala | Open the 9:30 ride ask (her own). No mutation — the seeded **proposed** match is already there. Cursor rests on "Neighbours already offering: I can drive Sunday mornings — Dan Murphy," then on the Matches row with its **Proposed** pill. | The ask up close; Dan's offer waiting; "Marta Keane → A ride to the 9:30 Mass… Proposed"; the locked panel: "Contact info will appear here after this match is accepted." | 9 |
| S7 | 7 | `/c/st-brigids/matches/{PROPOSED}/` (match-detail) | nuala | Click into the match. Click **Accept** (Dan's side pre-staged) → contact panel opens in the same take. Long linger on the revealed box. **Do not** click fulfilled. | The reveal: "Contact details are open below, shared between the two of you alone" + "Reach out kindly and arrange the rest together." | 15 |
| S8 | 8 | `/` (landing) | visitor (logged out) | Load landing fresh. Slow scroll to the footer, hold on "Built on the UMI Protocol." | The door the viewer will actually walk through; calm close for the disclosure + CTA | 12 |

Total ≈ 90s. S6→S7 records as **one continuous take** (the click-through IS the story); the
cut point between beats 6 and 7 happens in the edit, not the recording.

## Rules this spec bakes in (from keyed Stages 0–1)

- The connect reveal (S7) happens ON camera in a single click — the protected money shot.
- The two trust strings get deliberate dwell time: S4's posted-ask promise, S6's locked panel,
  S7's "between the two of you alone."
- All typed content is fictional and American-idiom (matches the seeded parish); the S2 join
  code is invented and never submitted; passwords appear only as masked dots.
- Nothing here touches production, posts anything, or leaves the local machine.
- Timing sync: each scene's Secs column matches its script beat's second-range; the rig tags
  each clip with scene number so Stage 5's cut-down map can reference clips by name.

## Appendix — deltas discovered at Stage 3 (recorded reality vs this spec)

S2 records as an off-camera-signed-in member (`/join/` is auth-gated for visitors; clip still
opens on the two doors). S4 continues one click past the post — board → her ask — because the
promise string lives on `needs/detail.html`, not the form. All passes record with
`reducedMotion: "reduce"` (full-motion hub animation wedges the headless renderer). The 9:16
pass hides `.umi-bottomnav` (still-gallery chrome convention; at phone width the nav z-orders
over the fixed submit — real stacking bug, flagged as a queue candidate). Full rationale:
`04-contact-sheet.md`.
