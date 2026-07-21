---
description: Handoff checkpoint for a multi-stage pipeline — record remaining stages + current state so a session or rate-limit cutoff leaves a clean recoverable point, not a half-finished merge. Read-only to source (writes only the scratch checkpoint).
allowed-tools: Read, Write, Edit
---
For any multi-stage pipeline (spec→TDD→PR→merge→deploy, a migration series, a batch of PR reviews),
keep a handoff checkpoint so an interruption is recoverable instead of a half-finished merge.

WRITE the checkpoint BEFORE stage 1, and UPDATE it after every stage/merge, to
`.claude/checkpoint.md` (a scratch handoff file — it is transient STATE, not source; make sure it is
gitignored, never committed):

1. **Goal** — one line: what "done" looks like.
2. **Stages** — ordered list, each marked ✅ done / ▶ in-progress / ⬜ pending, with the branch/PR
   number and the gate/CI status per stage.
3. **Current state** — exactly where we are: branch checked out, last commit sha, what is merged to
   `main`, what is awaiting CI or a human key.
4. **Resume** — the literal next command(s) to run to continue from here.

Rule: never start stage N+1 without updating the checkpoint for stage N. A rate-limit or context
cutoff must leave `.claude/checkpoint.md` accurate enough to resume blind.

**Output-token guard (insights 2026-07-20):** commit after EVERY stage; between stages report a
one-line status only. An interrupted run resumes by verifying commits, never by redoing work —
and short statuses keep long pipelines clear of output-limit deaths.
