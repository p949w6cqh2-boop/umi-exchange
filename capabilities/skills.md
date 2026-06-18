# Capabilities — the skills registry (C3)

> STATUS: **DRAFT** by Claude Code, 2026-06-17. Jasiah to confirm which become real
> `/skills` (one command forever).
>
> Principle (the blueprint): *"Typed the same thing three times? That's a skill waiting to
> exist."* Each skill has a **defined role**, the **keyring keys** it needs, and **where it
> routes for context**. The agent stays general-purpose; skills route to more context.
> **No key = no capability.** If it can, assume it will → every skill's worst case is a safe-fail.

## Observed skills (from how we've actually worked, 3×+)
| Skill | Fires when | Keyring keys needed | Routes to | Safe-fail |
|---|---|---|---|---|
| **verify-and-integrate an AGI bundle** | a design/code bundle arrives | branch ✅ · push-to-main ❌ ASK | the bundle + repo; `STATE.md` | branch, never main; tests must pass first |
| **run the pre-deploy gate** | before a merge/release | read-only ✅ | `CLAUDE.md` · runbook | report only; never deploys |
| **draft an AGI prompt** | new build/design needed | none (text only) | `docs/prompt-inventory.md` | output is a draft to copy-paste |
| **rotate / retire a KEK** | key rotation due | prod ops ❌ ASK | `docs/envelope-rollout-runbook.md` | dry-run + 3 censuses before dropping a key |
| **reconcile Brain ↔ STATE.md** | ground truth moved | branch ✅ | `umi-exchange/STATE.md` | propose diff; Jasiah confirms |
| **review / babysit a PR** | PR opened / CI event | comment ✅ · merge ❌ ASK | the PR + CI logs | fix on branch; ask before merge |
| **flaw audit + fix** | "what else is broken?" | branch ✅ | sandbox-report | add a regression test with every fix |

## How a new skill is born
1. Notice the same prompt repeated (Mon / Wed / Fri).
2. Name it; write a one-paragraph **role** + its required keyring keys + its context pointers.
3. Add a row above. (Later: a real `/skill` command in the harness.)

## Open (Jasiah to decide)
- Which of these become first-class `/commands` now?
- Any skill that should be **fully autonomous** vs **always-ask**? (drives the keys above)
