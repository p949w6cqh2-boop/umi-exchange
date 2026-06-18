# umi-brain — Router

> **This file is a router, not a knowledge base.** It holds pointers: "need X? look there."
> An index lives at every level so an agent goes straight to the source.
> Maintained for / by **Jasiah** (Founder & Steward). All plain markdown — portable to any tool.

## 🔑 Read this FIRST, every session
- **`trust/keyring.md`** — what you may/may not do. **Load-bearing. Non-negotiable.**
  TL;DR: propose/draft/analyse freely; **never** push to `main`, send, delete, spend, or touch live parish data without asking.

## Where things live  (routing tree — every folder has its own `CLAUDE.md` index; click in)
The four C's (all confirmed by Jasiah 2026-06-17 — rounds 1 & 2):
| C | Node (folder index) | Source file(s) |
|---|---|---|
| **C1 Context** | `identity/CLAUDE.md` | `identity/who-i-am.md` |
| **C1 Context** | `vision/CLAUDE.md` | `vision/what-is-umi.md` · `vision/journey.md` (had-vs-getting) |
| **C1 Context** | `projects/CLAUDE.md` | `projects/stack.md` (live truth → `umi-exchange/STATE.md`) |
| **C2 Connections** | `connections/CLAUDE.md` | `connections/connections.md` (graph + static-vs-live) |
| **C3 Capabilities** | `capabilities/CLAUDE.md` | `capabilities/skills.md` |
| **C4 Cadence** | `cadence/CLAUDE.md` | `cadence/cadence.md` · `cadence/drift-guard/` |
| **Trust (load-bearing)** | `trust/CLAUDE.md` | `trust/keyring.md` |
| Loose notes | `inbox/CLAUDE.md` | `inbox/` (`private.md` = local-only) |

> Routing rule: this file and every folder `CLAUDE.md` hold **pointers, not knowledge**.
> If you can't reach a fact by clicking down from here, that's the first bug to fix.

## The built reality (ground truth — code, not design)
- **Lake 1 = `umi-exchange`** (separate repo). Django/Postgres/Redis/HTMX. Lake 1's own `STATE.md` is the authoritative snapshot of what's actually built.
- **Lake 2 (Case Notes / casework) is now BUILT** inside `umi-exchange` (`apps/casework`), merged to main.
- **Envelope encryption / crypto-shred** is shipped across all PII (needs + casework + Person), Stages A–E complete. Conformance: **Core ✅ + Casework ✅**; next = Federation.

## Status legend (apply to every claim)
- **BUILT** — exists in code, tested. · **DESIGNED** — spec/design only, unbuilt, unverified. · **IDEA** — not yet specced.
- Designs are **not** facts. When a node asserts something, it must carry one of these tags.

## Cadence (how work fires) → `cadence/cadence.md`
- **Manual** — Jasiah asks. · **Event** — a hook fires. · **Schedule** — recurring (e.g. weekly check).
  Autonomy is earned: more autonomy = more watching. Start manual, graduate after battle-testing.

## How to extend this brain
- New knowledge → a markdown file in the right folder + a pointer added here.
- Repeated 3× the same prompt → it's a **skill** waiting to exist.
- Keep the router to **pointers**; put knowledge in the leaf files.
