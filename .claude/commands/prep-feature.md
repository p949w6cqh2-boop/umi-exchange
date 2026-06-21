---
description: Scope the next roadmap feature on a branch — plan only, no code, no push.
allowed-tools: Read, Glob, Grep, Bash(git checkout:*), Bash(git branch:*), Bash(git status:*)
---
Read the roadmap (umi-brain/projects/umi-exchange-roadmap.md if reachable, else ask for it).
Identify the next in-flight or unbuilt feature and its must-fix catches.

1. Create branch `feature/<name>` from an up-to-date base. **DO NOT PUSH.**
2. Read the relevant models/views in `apps/`.
3. Output a staged change plan: what each stage touches, the must-fix catches to honor
   (e.g. Postgres-verify, no `select_related` on nullable locked FKs, shared `StateMachineMixin`,
   reuse `apps/accounts/ratelimit.py`), and the verify gates (ruff, makemigrations --check, pytest
   on Postgres, check --deploy).

STOP before editing any code. This is a planning pass only (Keyring: read > edit, branch > main).
