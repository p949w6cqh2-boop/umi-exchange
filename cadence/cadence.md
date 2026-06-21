# Cadence — when work fires (C4)

> STATUS: **CONFIRMED by Jasiah, 2026-06-17 (interview round 2).**
>
> Every task fires one of three ways. **Autonomy is earned** — more autonomy = more watching.
> Start manual; promote only after battle-testing, and only if the worst case is a safe-fail.

## Manual — something you ask for (the default)
Everything in `capabilities/skills.md` lives here today, by Jasiah's policy, except the drift guard.
- **`/brain-refresh`** (`cadence/brain-refresh.md`) — nightly consolidation pass. **Stage 1 Manual**:
  run by hand, review the digest; graduate to scheduled report-only (cron → `claude -p`) after it
  proves safe. Reconcile · prune-to-archive · route-check · digest. Worst case is safe-fail (branch +
  archive, never delete/merge).

## Event — something happens (a hook fires)
- PR opened / CI status changes → review or triage (comment ✅; merge ASK). *(Available, used ad hoc.)*

## Schedule — recurring
**🟢 Graduated to report-only: the weekly Brain↔STATE drift guard.**
| Aspect | Decision |
|---|---|
| Runs where | **CI (GitHub Actions)** — not Jasiah's machine, not prod. It reports, it doesn't act. |
| Frequency | **Weekly, Sunday 00:00 UTC** |
| Output | A summary of what changed in `umi-exchange/STATE.md` vs the Brain's last-reconciled snapshot |
| On drift | Notify; Jasiah decides whether to sync the Brain |
| Graduation | Stays **report-only**; may **act (auto-open a sync PR)** after **3 clean runs** build confidence |

Implementation: `.github/workflows/drift-guard.yml` + `cadence/drift-guard/check-drift.sh`
(+ `STATE.snapshot.md` baseline). **Ready to activate once `umi-brain` is on a GitHub remote.**

(Also designed, not yet wired: weekly Lake-2 stale-draft sweep — discard `draft` notes > 72h, audited, via django-q2.)

## The autonomy ladder
1. **Manual** — run by hand. → 2. **Schedule/Event, report-only** — fires but only *proposes*; you approve. → 3. **Acting** — only after battle-testing (e.g., 3 clean runs) and only if the worst case is a safe-fail (archive not delete, draft not send, branch not main). Visibility increases with autonomy.
