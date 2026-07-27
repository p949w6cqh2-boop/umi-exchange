---
description: Ship a branch the house way — gate, open PR, hold for CI green, merge, delete branch. Merging to main always stays a human key.
allowed-tools: Bash, Skill, mcp__github__create_pull_request, mcp__github__pull_request_read, mcp__github__merge_pull_request
---
Codifies the standard umi-exchange merge flow. Do NOT merge to `main` without an explicit human key.

1. **Gate:** run the `/gate` skill (full pytest on Postgres+Redis with the count read from a file,
   `ruff check` + `ruff format --check`, `makemigrations --check`, bandit/semgrep `--baseline-commit
   main`, `check --deploy` = 0). Local PASS is necessary, NOT sufficient.
2. **PR:** open a PR to `main`. Stage explicit paths only — never `git add -A`/`git add .` here
   (blanket staging sweeps in untracked files nobody is looking at; hook-blocked). Body = what /
   why / tests. Update `CHANGELOG.md` in the
   board's plain language if the change is user-facing (skip for infra/CI-only changes).
3. **Hold for CI:** poll the PR's check runs (`pull_request_read` → `get_check_runs`). Do NOT merge
   until EVERY check is `completed` + `success`. Any `in_progress` or failure → hold and report;
   never merge on a pending or red run.
4. **Merge:** only on an explicit human key, via the PR (merge commit). Then delete the branch.
5. **Report:** PR number, the CI verdict per check, and the merge sha.
