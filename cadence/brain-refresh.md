---
description: Nightly brain consolidation — reconcile, prune hard, keep the brain lean and precise.
allowed-tools: Read, Edit, Write, Glob, Grep, Bash(git*)
---
# /brain-refresh — consolidation pass

> STATUS: **Stage 1 (Manual)** on the autonomy ladder (`cadence/cadence.md`). Run by hand first;
> graduate to scheduled report-only, then acting, only after battle-testing. Extends the existing
> report-only drift-guard with pruning + consolidation + a morning digest. Same house format as
> `capabilities/prompt-library.md`.

To use as a slash command, copy this file to `~/.claude/commands/brain-refresh.md`.

```
ROLE: nightly brain-consolidation pass for umi-brain (Jasiah's markdown OS). GOAL: keep the brain
LEAN, CURRENT, PRECISE. Operating assumption: most accumulated data is trash — prune hard, keep ONE
canonical copy, archive don't delete.
SCOPE: umi-brain/** + umi-exchange/{STATE.md, docs/**} ONLY. NEVER touch the app runtime DB or any
live community/parish data — that is the keyring's hard line.
INPUTS: git log since last run; STATE.md (code ground truth); every brain node + its CLAUDE.md index.
DO (in order):
  1. RECONCILE — brain claims vs STATE.md + git: fix stale facts; correct BUILT / DESIGNED / IDEA tags.
  2. PRUNE — flag duplicate / superseded / one-off / never-referenced content; move it to archive/
     (dated subfolder), NEVER hard-delete; collapse near-duplicates into one canonical note.
  3. ROUTE-CHECK — every fact reachable by clicking down from a CLAUDE.md index; fix orphans + broken
     pointers (bug #1); routers hold POINTERS not knowledge.
  4. CONSOLIDATE — one fact, one home; replace stray copies with pointers.
  5. SURFACE — same prompt/step seen 3x -> propose a skill or automation (don't build it, propose it).
  6. UPDATE — refresh projects/umi-exchange-roadmap.md (live handoff) to current reality.
PRECISION BUDGET: each leaf node <~200 lines; if a node is over, prune before adding. Prefer
archive-over-keep; "just in case" is trash.
OUTPUT (Stage 1/2 = report-only):
  (a) edits on a branch  brain/nightly-YYYYMMDD  (NOT master);
  (b) a digest at  inbox/nightly-YYYYMMDD.md : what changed · what was archived + why · proposed
      skills/automations · open questions for Jasiah. Do NOT merge.
CONSTRAINTS (keyring): branch not master; nothing merged/deployed; archive not delete; no PII/secrets
in git. STOP and leave it in the digest if a change is ambiguous or destructive. Commit branch +
digest — that IS the deliverable for morning review.
```
