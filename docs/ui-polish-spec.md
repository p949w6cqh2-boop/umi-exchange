# UMI UI Polish Spec — "Parish Hall Bulletin Board" (v2, theming-safe)

## Goal
Eliminate the bland/Squarespace feel — make it glanceable, tactile, bespoke — **without** breaking
per-community theming, the existing `.umi-*` design system, or the calm-motion / accessibility rules.

## Non-negotiable constraints (read first)
1. **Theming is live.** `templates/base.html` injects per-community colors into CSS vars
   (`--umi-primary`, `--umi-accent`, `--umi-bg`, `--umi-card`, `--umi-border`, …). **Any color that
   should follow a community's theme MUST use `var(--umi-*)`.** Never hardcode `#2B5E2B`/`#C49A3C`
   in `@layer components` — that re-bakes the palette and disables theming. (The Tailwind `parish-*`
   tokens are *fixed defaults* compiled into config; they do NOT pick up per-community overrides, so
   prefer `var(--umi-*)` for themeable surfaces/accents.)
2. **Polish the existing classes, don't fork them.** Enhance `.umi-card`, `.umi-card-hover`,
   `.umi-need-card`, `.umi-offer-card`, `.btn-primary`, `.btn-secondary`, `.umi-header`,
   `.umi-container`, `.umi-fade`. Do NOT introduce a parallel `.card-parish`/`.btn-parish` system —
   the templates already use `.umi-*`.
3. **Calm motion only.** House rule is "gentle fades, no movement." Keep transforms to a whisper
   (`scale(1.01)` max) and lean on **shadow + fade** for tactility. Motion is already globally gated
   by `prefers-reduced-motion` in `base.html`; keep it that way — add no ungated `translate`/`scale`.
4. **Presentation only.** No view/URL/model/HTMX-endpoint changes. Touch CSS + template markup only.
5. **Never hand-edit `static/css/output.css`.** Recompile (command at the end).

## 1. Design System — `static/css/input.css`
Edit the existing layers (do not replace the file). Keep all current `:root` vars and the
fades/focus-ring/x-cloak blocks.

**Base — add a subtle paper texture (themed, optional, calm):**
```css
@layer base {
  /* Faint bulletin-paper grain over the warm background. Themed via --umi-border. */
  body {
    background-image:
      radial-gradient(120% 60% at 50% -10%, #ffffff 0%, var(--umi-bg) 55%, var(--umi-bg-soft) 100%),
      radial-gradient(var(--umi-border) 0.5px, transparent 0.5px);
    background-size: auto, 22px 22px;
    background-attachment: fixed, fixed;
  }
  /* Glanceable headings: stronger serif weight + tighter tracking. */
  h1, h2, h3 { font-weight: 600; letter-spacing: -0.015em; }
}
```

**Components — enhance existing classes (all `var()`-driven):**
```css
@layer components {
  /* Lift via shadow, not movement. */
  .umi-card { @apply rounded-xl p-6 transition-shadow duration-300; }
  .umi-card-hover:hover {
    box-shadow: 0 8px 24px rgba(44, 42, 41, 0.10);
    transform: scale(1.01);              /* gated globally by prefers-reduced-motion */
  }
  /* Thicker accent rails read better as a bulletin. */
  .umi-need-card  { border-left: 5px solid var(--umi-need-accent); }
  .umi-offer-card { border-left: 5px solid var(--umi-offer-accent); }

  /* Buttons: add shadow + a gold accent variant; keep var-driven hover. */
  .btn-primary   { @apply shadow-sm hover:shadow-md; }
  .btn-secondary { @apply hover:shadow-sm; }
  .btn-accent {
    @apply inline-flex items-center justify-center gap-2 rounded-full px-6 py-3 min-h-[48px] font-medium transition shadow-sm hover:shadow-md;
    background-color: var(--umi-accent);
    color: var(--umi-text);
  }
  .btn-accent:hover { filter: brightness(0.95); }

  /* Category pill + tactile form controls + modal + timeline — all themed. */
  .umi-pill {
    @apply inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold uppercase tracking-wider;
    background-color: var(--umi-bg-soft);
    color: var(--umi-text-soft);
  }
  .umi-input {
    @apply w-full px-4 py-3 rounded-lg transition focus-ring;
    background-color: #ffffff;
    border: 2px solid var(--umi-border);
    color: var(--umi-text);
  }
  .umi-input:focus { outline: none; border-color: var(--umi-primary); }
  .umi-label { @apply block text-sm font-semibold mb-2; color: var(--umi-text-soft); }
  .umi-modal-panel {
    @apply w-full max-w-lg rounded-2xl overflow-hidden;
    background-color: var(--umi-card);
    border: 1px solid var(--umi-border);
    box-shadow: 0 20px 50px rgba(44, 42, 41, 0.25);
  }
  .umi-timeline-dot {
    @apply w-8 h-8 rounded-full flex items-center justify-center mr-3 border-2;
    border-color: var(--umi-border); background-color: var(--umi-bg-soft); color: var(--umi-text-soft);
  }
  .umi-timeline-active { background-color: var(--umi-primary); border-color: var(--umi-primary); color: #fff; }
}
```

## 2. Template Updates (REAL paths — refactor the existing markup, presentation only)
For each, the agent **reads the current file** and applies the classes above. Keep all Django/HTMX/
Alpine attributes, `{% url %}`s, and ARIA intact.

- **`templates/base.html`** — header already uses `.umi-header` (translucent blur ✅). Polish only:
  give the footer a warm dark band (`bg-[var(--umi-text)] text-[var(--umi-bg)]`) if a footer block
  exists; do not alter the theme-var `<style>` block.
- **`templates/communities/feed.html`** + **`templates/communities/_feed_results.html`** — make the
  card grid glanceable: `grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6` (results partial holds
  the cards). Don't change the HTMX swap targets.
- **`templates/components/_need_card.html`** — already `.umi-card umi-card-hover umi-need-card`. Make
  the title serif + bolder (`font-serif font-semibold`); convert the category span to `.umi-pill`;
  keep the existing urgency dot logic (low→green / medium→gold / high→orange-500 / critical→red-500).
- **`templates/components/_offer_card.html`** — mirror: `.umi-pill`, serif title, gold rail (already
  `.umi-offer-card`).
- **`templates/components/_empty_state.html`** — large inline SVG (currentColor, themed), warm copy,
  `.btn-primary` + `.btn-accent` actions.
- **`templates/needs/detail.html`** — wrap the detail body in `.umi-modal-panel` only if it's a modal;
  otherwise use `.umi-card`. Primary action = `.btn-primary`. (Detail is full-page here, not a modal —
  verify before adding Alpine close handlers.)
- **`templates/components/_match_timeline.html`** — apply `.umi-timeline-dot` / `.umi-timeline-active`
  to the existing step markup.
- **`templates/needs/create.html`** (+ `templates/offers/create.html`) — the need/offer forms: apply
  `.umi-input` to fields, `.umi-label` to labels, `.btn-primary` to submit. Keep the global field
  legibility rule in base.html.

> The original "use the HTML from chat history" line is removed — this spec is self-contained. If a
> structural detail is unclear, read the current template and preserve its structure; do not invent.

## 3. Execution Rules
- Presentation only — no view/URL/model/endpoint changes.
- Do NOT hand-edit `static/css/output.css`.
- Recompile at the end: `npx tailwindcss@3.4.14 -i static/css/input.css -o static/css/output.css --minify`
- Verify: `pytest -q` (template-render smoke) and, ideally, eyeball the feed + a detail page.
- Keyring: draft on a branch, **do not push to `main`**; report what changed.
