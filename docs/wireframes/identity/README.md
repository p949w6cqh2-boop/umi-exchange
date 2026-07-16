# Layer C wireframes — lo-fi (Stage 6)

> Annotated ASCII, 390px-first, structure only — no styling (Stage 7's job). Keyed medium.
> Legend per screen: REGIONS (what each does) · AUTHZ · EMPTY · SAFETY · VARIANTS (keyed:
> variant states are named explicitly, never improvised).

## Screens
01 /protocol/ (Layer P interleave check) · 02 settings-identity · 03 pages-manager ·
04 page-editor · 05 page-member-view (+draft-banner, +hidden-banner variants) ·
06 page-anon-view · 07 pages-index (+member, +anon, +coordinator-chips variants) ·
08 hub-personalized · 09 tombstone · 10 moderation-queue page row

## Flows (keyed at Stage 5)
F1 authoring: settings → Your pages → New → draft (save/preview loop) → [coordinator drafts] →
   admin Publish → live.
F2 live fix: published → admin Unpublish → draft edit → admin Publish (the priest signs again).
F3 member read: hub pages card / footer column → page. Draft invisible (404).
F4 anonymous front door: /c/<slug>/ → (no-oracle) → /p/ index (landing-marked only) → page →
   join CTA. Any ineligible case = identical login redirect.
F5 moderation: member flags page → coordinator queue (excerpt row) → Hide → member/anon 404,
   coordinator banner → Unhide reversible.
F6 switch: community switcher → whole bundle swaps (name, theme, welcome, pages nav).
