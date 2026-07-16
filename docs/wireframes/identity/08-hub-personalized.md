# 08 · Hub, personalized — 390px
```
┌──────────────────────────────┐
│ St. Patrick's        ⌂ ▤ ⊕ ▣│
├──────────────────────────────┤
│ Welcome back, Nuala.         │  greeting unchanged
│ "Whatever you did for the    │  welcome_line under it, quiet,
│  least of these…"            │  auto-escaped, absent when unset
│ [Post an ask] [Post an offer]│
│ ┌─ spotlight ──────────────┐ │
│ │ (scene: admin's pick,    │ │  scene_choices.hub — falls back
│ │  else default basket)    │ │  to today's default silently
│ │ ONE ASK, RIGHT NOW …     │ │  spotlight logic untouched
│ └──────────────────────────┘ │
│ ┌─ Your community ─────────┐ │
│ │ Pages: Our story ·       │ │  first 4 by sort_order
│ │ Mass times · Ministries  │ │
│ │ All pages ▸              │ │  → screen 07
│ └──────────────────────────┘ │
│ (pulse, corner, week — as is)│
└──────────────────────────────┘
```
REGIONS greeting+line; scene hook; pages card new. AUTHZ member. EMPTY no pages → card absent
(not an empty shell); no welcome_line → greeting exactly as today. SAFETY welcome_line escaped.
VARIANTS switcher swap = every region above changes together (F6 test).
