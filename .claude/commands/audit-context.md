---
description: GC for umi-exchange/CLAUDE.md — diff the docs against the code, propose a clean draft. Read-only.
allowed-tools: Read, Glob, Grep
---
Read `CLAUDE.md` and `STATE.md`. Walk `apps/` and `config/settings/base.py`.

Compare the documentation to the actual code and output:
1. **STALE (trash to cut):** statements in CLAUDE.md/STATE.md about files, apps, commands, or
   patterns that no longer exist or have changed.
2. **MISSING (facts to add):** new load-bearing patterns in the code that the docs don't mention
   (a fact = something that needs a migration or an architectural decision to change).

Then draft a corrected CLAUDE.md. **Do NOT write or commit it — propose the draft inline only.**
Keep the same structure and tone. Facts only; never add ephemeral/transient state.
