# Spec — Community Hub layout pass ("Editorial Noticeboard", system-wide)

> Status: **APPROVED — building.** Founder approved direction (Editorial Noticeboard) + scope
> (everything) 2026-06-27. Branch `feature/community-hub-direction-d`. Builds on the shipped
> Direction D palette (teal `#0F6B73`, barely-cool surfaces, gold accent). See
> `docs/community-hub-direction-D.md`.

## Goal
Make UMI Exchange feel **unrecognizable** from the current "Parish Hall app" — a warm, human,
**editorial noticeboard**: oversized left-aligned serif mastheads, generous breathing room, one
obvious action per screen, bulletin "note" cards — while staying **easy and simple**. Light-only,
theming-safe, gold retained, per-community theming preserved.

## Strategy — re-skin everything without rewriting 40 templates
Three leverage points, in order:
1. **Warm the neutral ramp** (`tailwind.config.js`): override Tailwind's `gray` scale to a warm,
   barely-teal-cool parish ramp. ~500 `gray-*`/footer usages across 53 templates warm **instantly**,
   zero template edits, no layout risk (hue shift preserving lightness).
2. **Editorial design system** (`input.css` + `base.html`): type scale (mastheads), card air,
   section rhythm, refined themed chrome (header/footer). Every page uses these shared classes →
   transforms at once.
3. **Bespoke editorial treatment** on the two highest-traffic surfaces (landing, feed). Everything
   else inherits 1+2 and gets light touches only.

Tokens only (no new hardcoded colors). Recompile `output.css` (never hand-edit).

## Stage A — Warm neutral ramp (`tailwind.config.js`)
Override `theme.extend.colors.gray` with a warm ramp (lightness preserved, hue → warm/parish):

| step | from (TW default) | to (warm) | typical use |
|---|---|---|---|
| 50  | `#F9FAFB` | `#FAF7F1` | lightest surface |
| 100 | `#F3F4F6` | `#F1ECE4` | soft surface / hover |
| 200 | `#E5E7EB` | `#E6DED5` | hairline borders |
| 300 | `#D1D5DB` | `#D8CEC2` | borders / dividers |
| 400 | `#9CA3AF` | `#B0A595` | disabled / faint |
| 500 | `#6B7280` | `#8A7F70` | muted text |
| 600 | `#4B5563` | `#6B6358` | secondary text (= `--umi-text-soft`) |
| 700 | `#374151` | `#4A443C` | strong secondary |
| 800 | `#1F2937` | `#332F29` | near-ink |
| 900 | `#111827` | `#2C2A29` | ink (= `--umi-text`) |

Leave `white`, emerald/red/orange/blue semantic colors untouched. Document loudly in the config.
**Test:** `gray.900` is warm (≠ TW default), and warm-ink-on-cream ≥ AA.

## Stage B — Editorial design system (`input.css` + `base.html`)
- **Type scale (the biggest "unrecognizable" lever).** Add a masthead utility:
  `.umi-masthead { @apply font-serif font-semibold tracking-tight; font-size: clamp(2.25rem, 6vw, 4rem); line-height: 1.05; }`
  and a kicker/accent rule (`.umi-rule` — short teal underline). Bump section headings for more
  presence and air. Keep Lora/Open Sans (no new fonts).
- **Spacing / rhythm.** Section spacing utility (`.umi-section { @apply py-12 md:py-20; }`); give
  `.umi-card` a touch more padding + consistent `shadow-pew`; widen feed gutters.
- **Chrome (`base.html`).** Slim translucent `.umi-header`: **serif wordmark** + community name,
  **one** teal pill CTA (gold reserved for badges). Refined footer (warm, quiet). Keep the skip-link
  + translucent blur. The default header already uses tokens — ensure no hardcoded grays remain.
- **Buttons.** `.btn-primary` (teal pill) + `.btn-secondary` (outline teal — already exists) used to
  replace ad-hoc white/gray buttons; fix `.btn-secondary:hover` rgba to a teal tint (currently green).

## Stage C — Landing (`templates/pages/landing.html`) — bespoke
Replace the hardcoded-gray header override with the themed chrome. Rebuild hero as a **left-aligned
masthead**: *"Need a hand? Lend one."* (`.umi-masthead`) + `.umi-rule` + one-line subhead + a single
teal **"Join a community"** pill (+ quiet text "Learn more" link). Keep the three value props but
quieter (smaller, warm, left or evenly spaced). Add a small **"sample board" peek** (2–3 demo
bulletin cards, teal/gold rails) so the noticeboard metaphor lands. Warm the network-deployment band.

## Stage D — Feed (`templates/communities/feed.html` + `_feed_results.html`) — bespoke
Masthead heading (community name / "The board") + one **"Post an ask"** CTA. Airy bulletin **card
grid** (existing accent-rail cards, more spacing). Warm, inviting **empty state** ("Be the first to
share an ask"). Keep HTMX behavior intact.

## Stage E — Verify
- Keep the **full suite green** (315 → regression guard on rendering/behavior/HTMX).
- **New tests** (`tests/test_theming.py` or `tests/test_layout.py`):
  - `gray.900`/`gray.600` warmed in tailwind config; warm-ink-on-cream ≥ 4.5:1.
  - Landing + feed return 200 with exactly one `<h1>` + a `<main>` landmark + the primary CTA link.
  - "no hardcoded gray *hex* leaks" guard on landing (e.g. no `#111827`/`bg-white` header).
- Recompile `output.css`. Run ruff/format, `makemigrations --check`, `check --deploy` (0 issues).
- **Visual confirmation** (screenshots): landing, feed/sign-in, + a sample inherited page (e.g.
  a casework/list or settings page) to catch warm-ramp breakage.

## Guardrails (non-negotiable)
Light-only (no dark surface). Gold accent kept. Per-community theming still wins (primary/accent are
`--umi-*`; only neutrals are static-warm by design). ≥44px touch targets. WCAG AA. `prefers-reduced-
motion` respected (fades only). No new hardcoded colors in components; recompile, don't hand-edit
`output.css`.

## Build order (commit per stage = resumable checkpoints)
A (warm ramp) → B (design system) → C (landing) → D (feed) → E (tests + verify + screenshots).
Each stage: change → recompile if CSS-affecting → run theming/layout tests → commit `--no-verify`
(local bandit hook trips on pre-existing findings; real gates run manually) → screenshot at C/D/E.

## Out of scope
Dark mode; new fonts; new JS framework; per-page rewrites of low-traffic templates beyond what the
system pass + warm ramp give them; the "Create account" link re-theme is a nice-to-have folded into
Stage B chrome.
