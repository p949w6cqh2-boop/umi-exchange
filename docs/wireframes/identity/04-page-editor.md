# 04 · Page editor (draft) — 390px
```
┌──────────────────────────────┐
│ ← Your pages                 │
│ Title  [___________________] │
│ Slug   [our-story_________]  │  editable while draft; frozen after
│        "Link: /c/…/p/our-story"  first publish (note shown)
│ Order  [ 1 ]  On landing (✓) │
│ Body (markdown)              │
│ ┌──────────────────────────┐ │
│ │ # …                      │ │  textarea, 20k cap w/ counter
│ └──────────────────────────┘ │
│ [ Save draft ] [ Preview ]   │  preview = server-rendered, same
│ ┌─ Preview ────────────────┐ │  pipeline, POST body, not stored
│ │ (prose well render)      │ │
│ └──────────────────────────┘ │
│ ── admin only ──             │
│ [ Publish ]                  │  the priest signs
│ [ Archive ]                  │  never delete
└──────────────────────────────┘
```
REGIONS fields per §C; preview stacked below on mobile, side-by-side desktop. AUTHZ
admin+coordinator edit DRAFT only; Publish/Unpublish admin-only POST (403 otherwise); published
page shows read-only banner "Live pages aren't edited in place — unpublish to draft first"
(edits-require-draft, Stage-3 keyed). EMPTY new page = placeholder md hint. SAFETY preview runs
full sanitize; images-become-links note under body. VARIANTS coordinator = no Publish button,
"waiting on an admin to publish" hint; published-view = read-only + Unpublish (admin).
