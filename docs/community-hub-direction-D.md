# Visual Direction — "Community Hub" (Direction D)

> Status: **DESIGN ONLY — awaiting founder approval.** No view/template/CSS changes yet.
> Branch `design/community-hub-direction`. Evolves the shipped "Parish Hall" look
> (see `docs/ui-polish-spec.md`, `static/css/input.css`, `templates/base.html`) toward a warmer,
> livelier **town-square / wellspring** feel — entirely through the existing `--umi-*` tokens, so it
> stays theming-safe and light-only.
>
> **Scope correction (prep-feature pass, 2026-06-27):** the original draft below said this is a
> re-tint of *two* files (`base.html` + `input.css`). That undercounts. The default green palette has
> **four** sources and they must move together, or the re-tint applies only halfway (default community
> pages stay green). See **"Where the default green actually lives"** and **Open questions 3 & 4**,
> which raise two real decisions the first draft didn't surface.

## Decisions (founder, 2026-06-27) — APPROVED, building
1. **Teal depth:** `#0F6B73` (lively mid water-teal). `primary-hover` → `#0B585F`.
2. **Soft surfaces:** apply a **barely-there cool tint** — `--umi-bg-soft` → `#EFF1EE`,
   `--umi-card` → `#F6F8F5`, `--umi-border` → `#DDE6E2`. `--umi-bg` stays cream `#FDFBF7`.
3. **Preset strategy: (A)** re-tint `THEMES["parish"]` itself → teal and relabel "Parish — warm teal".
4. **`parish-green` classes: (b)** migrate the ~10 template usages to the var-backed `umi-primary`
   color so they finally respect per-community theming; also re-tint `tailwind.config.js` `parish.*`
   to teal so any straggler matches.

Built via TDD (`tests/test_theming.py`): default theme renders teal, gold retained, per-community
override still wins, WCAG AA guard, and a **four-source-sync** test that fails if the fallbacks drift
from the canonical theme. Layout/type/spacing ("breathing room", masthead headings, one-CTA) is a
**separate follow-up pass** — this change is the palette foundation.

## The idea in one line
A warm digital **town well** people gather around: cream paper, **water-teal** as the gathering color,
**soft gold** kept as the warm accent so it reads *parish*, not generic-SaaS. Alive and inviting, but
calm and dignified. Human, never corporate, never churchy.

## How this stays theming-safe (read first)
Direction D **only changes default hex values** — it adds no hardcoded colors to components and forks
no new classes. Per-community theming keeps working: a community that sets its own `primary` via
`theme_custom` still overrides teal (`resolve_theme()` applies overrides last). So this is a palette
re-tint, nothing structural.

## Where the default green actually lives (prep-feature finding — read before building)
The shipped default `#2B5E2B` green is defined in **four** places, in the order that decides what a
user actually sees:

| # | Source | Role | In original draft? |
|---|--------|------|--------------------|
| 1 | `apps/communities/themes.py` → `THEMES["parish"]` | **The real default.** `resolve_theme()` fills `umi_theme.*` for every community page → wins the cascade. | ❌ missed |
| 2 | `templates/base.html` `{{ …\|default:"#2B5E2B" }}` (L12,13,20) | Fallback only when `umi_theme` is absent (non-community pages / missing key). | ✅ |
| 3 | `static/css/input.css` `:root` (L9,10,18) | CSS fallback; compiled into `output.css`. | ✅ |
| 4 | `tailwind.config.js` `parish.green` / `parish.greendark` | **Static** `parish-green`/`parish-greendark` utility classes used in ~10 templates — do **not** follow `--umi-*` at all. | ❌ missed |

**Consequence:** changing only #2 + #3 (what the draft said) leaves **default community pages green** —
`resolve_theme()` returns `THEMES["parish"]["primary"]`, so base.html's `|default` never fires — and
every `text-parish-green` class stays green regardless. **#1 and #4 must change too.** The build plan
must touch all four sources, then recompile `output.css` (never hand-edit it). See Open Qs 3 & 4 for
the two decisions this raises.

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

**Net (per source):** three token *values* change (`primary`, `primary-hover`, `need-accent` → teal;
`need-accent` follows `primary` automatically in base.html). Everything warm — paper, card, border,
ink, **and the gold accent** — stays. White text on the teal button is 6.23:1 (AA pass). The teal is
intentionally pitched near the current green's perceived weight so it's a calm drop-in, not a jarring
rebrand. **But those three values must be changed in all four sources above** (themes.py, base.html,
input.css, tailwind.config.js) — so the edit is small but spans four files, not two.

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
3. **Re-tint the "parish" preset, or add a new one?** (raised by the four-source finding) The default
   `THEMES["parish"]` is labelled *"Parish — warm green"* — making its `primary` teal makes the label
   lie. Options:
   - **(A)** Re-tint `THEMES["parish"]` → teal and relabel (e.g. "Parish — warm teal"). Simplest;
     changes what "parish" *means* for every existing community on the default.
   - **(B, recommended)** Add a new `THEMES["hub"]` (the teal palette) and flip `THEME_DEFAULT` to it,
     leaving green "parish" selectable. Non-destructive, reversible per community. *Note:* an `ocean`
     preset (teal `#146C7E`) already exists and is close — worth a look before adding another.
4. **What to do with the `parish-green` Tailwind classes** (source #4, ~10 templates)?
   - **(a)** Re-point `tailwind.config.js` `parish.green`/`greendark` → teal. Minimal; they stay a
     *static* named color (still don't follow per-community theming).
   - **(b, more correct)** Migrate those usages from `parish-green` to the var-backed `umi-primary`
     color (already defined as `var(--umi-primary, …)` in the config) so they finally respect
     per-community themes. Larger (touches ~10 templates) and fixes a latent bug: today a community on
     the `rose`/`ocean`/etc. theme still shows parish-*green* on those elements.

## Scope / constraints honored
Design only — no code, no templates, no migrations. Light theme only (no dark surface introduced).
All colors expressed as defaults (theming-safe; `theme_custom` overrides still win). Gold retained.
**STOP here for approval** before any build.

Once approved, the build is a small re-tint but spans **four sources** (not two): `themes.py`
`THEMES["parish"]`/new preset · `base.html` defaults · `input.css` `:root` · `tailwind.config.js`
`parish.*` → then **recompile** `output.css` (`npx tailwindcss@3.4.14 -i static/css/input.css -o
static/css/output.css --minify`; never hand-edit it). The Sign-in Hub — built on these vars —
inherits it for free.

**Verify gates:** `ruff check . && ruff format --check .` (covers `themes.py`) · `makemigrations
--check` (expect clean — no model change) · `pytest -q` on Postgres (incl. a new regression test that
asserts the default palette stays in sync across all four sources + a WCAG ≥ 4.5:1 primary-on-`bg`
guard) · `check --deploy` = 0 issues · visual spot-check: default feed, a `theme_custom` override
(must still win), and a non-parish preset; confirm light-only and gold intact.

> Note: the brief referenced brain *voice / design-direction* nodes whose paths weren't supplied. This
> draft is reconciled against the codebase tokens + `docs/ui-polish-spec.md` + the brief's mood; if
> those brain nodes exist, point me at them and I'll reconcile against them in a revision.
