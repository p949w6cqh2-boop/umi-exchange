---
description: One-command security pass over a PR/diff — the recurring-criticals checklist, severity-ranked, report-only, BEFORE any merge. Complements (does not replace) the security-guidance plugin's /security-review skill.
allowed-tools: Bash, Read, Grep, Skill, mcp__github__pull_request_read
---
The three bugs that keep coming back in this repo, plus the standing sweeps. Run against a PR
number or the current branch diff. REPORT-ONLY: findings ranked by severity; nothing merges on
a red finding without the founder seeing it first.

1. **Scope the diff:** `git diff main...HEAD --stat` (three-dot — two-dot has lied here) or
   `gh`/MCP the PR's files. List every touched app/template.

2. **The recurring criticals (each has shipped a real bug before):**
   - **Prod-guards keyed off `DEBUG`, never the settings-module name.** Grep the diff for
     `settings.DEBUG`, `DJANGO_SETTINGS_MODULE`, `ENVIRONMENT`, module-name string checks.
     A guard reading the module name passes in prod with dev settings loaded.
   - **Probe/health endpoints must never redirect.** Any change near `health/`, middleware,
     `SECURE_SSL_REDIRECT`, or url patterns: confirm `/health/` returns 200 direct (the LB
     drops a 301). Check `X-Forwarded-Proto` handling if SSL-redirect logic moved.
   - **User-row / PII leaks across communities.** Any queryset touching `User`, `Member`,
     `Person`, or contact fields: confirm community scoping on every filter, no
     `.values()`/serializer exposing rows past the viewer's membership, contact revealed
     only post-acceptance (§8.2).

3. **Standing sweeps over the diff:**
   - Encrypted fields only via model properties (never raw `*_enc`/`*_enc_dek`).
   - No new plaintext PII columns; no PII in logs/audit `emit()` payloads.
   - Rate-limit bypasses: new POST endpoints on auth/flag surfaces carry limits.
   - Secrets: nothing resembling a key/token/password in the diff (`bandit` + eyeball).
   - `TransitionConflict` caught BEFORE `ValidationError` where both handled.

4. **Report:** findings as `SEVERITY (Critical/High/Med/Low) — file:line — claim — fix`,
   most severe first; explicitly state "no findings" per category otherwise. If any
   Critical/High: STOP — the finding goes to the founder before any merge conversation.

5. Optional depth: invoke the security-guidance plugin's `/security-review` skill for the
   full-branch pass; this command is the fast repo-specific gate, not a replacement.
