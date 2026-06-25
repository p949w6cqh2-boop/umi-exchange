# Visual Direction — "Community Hub" (Direction D)

> Status: **DESIGN ONLY — awaiting founder approval.** No view/template/CSS changes yet.
> Branch `design/community-hub-direction`. Evolves the shipped "Parish Hall" look
> (see `docs/ui-polish-spec.md`, `static/css/input.css`, `templates/base.html`) toward a warmer,
> livelier **town-square / wellspring** feel — entirely through the existing `--umi-*` tokens, so it
> stays theming-safe and light-only.

## The idea in one line
A warm digital **town well** people gather around: cream paper, **water-teal** as the gathering color,
**soft gold** kept as the warm accent so it reads *parish*, not generic-SaaS. Alive and inviting, but
calm and dignified. Human, never corporate, never churchy.

## How this stays theming-safe (read first)
`templates/base.html` injects every color as a `--umi-*` **default** (`{{ umi_theme.x|default:"…" }}`).
Direction D **only changes those default hex values** — it adds no hardcoded colors to components and
forks no new classes. Per-community theming keeps working: a community that sets its own `primary`
still overrides teal. So this doc is a palette re-tint, nothing structural.

## Reconciled `--umi-*` palette (current → Direction D)
Contrast measured against `--umi-bg` cream `#FDFBF7` (WCAG AA: 4.5 normal text / 3.0 large).

| token | current | Direction D | on cream | change? |
|---|---|---|---|---|
| `--umi-primary` | `#2B5E2B` green | **`#0F6B73`** water-teal | **6.03:1** (AA + headroom) | ✅ shift to teal |
| `--umi-primary-hover` | `#244F24` | **`#0B585F`** deeper teal | 7.6:1 | ✅ |
| `--umi-accent` | `#C49A3C` gold | **`#C49A3C`** (unchanged) | 2.5:1 (decorative only) | ⛔ **keep gold** |
| `--umi-bg` | `#FDFBF7` paper | unchanged | — | ⛔ keep cream |
| `--umi-bg-soft` | `#F5F0E8` cream | unchanged (see Open Q2) | — | ⛔ keep warm |
| `--umi-card` | `#FAF7F1` | unchanged | — | ⛔ keep warm |
| `--umi-border` | `#E6DED5` | unchanged | — | ⛔ keep warm |
| `--umi-text` | `#2C2A29` warm brown | unchanged | 13.6:1 | ⛔ keep warm-brown ink |
| `--umi-text-soft` | `#6B6358` | unchanged | 4.7:1 | ⛔ keep |
| `--umi-need-accent` | green (=primary) | **`#0F6B73`** teal (follows primary) | — | ✅ need rail → teal |
| `--umi-offer-accent` | `#C49A3C` gold | **`#C49A3C`** (unchanged) | — | ⛔ offer rail stays gold |

**Net:** three values change (`primary`, `primary-hover`, `need-accent` → teal). Everything warm —
paper, card, border, ink, **and the gold accent** — stays. White text on the teal button is 6.23:1
(AA pass). The teal is intentionally pitched near the current green's perceived weight so it's a calm
drop-in, not a jarring rebrand.

## Type pairing (keep — it already fits)
Retain **Lora** (serif display, Georgia fallback, no external webfont) for headings and **Open Sans**
for body. This pairing is already warm and humane — exactly the "dignified, not corporate, not
churchy" register Direction D wants. The only move: let headings **breathe more** (slightly larger
display size + line-height on the hub's primary heading) to feel like a noticeboard masthead rather
than an app title. No new fonts.

## Density & spacing — medium-low (the "breathing room" pass)
- Generous vertical rhythm between feed cards and sections; nothing cramped; clear hierarchy.
- **One obvious primary action** per screen — a single teal **"Post an ask"** pill, never competing
  with secondary actions.
- Card-based, glanceable bulletin feed (the existing accent-rail cards), big friendly touch targets
  (keep the ≥44px minimum already in base). No dense data tables anywhere.
- Mobile-first; calm motion only (gentle fades), `prefers-reduced-motion` respected (already wired
  via `animations.css`).

## Per-component notes
- **Header** — keep the translucent blurred cream bar. Wordmark in warm ink; the primary CTA becomes
  a **teal "Post an ask"** pill. Gold appears only as an accent (e.g. a verified badge), never as a
  second CTA — one obvious action.
- **Feed cards** — keep the bulletin card + left **accent rail**: **need = teal rail**, **offer = gold
  rail** (this is what preserves the parish duotone while the primary shifts to teal). A touch more
  padding and inter-card spacing; soft shadow lift on hover (fade only).
- **Primary button** — teal fill `#0F6B73`, white label (6.23:1), pill shape, hover `#0B585F`. This is
  the wellspring action; it should feel inviting and unmistakable.
- **Empty state** — warm and welcoming, not a void: centered, `--umi-text-soft`, inviting microcopy
  ("Be the first to share an ask"), calm. Optional later: a simple line motif (well / noticeboard) —
  no asset needed now.

## Open color questions (for the founder)
1. **Teal depth & hue** — all three clear AA on cream with headroom (contrast = on-cream / white-on-teal):
   - **`#0F6B73`** — lively mid water-teal, **6.0 / 6.2**. *Recommended:* most "town square," brightest.
   - **`#1B5E5E`** — deep balanced teal (slightly bluer), **7.2 / 7.5**. Calm, dignified.
   - **`#0E5F66`** — deep green-teal, **7.1 / 7.4**. Closest drop-in for the current green's weight.
   (`#1B5E5E` was the parallel proposal from a second design pass; folded in here so you see one spectrum.)
2. **Cool tint on the soft surfaces?** Keep `--umi-bg-soft`/`--umi-card`/`--umi-border` fully warm
   (recommended — protects the cream-not-sterile feel), or give them a *barely-there* cool tint
   (e.g. border `#DDE6E2`) to lean further into "water"? Risk: the brief's "sterile white" warning.

## Scope / constraints honored
Design only — no code, no templates, no migrations. Light theme only (no dark surface introduced).
All colors expressed as `--umi-*` defaults (theming-safe). Gold retained. **STOP here for approval**
before any build; once approved, the change is a small re-tint of the defaults in `base.html` +
`input.css` (then recompile `output.css`), and the Sign-in Hub — built on these vars — inherits it
for free.

> Note: the brief referenced brain *voice / design-direction* nodes whose paths weren't supplied. This
> draft is reconciled against the codebase tokens + `docs/ui-polish-spec.md` + the brief's mood; if
> those brain nodes exist, point me at them and I'll reconcile against them in a revision.
