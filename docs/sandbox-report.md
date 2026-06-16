# Sandbox Validation Report

> **Read-only** validation of the current system. No production code changed, nothing deployed,
> no schema altered. Run on branch `claude/sandbox-and-inventory` (off `main` @ `00ead8b`).
> Date: 2026-06-16. Env: Python 3.11, venv, SQLite dev DB, `ENCRYPTION_KEY` set for crypto tests.

## Table of contents
1. [Results at a glance](#1-results-at-a-glance)
2. [User-flow simulation](#2-user-flow-simulation)
3. [`check --deploy`](#3-check---deploy)
4. [Warnings & deprecations](#4-warnings--deprecations)
5. [Needs attention before next deployment](#5-needs-attention-before-next-deployment)
6. [How to reproduce](#6-how-to-reproduce)

## 1. Results at a glance
| Check | Command | Result |
|---|---|---|
| Test suite | `pytest -q` | ✅ **157 passed, 1 skipped** |
| User flow | `pytest tests/test_match_views.py tests/test_views.py` | ✅ **35 passed** |
| Lint | `ruff check .` | ✅ clean |
| Format | `ruff format --check .` | ✅ 171 files clean |
| Migrations consistent | `makemigrations --check --dry-run` | ✅ no changes detected |
| Migration plan | `migrate --plan` | ✅ no pending operations |
| Deploy check (prod settings) | `check --deploy` (production.py + secrets) | ✅ **0 issues** |
| Deploy check (dev settings) | `check --deploy` (development.py) | ⚠️ 6 warnings — expected (see §3) |

## 2. User-flow simulation
The full core flow is exercised by the test suite via Django's test `Client`
(register → join community → post need → propose match → accept → fulfill), and it **passes (35
tests)**. Specifically verified:
- **Auth**: register, login (rate-limited), join community.
- **Match lifecycle**: propose → accept → fulfill; self-match rejection (400); non-participant 403;
  concurrent double-accept → 409.
- **Contact revelation**: hidden before acceptance, revealed after (participants + coordinator).
- **Audit**: a `read`/`match_contact` row is written on disclosure; status changes audited.
> No standalone script was added (to honor "don't modify code"); the existing client-based tests
> *are* the flow simulation.

## 3. `check --deploy`
- **Under production settings → 0 issues.** (`DJANGO_SETTINGS_MODULE=config.settings.production`
  with real `SECRET_KEY`/`ENCRYPTION_KEY`.) Confirms `production.py` sets HSTS, SSL redirect,
  secure session/CSRF cookies, `DEBUG=False`, and the insecure-key boot guard.
- **Under development settings → 6 warnings** (W004 HSTS, W008 SSL redirect, W009 SECRET_KEY,
  W012 session-cookie-secure, W016 CSRF-cookie-secure, W018 DEBUG). These are **expected**: dev
  settings intentionally relax these, and `production.py` addresses every one. Not action items.

## 4. Warnings & deprecations
- **2 pytest warnings — `RemovedInDjango60Warning`**: `CheckConstraint(check=…)` in
  `apps/casework/models.py` should become `condition=` before Django 6.0. (Works today.)
- **1 skipped test**: an environment-gated casework test (skips when its precondition isn't met).
- No runtime errors, no unexpected deprecations.

## 5. Needs attention before next deployment
**Operational (must do at deploy time):**
- Set a real `SECRET_KEY` and `ENCRYPTION_KEY` (production refuses to boot otherwise — by design).
- Run `collectstatic` (WhiteNoise manifest storage) and serve over HTTPS (Caddy).

**Known flaws (verified real; fixes queued as AGI prompts — see `docs/prompt-inventory.md`):**
| Severity | Item | Status |
|---|---|---|
| 🔴 | Unsalted IP hash in `audit/services.emit` (rainbow-tableable) | prompt written |
| 🔴 | `X-Forwarded-For` spoofing → rate-limit bypass / audit IP poisoning | prompt written |
| 🟠 | Follow-ups not re-gated by current case access (`MyFollowUpsView`) | prompt written |
| 🟠 | Offline draft **note body** stored plaintext in IndexedDB until sync | prompt written |
| 🟠 | Casework PII on direct-KEK (no crypto-shred) vs. envelope elsewhere | prompt written |
| 🟡 | Household join overwrites all memberships, unaudited | prompt written |
| 🟡 | Feed loads all rows into memory before paginating | prompt written |
| 🟡 | `rotate_keks` skip-lock can leave a row unrotated | prompt written |
| 🟡 | Django 6.0 `CheckConstraint` deprecation | prompt written |

**Not real (do not action):** IntegrityError "transaction crash" (saves run in autocommit) and
CSRF-cookie HttpOnly (Django default by design).

## 6. How to reproduce
```bash
git checkout claude/sandbox-and-inventory   # off main @ 00ead8b
python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
export ENCRYPTION_KEY="$(python -c 'from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())')"
ruff check . && ruff format --check .
python manage.py makemigrations --check --dry-run
python manage.py migrate --plan
python -m pytest -q
DJANGO_SETTINGS_MODULE=config.settings.production SECRET_KEY=… ENCRYPTION_KEY=… ALLOWED_HOSTS=… \
  python manage.py check --deploy
```
