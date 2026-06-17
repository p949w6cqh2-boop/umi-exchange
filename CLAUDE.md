# umi-brain — Router

> **This file is a router, not a knowledge base.** It holds pointers: "need X? look there."
> An index lives at every level so an agent goes straight to the source.
> Maintained for / by **Jasiah** (Founder & Steward). All plain markdown — portable to any tool.

## 🔑 Read this FIRST, every session
- **`trust/keyring.md`** — what you may/may not do. **Load-bearing. Non-negotiable.**
  TL;DR: propose/draft/analyse freely; **never** push to `main`, send, delete, spend, or touch live parish data without asking.

## Where things live
| Need… | Go to |
|---|---|
| Who Jasiah is / origin story / entity status | `identity/who-i-am.md` |
| What UMI means, canonical names, the 5-year vision, the 8 lakes | `vision/what-is-umi.md` |
| Tool stack, who-does-what, project ("world") inventory | `projects/stack.md` |
| Permissions / the keyring / safe-fail rules | `trust/keyring.md` |
| Loose notes not yet filed | `inbox/` |

## The built reality (ground truth — code, not design)
- **Lake 1 = `umi-exchange`** (separate repo). Django/Postgres/Redis/HTMX. Lake 1's own `STATE.md` is the authoritative snapshot of what's actually built.
- **Lake 2 (Case Notes / casework) is now BUILT** inside `umi-exchange` (`apps/casework`), merged to main.
- **Envelope encryption / crypto-shred** is shipped across all PII (needs + casework + Person), Stages A–E complete. Conformance: **Core ✅ + Casework ✅**; next = Federation.

## Status legend (apply to every claim)
- **BUILT** — exists in code, tested. · **DESIGNED** — spec/design only, unbuilt, unverified. · **IDEA** — not yet specced.
- Designs are **not** facts. When a node asserts something, it must carry one of these tags.

## Cadence (how work fires) — to wire up later
- **Manual** — Jasiah asks. · **Event** — a hook fires. · **Schedule** — recurring (e.g. weekly check).

## How to extend this brain
- New knowledge → a markdown file in the right folder + a pointer added here.
- Repeated 3× the same prompt → it's a **skill** waiting to exist.
- Keep the router to **pointers**; put knowledge in the leaf files.
