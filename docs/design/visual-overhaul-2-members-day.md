# Visual Overhaul Phase 2 — "The Member's Day"

> STATUS: DESIGNED, approved by Jasiah 2026-07-10 (scope + design via session Q&A).
> Continues the merged look-don't-read overhaul (`e8d446d`) into the logged-in member journey.
> Presentation-only: **no view/URL/model/HTMX changes** — stricter than phase 1 (which added one
> additive filter). Casework and federation surfaces are deliberately out of scope.

## Why

Phase 1 treated the public arc (landing → story → believe → different → join-door) and made the
board surfable. The logged-in journey still reads instead of looks:

- `communities/join.html` / `create.html` — the threshold moment, scene-less.
- `hub/_hub_body.html` — The Pulse works, but the crown is plain and empty states are bare text.
- `needs/detail.html` / `offers/detail.html` — still on the **pre-Commons `text-gray-*` palette**
  (objective defect: off design-system since v2), zero visual hierarchy.
- `matches/detail.html` — the §8.2 contact reveal, the emotional peak of the whole product, is a
  generic emerald alert box.

## The four beats

### Beat 1 — Threshold (`communities/join.html`, `communities/create.html`)
- **One new linocut scene (#7): "the threshold"** — two doors in a parish wall, one ajar with warm
  light, one fresh-painted. Same language as the six: two-ink editorial, faceless, theme-tinted
  washes (`var(--umi-*)`), print grain. Original SVG, no stock/AI-raster.
- Scene crowns the two-doors header on `join.html`; `create.html` gets a smaller echo of the same
  scene so both doors of the flow rhyme.
- Serif chapter-door continuity: the public arc ends at "Join"; these pages open like the next
  chapter rather than an unrelated form.
- Forms, HTMX, URLs untouched.

### Beat 2 — Hub crown (`hub/_hub_body.html`, `hub/_spotlight.html`, `hub/_pulse.html`)
- Masthead: low-opacity wash of **"the well"** (existing scene — morning at the well = the daily
  return), clipped right, `aria-hidden="true"`, absolutely positioned so layout metrics don't move.
- **Empty states get miniature scenes**: spotlight-empty and pulse-empty render a small linocut
  vignette instead of text-only.
- Pulse mechanics untouched: the 60s HTMX poll and swap targets stay exactly as-is; scenes render
  inside the swapped partials only where they are part of that partial's empty state (safe — the
  poll re-renders the whole partial), the masthead scene lives outside all swap targets.

### Beat 3 — Notices (`needs/detail.html`, `offers/detail.html`)
- **Palette normalization**: every `text-gray-*` / `bg-gray-*` legacy utility replaced with
  parish-ink/stone tokens (`text-parish-ink/NN`, `var(--umi-border)`, themed chips). Detail pages
  must end the batch with zero `text-gray-` occurrences.
- Header rebuilt as **"a notice pinned to the board"**: large category medallion (same treatment
  as phase-1 feed cards), serif display title, one compressed meta line (poster, badges,
  neighbourhood, age), description as the only paragraph. Urgency/status chips themed via tokens.
- Back-link becomes the board breadcrumb (matches phase-1 sticky-bar language).
- Owner/coordinator delete action stays, restyled with tokens; confirm flow unchanged.

### Beat 4 — The exchange ceremony (`matches/detail.html`, `components/_contact_info_box.html`, `components/_match_timeline.html`)
- Contact-reveal banner → **ceremony card**: "the exchange" linocut (existing scene) + serif
  "You're connected." + one quiet line on §8.2 spirit (shared only between you two). Same
  gating expression (`show_contact and contact_info and is_participant`) — zero logic change.
- Timeline markers restyled with inked linocut flavor (hand-stroke dots/rules); same DOM data.
- Accept-confirm modal: raw `bg-white`/`text-gray-900` → tokens; behavior (Alpine `confirm`
  state) untouched.

## Rails (standing rules honored)

- Presentation-only: no view/URL/model/HTMX/schema changes anywhere in the batch.
- Themeable color via `var(--umi-*)` only; never hand-edit `output.css` — recompile via
  local tailwindcss and commit the compiled file.
- Scenes are decorative: `aria-hidden="true"`, `focusable="false"`; reduced-motion honored by the
  existing reveal/transition CSS (no new motion primitives).
- Multi-line comments: `{% comment %}` only.

## Tests (TDD — failing first, per beat)

- `tests/test_members_day.py` (new):
  - join + create render the threshold scene include (auth'd, no-community user 200s).
  - hub masthead carries the well wash; hub still 200s with and without communities.
  - need/offer detail: **no `text-gray-` in the rendered body** (palette regression guard),
    medallion present, page 200s for a member.
  - match detail (accepted, participant, contact consented): ceremony copy present;
    (proposed): ceremony absent — gating preserved.
- Existing suites must stay green: 728 on Postgres 16 + Redis is the baseline.

## Gate

Full standing gate: ruff check + format · `makemigrations --check` (must be no-op — no schema) ·
bandit/semgrep vs main baseline · **full pytest on Postgres 16 + Redis** · `check --deploy` = 0.
Branch `feature/visual-overhaul-2` → PR → STOP before merge (keyring).

## Out of scope (explicit)

Casework (work tool — speed over art, PII restraint), federation surfaces (Wellspring-treated in
Stage C3), dashboard/notifications/tags/settings/auth (phase 3 candidates), any engagement
mechanics (anti-manipulation stance from Hub v2 stands).
