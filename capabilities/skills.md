# Capabilities — the skills registry (C3)

> STATUS: **CONFIRMED by Jasiah, 2026-06-17 (interview round 2).**
>
> Principle: *"Typed the same thing three times? That's a skill waiting to exist."* Each skill
> has a defined role, the **keyring keys** it needs, and where it routes for context. The agent
> stays general-purpose; skills route to more context. **No key = no capability.** If it can,
> assume it will → every skill's worst case is a safe-fail.
>
> **Autonomy policy (Jasiah):** everything stays **Manual** (Jasiah signs off) until proven.
> The Brain↔STATE drift guard is the one exception — **report-only now, may act after 3 clean runs.**

## Registry
| Skill | Autonomy | Keyring keys | Routes to | Why this level |
|---|---|---|---|---|
| **verify-and-integrate a bundle** | Manual | branch ✅ · push-main ❌ | bundle + repo · `STATE.md` | Jasiah is final authority on what enters the codebase |
| **run the pre-deploy gate** | Manual | read-only | `CLAUDE.md` · runbook | deployment is high-risk; Jasiah approves |
| **draft an AGI prompt** | Manual (autonomous later) | none | `docs/prompt-inventory.md` | still refining the art |
| **rotate / retire a KEK** | Manual | prod ops ❌ | envelope-rollout-runbook | security-critical ops |
| **reconcile Brain ↔ STATE** | **Report-only** (act after 3 clean runs) | branch ✅ | `umi-exchange/STATE.md` · `cadence/` | low-risk, high-value, fully observable |
| **babysit a PR** | Manual | comment ✅ · merge ❌ | PR + CI logs | Jasiah decides when to merge |

## How a new skill is born
1. Notice the same prompt repeated (Mon/Wed/Fri). 2. Name it; write its role + required keys + context pointers. 3. Add a row. 4. Later: a real `/skill` command. 5. Promote autonomy only after battle-testing (see `cadence/cadence.md`).
