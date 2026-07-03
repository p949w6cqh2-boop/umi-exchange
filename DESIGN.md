# Design

> Visual system for UMI Exchange — **"The Wellspring"** (Direction D). Light-only, theming-safe,
> scan-first editorial noticeboard. Tokens are CSS custom properties (`--umi-*`) injected per request
> in `templates/base.html` (defaults) and `static/css/input.css` (`:root`), compiled to
> `static/css/output.css` via Tailwind. Per-community themes override in `apps/communities/themes.py`.

## Theme

A warm digital **town well**: cream paper, **water-teal** as the gathering color, **soft gold** as
the warm accent. **Editorial noticeboard, not an app** — oversized serif mastheads, breathing room,
bulletin "note" cards. **Light theme only** (ink stays dark across all per-community presets). Color
strategy: **Restrained → Committed** — warm neutrals carry the surface, teal carries action, gold
carries warmth.

## Color

Default "parish / Wellspring" palette (per-community themes override `primary`/`accent`/surfaces):

| token | value | role |
|---|---|---|
| `--umi-primary` | `#0F6B73` | water-teal — primary actions, links, need rail (6.03:1 on cream) |
| `--umi-primary-hover` | `#0B585F` | hover + focus ring |
| `--umi-accent` | `#C49A3C` | soft gold — warm accent, offer rail (decorative/fill; dark ink on gold = AA) |
| `--umi-bg` | `#FDFBF7` | cream paper (body) |
| `--umi-bg-soft` | `#EFF1EE` | barely-cool soft surface |
| `--umi-card` | `#F6F8F5` | barely-cool card |
| `--umi-border` | `#DDE6E2` | barely-cool hairline border |
| `--umi-text` | `#2C2A29` | warm ink (13.6:1) |
| `--umi-text-soft` | `#6B6358` | muted warm (4.7:1) |
| `--umi-need-accent` | `#0F6B73` | need cards → teal left rail |
| `--umi-offer-accent` | `#C49A3C` | offer cards → gold left rail |

- **Neutral ramp:** Tailwind's cool default `gray` is overridden to a **warm parish ramp**
  (`50 #FAF7F1` … `600 #6B6358` … `900 #2C2A29`) so every `gray-*` usage reads warm, app-wide.
- **Semantic status** colors (emerald / amber / orange / red) are retained for urgency + state.
- **Per-community theming:** presets in `apps/communities/themes.py` (parish, ocean, forest, kinfolk,
  sankofa, royal, rose, clay, slate, midnight) plus per-community `theme_custom` hex overrides win
  over the defaults via `resolve_theme()`. Only the neutral ramp is static-warm by design.

## Typography

- **Display / headings:** **Lora** (serif; Georgia fallback — no external webfont). Editorial mastheads.
- **Body / UI:** **Open Sans** (system-ui fallbacks). Pairing is contrast-axis (serif + humanist sans).
- **Utilities:** `.umi-masthead` (`clamp(2.75rem,7vw,4.5rem)`, line-height 1.03), `.umi-display`
  (`clamp(1.75rem,4vw,2.5rem)`), `.umi-kicker` (small uppercase, teal), `.umi-rule` (short teal accent
  rule under a masthead).
- **Scan-first:** one masthead is the focal point per screen; copy is deliberately sparse.

## Layout & Spacing

- **Content column:** `.umi-container` (max-width 960px), mobile-first.
- **Rhythm:** `.umi-section` (`py-12 md:py-20`) for generous vertical breathing room; spacing varied
  for rhythm, not uniform.
- **Feed:** responsive bulletin grid (1 / `sm:2` / `lg:3`).
- **Cards:** `.umi-card` (rounded-xl, warm surface, hairline border, soft `pew` shadow, `p-6 md:p-7`)
  with a left accent rail — `.umi-need-card` (teal) / `.umi-offer-card` (gold).

## Components

- **Buttons:** `.btn-primary` (teal pill, white label, hover → deeper teal), `.btn-secondary` (outline
  teal), `.btn-accent` (gold). One obvious primary action per screen.
- **Header (`.umi-header`):** translucent blurred cream bar, serif wordmark + community name, a single
  CTA pill; gold reserved for badges. **Footer:** warm-dark (`--umi-text` ground).
- **Forms:** `.umi-input`, `.umi-label`, `.umi-pill` (quiet chip); native radios/checkboxes themed via
  `accent-[var(--umi-primary)]`; category/urgency selectors use teal selected-states.
- **Empty states:** warm, inviting microcopy ("Be the first to share an ask") — teach the surface,
  never "nothing here."
- **Bulletin card:** category icon + pill, serif title, `requester · timesince`, urgency dot.

## Motion

- **Calm fades only** — `.umi-fade` (200ms ease). No movement, no bounce, no orchestrated page loads.
- **`prefers-reduced-motion: reduce`** disables animation globally (honoured).
- **Hover:** soft shadow lift on cards (opacity/shadow, not layout).

## Accessibility

- WCAG 2.1 AA; contrast verified (teal 6.03:1 / white-on-teal 6.23:1 / ink 13.6:1).
- Light-only; visible teal focus ring (`.focus-ring`); skip-to-content link; ≥44px targets.

## Where it lives / how to build

`templates/base.html` (token injection + chrome) · `static/css/input.css` (`:root` + `@layer
components`) · `tailwind.config.js` (warm gray ramp, parish colors, fonts) · `apps/communities/
themes.py` (per-community presets). **Never hand-edit `output.css`** — recompile:
`npx tailwindcss@3.4.14 -i static/css/input.css -o static/css/output.css --minify`.
