# Cadence — when work fires (C4)

> STATUS: **DRAFT** by Claude Code, 2026-06-17. Jasiah to confirm what runs unattended.
>
> Every task fires one of three ways. **Autonomy is earned** — more autonomy = more
> watching (visibility, monitoring, battle-testing), not less. Start manual; promote a
> routine to Event/Schedule only after it's proven and its worst case is a safe-fail.

## Manual — something you ask for
The default and the safe one. Most skills in `capabilities/skills.md` live here today.

## Event — something happens (a hook fires)
Candidates, each gated by the keyring:
- **PR opened / CI status changes** → review or triage (comment ✅; merge ASK).
- **Ground truth moves** (merge to `main`) → flag that `STATE.md` / the Brain may need a refresh.

## Schedule — recurring
- **Weekly — drift guard (highest value first):** reconcile the Brain against
  `umi-exchange/STATE.md`; propose a diff if they disagree. (This node *just* fixed a real
  drift — Lake 2 read "DESIGNED" when it was BUILT.)
- **Weekly — stale-draft sweep** (Lake 2): discard case notes left in `draft` > 72h, audited.
  (Designed as a django-q2 task; not yet wired.)

## The autonomy ladder (how a routine graduates)
1. **Manual** — run it by hand a few times.
2. **Event/Schedule, report-only** — it fires but only *proposes*; you approve.
3. **Event/Schedule, acting** — only after battle-testing, and only if its worst case is a
   safe-fail (archive not delete, draft not send, branch not main). Visibility increases with autonomy.

## Wiring (not built yet)
- Local schedules → cron / django-q2; repo events → GitHub webhooks / Actions; Claude Code
  PR-activity subscriptions already exist for the Event tier.

## Open (Jasiah to decide)
- Which routine graduates past Manual first, and to which tier?
- Where does the schedule run — your machine, the prod host, or CI?
