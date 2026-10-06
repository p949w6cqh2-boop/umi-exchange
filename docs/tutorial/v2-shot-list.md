# Tutorial v2 — shot list (the rig's spec)

> STATUS: keyed by Jasiah 2026-10-06 ("1,2": script + shot list + recording run). Script and research:
> umi-brain `presence/drafts/video/tutorial-v2/` (`script.md`, `research.md`). Rig:
> `record-tutorial.mjs --set=v2`, driven by `cycle.sh` with `SET=v2`. Output: `out/v2/<aspect>/`
> (gitignored). **The August clips in `out/16x9` and `out/9x16` are never written:** approved Shorts were cut
> from them. Every name below is invented; every persona is a seeded St. Brigid's member; nothing touches
> production.

## How to run it

| Cycle | Command (from the repo root) | Records |
|---|---|---|
| Main | `SET=v2 bash docs/tutorial/cycle.sh <aspect>` | the 7 August scenes + v2-10 … v2-18, except the two below |
| Communion | `SET=v2 COMMUNION=1 bash docs/tutorial/cycle.sh <aspect> v2-16a-communion-helper,v2-16b-communion-coordinator` | v2-16a, v2-16b |
| Idle | `SET=v2 IDLE=75 bash docs/tutorial/cycle.sh <aspect> v2-19-idle` | v2-19 |

Every cycle builds a fresh scratch database, so the three never see each other's state. **The gate:** two
consecutive green passes of all three cycles, in both aspects (the v1 precedent, `04-contact-sheet.md:9-12`).

## Staged off camera (`cycle.sh`, scratch database only)

- **Main:** Joe gets the invented number 555-0144, so the reset scene shows the call-back box. Dan gets
  555-0131 and his ride offer's contact choice is set to phone, so the connect in `06-07` opens onto a number:
  every seeded offer otherwise keeps the form's default, "in the app" (`apps/offers/models.py:26`), and the
  reveal would read only "They prefer to arrange things through the community."
- **Communion only:** Aggie gets 555-0172; an ask "Communion at home on Sundays" in the Communion at home
  category; Frank volunteers directly (no standing offer); the match is moved to accepted through
  `transition_to`. This has a cycle of its own because an accepted match tops every hub feed
  (`apps/hub/selectors.py:114-161`), and the Communion chapter waits on a priest's read.

## Scenes, in recording order

| Slug | Chapter | Persona | Route | What happens on camera, in order | Strings the camera lands on | Target s |
|---|---|---|---|---|---|---|
| `01-landing` … `08-close` | Asking and offering; Run your own | visitor / nuala | as in `02-shot-list.md` | the August scene bodies, unchanged | as in `02-shot-list.md`, with today's screens: the connect reads "shared between the two of you and your coordinator" (`templates/matches/detail.html:27`) | as v1 |
| `v2-10-signup-no-email` | No email? | maura (new) | `login` → `register` → `/join/` → `/auth/verify/pending/` | Create an account → username `maura` → glide over the empty email box → password → **the eye** → confirm → Create account → hold on the code → tick → Continue | "Your recovery code" · "I have written this down or printed it." · "One more step before you can post" | 30 |
| `v2-11-vouch` | No email? | tom | `community-settings` → `member-vouch` | "Vouch for a neighbour" → `maura` → Vouch | "Vouch for a neighbour" (the app's spelling) | 12 |
| `v2-12-recovery-redeem` | No email? | signed out | `login` → `recovery-code-redeem` → `password_reset_confirm` | Have a recovery code? → `maura` + the code from v2-10 → Continue → "Your new recovery code" → tick → Set my new password → new password, **the eye** → Set Password | "Use your recovery code" · "Your new recovery code" · "Set New Password" | 30 |
| `v2-13-coordinator-reset` | Locked out? | tom | `community-settings` → `member-reset` | "Help a neighbor reset their password" → `joe` → Make a code → the code → the call-back box | "Reset code for Joe Callahan" · "You may call them back on the number saved on their account" · "(not confirmed by a code)" | 15 |
| `v2-14-intake-role` | Signing up in person | marta | `community-settings` | Grace's role picker → Intake helper → Save → back to the picker (a headless recording never shows the dropdown open) → the explanation line | "Role for Grace Okafor" · "can vouch for neighbors they have met in person" | 15 |
| `v2-15-signup-helper` | Signing up in person | grace | `member-vouch-page` → `intake-register` → `member-vouch-page` | Use the sign-up helper → `eileen`, no email → Make their account → the code → tick → Continue → ← Back to vouching → `eileen` → Vouch | "Sign up a neighbor" · "Your recovery code" · "Vouch for a neighbor" | 35 |
| `v2-16a-communion-helper` | Communion at home ⛪ | frank | `match-detail` | the accepted match, held on the contact box | "You're connected." · "Aggie Lynch" · "A coordinator can pass a message along." | 8 |
| `v2-16b-communion-coordinator` | Communion at home ⛪ | tom | `match-detail` | the same match, held on Aggie's number | "Phone: 555-0172" | 8 |
| `v2-17-activity` | Who did what | tom | `community-activity` (opened directly; settings links it at the top, beside the coordinator's broken QR) | one short scroll, newest row kept in frame | "Tom Byrne vouched for a neighbor: maura" · "Tom Byrne made a password reset code: for Joe Callahan" · "Marta Keane changed a role: Grace Okafor (member → intake)" · Grace's vouch for eileen | 15 |
| `v2-18-protocol-page` | Run your own (+ protocol video) | visitor | landing → `protocol` | glide to the footer link → `/protocol/` → slow scroll | "Built on the UMI Protocol v0.1. Build your own." · "The UMI Protocol" | 20 |
| `v2-19-idle` | Small things | nuala | `hub` | open the hub, touch nothing until the warning, glide to it, tap I'm still here | "Still there? To keep your account safe, you will be signed out in 1 minute." · "I'm still here" | 25 |

Dates on cards come from `05-board`; the eye from v2-10 and v2-12. **Not filmed:** codes by phone (switched
off), the pilot-area limit (off), legal holds, casework.

## Rules the rig enforces

- **Dependencies fail loud.** v2-11 and v2-12 need v2-10 in the same run, v2-15 needs v2-14, and v2-17 needs
  11, 13, 14 and 15 (`requires`). Run alone, they stop with a message instead of filming the wrong state.
- **No refusal on camera.** The board allows 5 sign-in POSTs a minute per IP, shared by sign-in, sign-up,
  recovery codes and set-password (`apps/accounts/ratelimit.py`). The rig counts its own and waits for room
  before any scene that makes one on camera (`authBudget`).
- **Today's screens or nothing.** The server runs with `--insecure` so static files come from the source tree,
  and the cycle refuses to record unless the served `password-toggle.js` and `idle-timeout.js` match the
  source byte for byte. (Before 10-06 the rig served a stylesheet collected 2026-08-05.)
- **Never "Print this page"** on a recovery-code screen: it opens the print dialog.
- **v2-19 never scrolls while it waits:** scrolling counts as activity (`static/js/idle-timeout.js:88-91`).

## For the Shorts (9:16 clips)

The pipeline reads `out/9x16` by default and a batch's own `rig/` folder first (umi-brain
`presence/drafts/video/pipeline/treat.py:24,208-213`). A batch that wants today's screens copies the v2 clip
into its `rig/` folder **under the same name** (`05-board.webm` …), plus a `cliptrims.json` entry derived by
the luminance rule. Clip-by-clip suitability, including the dated screens and the ⛪ hold on v2-16a/b, is in
`v2-contact-sheet.md`.
