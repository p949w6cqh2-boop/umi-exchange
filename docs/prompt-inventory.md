# Prompt Inventory

> A catalog of every prompt written for the AGI ("the builder") across this project, grouped by
> category. Each entry has a short title, what it was used for, an approximate date, and the output
> it produced. The intent: anyone picking up this project can re-run, audit, or extend the build by
> sending these prompts in the recommended order — copy-paste, no archaeology required.
>
> **How to use:** prompts are written to be sent one at a time to the builder. After each, the
> human verifies the output (the "verify-before-trust" rule) and only then sends the next. Outputs
> below describe what *was* produced and integrated onto `main` (current head `00ead8b`).

## Table of contents
1. [Recommended order to send prompts in](#1-recommended-order-to-send-prompts-in)
2. [Agent instructions](#2-agent-instructions)
3. [System design](#3-system-design)
4. [Code generation & security](#4-code-generation--security)
5. [Testing](#5-testing)
6. [Documentation](#6-documentation)
7. [Deployment & operations](#7-deployment--operations)
8. [Fix prompts (verified flaws)](#8-fix-prompts-verified-flaws)
9. [Future / R&D](#9-future--rd)

---

## 1. Recommended order to send prompts in

Send top-to-bottom. Each step assumes the previous one landed and was verified.

| # | Prompt | Category | Why this order |
|---|---|---|---|
| 1 | Master agent preamble (keyring) | Agent instructions | Sets safety rails before any code is written. |
| 2 | UMI Protocol v1.0 core design | System design | Defines entities/state machines everything else builds on. |
| 3 | Lakes 2–8 design | System design | Layers casework + future lakes onto the core. |
| 4 | Federation design | System design | Cross-community design; depends on core + lakes. |
| 5 | Security-hardening | Code gen & security | Harden the generated core before adding data. |
| 6 | Encryption & privacy (envelope) | Code gen & security | Crypto-shred + contact revelation; needs hardened base. |
| 7 | Robustness & cleanup | Code gen & security | Race handling, expiry, dead-code sweep. |
| 8 | Test-hardening | Testing | Lock the matrix down once behavior is stable. |
| 9 | Contributor/routes/key-rotation docs | Documentation | Document the now-stable system. |
| 10 | Ops & resilience | Deployment & ops | Production settings, health, workers. |
| 11 | Fix prompts (§8, by severity) | Fix prompts | Address verified flaws, 🔴 first. |
| 12 | Mobile + LLM classifier | Future / R&D | Only after the web app is solid. |

---

## 2. Agent instructions

### 2.1 Master agent preamble ("the keyring")
- **Used for:** the standing system prompt prepended to every builder session — defines what the
  agent may and may not do without asking.
- **Approx date:** 2026-06-13 (refined throughout).
- **Output:** the operating contract followed for the whole build — *safe-fail* defaults (archive
  not delete, draft not send, read not edit, branch not main); never send real email/SMS, spend
  money, delete data, or touch live parish data without explicit approval; sensitive personal data
  stays out of git (local-only `inbox/private.md`). "Push directly to main — must ask."

---

## 3. System design

### 3.1 UMI Protocol v1.0 core design
- **Used for:** the foundational spec — Need / Offer / Match / Consent entities, state machines,
  contact-revelation rules (§8.2), append-only audit (§8.3), self-match prevention (§8.6),
  concurrency/locking (§8.7).
- **Approx date:** 2026-06-13.
- **Output:** the 12-app Django project on `main` (accounts, audit, communities, consent,
  dashboard, health, households, matches, needs, notifications, offers, people) with
  `transition_to()` state machines and the audited match lifecycle.

### 3.2 Lakes 2–8 design (AGI's design doc)
- **Used for:** layering casework (Lake 2) and the roadmap for later lakes onto the core. The
  builder's own design doc was preferred over a hand-written one.
- **Approx date:** 2026-06-14.
- **Output:** the `casework` + `people` apps — case files, sensitivity levels, the `case_access()`
  authorization matrix (`apps/casework/access.py`), the 4-hour sensitive-session re-auth
  middleware, and offline visit drafts.

### 3.3 Federation design
- **Used for:** cross-community sharing/discovery design (how independent parishes interoperate
  without a central authority).
- **Approx date:** 2026-06-14.
- **Output:** design captured for a future lake; not yet implemented on `main`.

---

## 4. Code generation & security

### 4.1 Security-hardening
- **Used for:** hardening the generated core — CSPRNG join codes, constant-time health token,
  production fail-fast on insecure `SECRET_KEY` / empty `ENCRYPTION_KEY`, salted IP hashing in the
  audit model, Argon2 password hashing.
- **Approx date:** 2026-06-14.
- **Output:** `config/settings/production.py` boot guards; `apps/audit/models.py` salted
  `ip_hash`; CSPRNG join codes; Argon2 configured.

### 4.2 Encryption & privacy (envelope)
- **Used for:** envelope encryption (per-record DEK wrapped by a MultiFernet KEK list) to enable
  crypto-shred, plus the `on_behalf_of_name` read/write path and contact revelation after
  acceptance.
- **Approx date:** 2026-06-15.
- **Output:** `people.crypto` (direct-KEK + envelope), `Need.on_behalf_of` envelope fields, the
  `rotate_keks` management command, and the Postgres `REVOKE` migration making audit append-only.

### 4.3 Robustness & cleanup
- **Used for:** concurrency correctness (`SELECT FOR UPDATE` → 409 on double-accept), stale-need
  expiry emitting `match.expired` per match, and removing dead/duplicate code paths.
- **Approx date:** 2026-06-15.
- **Output:** the 409 race path in the match accept view, `expire_stale_needs` in
  `apps/needs/tasks.py` (+ regression test), and removal of the superseded
  `set_on_behalf_of`/`get_on_behalf_of` helpers.

---

## 5. Testing

### 5.1 Test-hardening
- **Used for:** locking down the authorization matrix and the full user flow with the Django test
  client (register → join → post need → propose → accept → fulfill), plus negative cases
  (self-match 400, non-participant 403, concurrent accept 409).
- **Approx date:** 2026-06-15.
- **Output:** the test suite that today reports **157 passed, 1 skipped** (see
  `docs/sandbox-report.md`), including `tests/test_match_views.py`, `tests/test_views.py`,
  `tests/test_theming.py`, and `tests/test_needs_expiry.py`.

---

## 6. Documentation

### 6.1 Contributor guide / routes / key-rotation
- **Used for:** developer-facing docs — how to set up the project, the route map, and the KEK
  rotation runbook.
- **Approx date:** 2026-06-15.
- **Output:** project docs and the key-rotation procedure backing the `rotate_keks` command.

---

## 7. Deployment & operations

### 7.1 Ops & resilience
- **Used for:** production settings (HSTS, SSL redirect, secure cookies, `DEBUG=False`),
  WhiteNoise manifest static storage, gunicorn, django-q2 ORM-broker workers, and health checks.
- **Approx date:** 2026-06-15.
- **Output:** `config/settings/production.py` (passes `check --deploy` with 0 issues under prod
  settings), the `health` app, and worker/static configuration.

---

## 8. Fix prompts (verified flaws)

These were written after auditing the codebase (and double-checking a Gemini-supplied flaw list
against the real source). Send 🔴 first. Each maps to a row in
`docs/sandbox-report.md` §5.

### 8.1 🔴 Salt the audit-service IP hash
- **Used for:** fixing `apps/audit/services.py` `ip_hash()`, which uses an **unsalted** SHA-256
  (rainbow-tableable) — a regression vs. the salted hash in `apps/audit/models.py`.
- **Approx date:** 2026-06-16.
- **Output:** prompt written (fix not yet applied — `main` unchanged per task constraints).

### 8.2 🔴 Stop trusting `X-Forwarded-For`
- **Used for:** fixing client-spoofable client-IP extraction in `apps/accounts/ratelimit.py` and
  `apps/audit/services.py` (rate-limit bypass + audit IP poisoning).
- **Approx date:** 2026-06-16.
- **Output:** prompt written.

### 8.3 🟠 Re-gate follow-ups by current case access
- **Used for:** `MyFollowUpsView` (`apps/casework/views.py`) filters by `assigned_to` + community
  but does not re-check `case_access()`.
- **Approx date:** 2026-06-16.
- **Output:** prompt written.

### 8.4 🟠 Encrypt offline draft note bodies
- **Used for:** `static/casework/visit_offline.js` stores draft note **body** (PII) as plaintext in
  IndexedDB until sync.
- **Approx date:** 2026-06-16.
- **Output:** prompt written.

### 8.5 🟠 Move casework PII onto envelope encryption
- **Used for:** casework PII uses direct-KEK (no crypto-shred) while the rest of the system uses
  envelope encryption.
- **Approx date:** 2026-06-16.
- **Output:** prompt written.

### 8.6 🟡 Audit + guard household-membership reassignment
- **Used for:** `apps/households/views.py` does an unguarded, unaudited mass `member_set.update()`.
- **Approx date:** 2026-06-16.
- **Output:** prompt written.

### 8.7 🟡 Paginate the feed at the DB layer
- **Used for:** `FeedView.get_queryset` loads all needs + offers into memory and sorts before
  paginating.
- **Approx date:** 2026-06-16.
- **Output:** prompt written.

### 8.8 🟡 Make `rotate_keks` skip-lock safe
- **Used for:** `select_for_update(skip_locked=True)` + `pk__gt` paging can permanently skip a
  locked row.
- **Approx date:** 2026-06-16.
- **Output:** prompt written.

### 8.9 🟡 Django 6.0 `CheckConstraint` deprecation
- **Used for:** `CheckConstraint(check=…)` → `condition=` in `apps/casework/models.py`.
- **Approx date:** 2026-06-16.
- **Output:** prompt written.

> **Not flaws (do not write fixes):** the alleged IntegrityError "transaction crash" (saves run in
> autocommit) and CSRF-cookie `HttpOnly` (Django default by design).

---

## 9. Future / R&D

### 9.1 Mobile (React Native) + LLM need classifier
- **Used for:** designing a mobile client and an LLM-assisted classifier that routes free-text
  needs to categories.
- **Approx date:** 2026-06-16.
- **Output:** design/prompt captured for later; not implemented.
