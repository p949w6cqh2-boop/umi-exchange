# UMI Exchange — Bundle Integration Plan

**Source of truth:** `umi-exchange-FULL-BUNDLE.md` (65 `### FILE:` + 7 `### EDIT:` blocks).
⚠️ It exists only as an upload — re-supply it each session (the sandbox is ephemeral).
**Branch model:** one branch per step; verify gate before merge; nothing reaches `main` without explicit approval.

## ✅ Step 1 — DONE (`claude/lake2-step1`)
`apps.people` + the §10 Lake-1 improvement *files* are present and migrating; the audit
`0002`→`0003` migration clash is resolved; consent kept `granted_to` (D1); 78 tests pass.
**Not yet activated:** feed-search wiring, rate-limit middleware, `require_role`, and the
§10 targeted tests.

## Step 2 — Casework (the goal)
**Write (FILE blocks):** `apps/casework/` (26 files incl. `models, views, forms, urls, admin,
state, access, audit[shim], notify, middleware, tasks, apps, __init__`, and
`migrations/{__init__,0001_initial,0002_widen_audit_action}`), `templates/casework/` (15),
`static/casework/visit_offline.js`.
**Wire (§0 edits):**
- `config/settings/base.py` → add `apps.casework.middleware.SensitiveSessionMiddleware` to
  `MIDDLEWARE` *after* `AuthenticationMiddleware`. (`apps.people`/`apps.casework` already in
  `INSTALLED_APPS` from Step 1 — only the casework middleware line remains.)
- `config/urls.py` → add
  `path("c/<slug:slug>/cases/", include(("apps.casework.urls","casework"), namespace="casework"))`
  **above** the existing `c/` communities include.
**Apply (3 casework EDITs, on top of the FILE versions):** `views.py` ×2 (structured-grantee
consent + throttle the 3 sensitive endpoints via `accounts.ratelimit`), `forms.py` ×1
(consent picker prefers this community's grantee).
**Migrations:** `casework 0001`, `casework 0002_widen_audit_action` — **redundant but safe**
(re-widens audit Postgres-side; idempotent; no-op on SQLite since our `audit 0003` already did it).
**Verify gate:** `py_compile` → `manage.py check` → `makemigrations --check` →
`migrate people casework` → `ENCRYPTION_KEY=<set> pytest apps/casework/` → `ruff`.
**Risks:** (1) `base.html` block names vs parish base — likely first break; (2) `ENCRYPTION_KEY`
must be set in test env (our default empty) — confirm casework conftest sets it; (3) re-auth
middleware is global but scopes to the `casework` namespace — confirm via full suite; (4)
service-worker route `/cases/visit/sw.js`.

## Step 2b — Finish §10 activation (small EDITs + tests)
Wire `needs.search.apply_search()` into `FeedView`'s `q`; add the auth-path rate-limit
middleware; `require_role` helper (§10.8); pull the bundle's §10 tests so `covers()`, the
limiter, and the expiry audit are actually proven.

## Step 3 — Envelope encryption (highest blast radius — own branch)
EDIT `needs/models.py` (`on_behalf_of` → envelope via `on_behalf_of_name` + `_dek` column),
`needs/0003_on_behalf_envelope.py`, `management/commands/{migrate_on_behalf_envelope,
shred_on_behalf,rotate_keks}.py`; call-site sweep `grep -rn on_behalf_of`; staged 5-phase
rollout, each reversible (`--to-legacy`); decide `ENCRYPTION_KEYS` (list) vs legacy
`ENCRYPTION_KEY`.

## Step 4 — `CLAUDE.md` at repo root
Only after Steps 2–3 are real (else it asserts DESIGNED-as-BUILT). Put `FULL-BUNDLE.md` in `docs/`.

## Fold in 3 pre-existing flaws (independent of the bundle)
- 🟠 #1 `needs/tasks.py:31` bulk-`.update()`s proposed matches to `expired` with **no audit** —
  now fixable via `emit("match.expired", m, …)`. Do during Step 2b.
- 🟠 #2 `FeedView` loads all rows into memory before paginating — fix when wiring search.
- 🟡 #3 Household join overwrites all memberships, unaudited.

## Open governance decision (not code)
Manual §5.8 72-hour erasure vs. append-only. Honest path = crypto-shred via Step 3 envelope;
until shipped, the **privacy policy must state actual retention**, not claim §5.8 compliance.
