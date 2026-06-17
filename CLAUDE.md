# CLAUDE.md

Guidance for Claude Code (and other AI agents) working in this repository.

## What this is

**UMI Exchange** — a reference implementation of the **UMI Protocol v0.1** (Core conformance):
an open-source platform for coordinating reciprocal exchange (mutual aid) in communities — a
Catholic parish, a secular mutual-aid group, a disaster-relief network, a timebank. Built so any
such community can adopt it as a starting point and re-skin it per community.

Stack: **Django 5.2** · PostgreSQL (prod/CI) / SQLite (local default) · Redis (optional) ·
HTMX + Alpine.js + Tailwind (compiled `static/css/output.css`) · WhiteNoise · gunicorn ·
django-q2 (optional background tasks) · Argon2 password hashing.

## Commands

```bash
make run        # runserver
make test       # pytest (see ENCRYPTION_KEY note below)
make migrate
make shell
make lint       # ruff check . && ruff format --check .   (mirrors CI)
make format     # ruff format .
```

- **Run the suite:** `pytest -q`. Single test: `pytest tests/test_views.py::TestPublicViews::test_landing_page`.
- **Encryption tests need a key.** Crypto/envelope tests require `ENCRYPTION_KEY` (or `ENCRYPTION_KEYS`) set, e.g.:
  ```bash
  export ENCRYPTION_KEY="$(python -c 'from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())')"
  ```
  (The `apps/casework` conftest sets one automatically for its tests; top-level runs may need it exported.)
- **Run against Postgres locally** (matches CI — see "SQLite vs Postgres" below):
  ```bash
  DATABASE_URL="postgres://user:pass@127.0.0.1:5432/umi_test" pytest -q
  ```
- **Lint config:** ruff, `line-length = 120`, `target-version = py312`, rules `E,F,I,N,W`. Migrations ignore `E501`; settings modules ignore `F403/F405`.
- **Deploy check:** `DJANGO_SETTINGS_MODULE=config.settings.production SECRET_KEY=… ENCRYPTION_KEY=… ALLOWED_HOSTS=… python manage.py check --deploy` → must be **0 issues**.
- **CSS:** `output.css` is compiled, committed Tailwind — regenerate with
  `npx tailwindcss@3.4.14 -i static/css/input.css -o static/css/output.css --minify`. Never hand-edit it.

## Settings

`config/settings/{base,development,production}.py`, selected by `DJANGO_SETTINGS_MODULE`
(tests + local default to `development`).

- DB via `DATABASE_URL` (django-environ); defaults to `sqlite:///db.sqlite3`.
- Field encryption keys: `ENCRYPTION_KEYS` (list, primary first) or legacy `ENCRYPTION_KEY`.
- **`production.py` fails fast** (`ImproperlyConfigured`) on an insecure/empty `SECRET_KEY` or an
  empty `ENCRYPTION_KEY` — by design. It also sets HSTS, SSL redirect, secure cookies, `DEBUG=False`.
- Dev relaxes those, so `check --deploy` under *development* reports the expected W004/W008/W012/W016/W018 — not action items.

## Architecture

12 project apps under `apps/`:

- **Lake 1 — mutual aid:** `communities` (Community/Member/Category, feed, per-community theming),
  `needs`, `offers`, `matches` (propose→accept→fulfill), `households`, `notifications`, `dashboard`,
  `accounts` (auth + rate limiting).
- **Lake 2 — casework:** `casework` (CaseFile/CaseNote/FollowUp/WarmHandoff/CaseAccessGrant), backed by
  `people` (Person) and `consent`.
- **Cross-cutting:** `audit` (append-only log), `health` (load-balancer probe).

Key mechanisms (respect these — they're load-bearing):

- **State machines:** entities change state only via `transition_to(...)` (`StateMachineMixin`);
  invalid transitions raise `ValidationError`. Views map conflicts → HTTP 409.
- **Append-only audit (§8.3):** `AuditLog` refuses UPDATE/DELETE; a Postgres migration `REVOKE`s
  them too. Write via `apps.audit.services.emit(action, resource, …)` or `AuditLog.log(...)`.
  IP addresses are stored **salted-SHA-256**, never raw; client IP comes from the trusted
  `X-Real-IP` (reverse proxy), never the spoofable left-most `X-Forwarded-For`.
- **Encryption:** `apps/people/crypto.py`. Two layers: *direct-KEK* (`encrypt_str`/`decrypt_str`,
  MultiFernet over the KEK list → rotation-ready) and *envelope* (`envelope_encrypt_str` → per-record
  DEK wrapped by the KEKs → enables crypto-shred). **Always read/write encrypted fields through their
  model property** (e.g. `Need.on_behalf_of_name`, `CaseFile.summary`) — never touch the raw `*_enc`
  / `*_enc_dek` columns directly, and never pass pre-encrypted bytes to a setter.
- **KEK rotation:** `manage.py rotate_keks` re-wraps every envelope DEK; register new
  `(app, Model, dek_field)` tuples in its `ENVELOPE_DEK_FIELDS`.
- **Casework sensitivity:** `apps/casework/access.py` `case_access()` is the single authorization
  matrix; `SensitiveSessionMiddleware` enforces 4-hour re-auth on casework decrypt views.
- **CSPRNG everywhere:** join/household codes use `secrets.choice`; health token compares with
  `constant_time_compare`.
- **Concurrency:** contended writes use `select_for_update`; double-accept → 409.

## Gotchas (these have bitten us)

- **SQLite ≠ Postgres.** SQLite silently ignores `select_for_update`; Postgres enforces it. In
  particular `select_for_update()` + `select_related()` of a **nullable** FK (an outer join) makes
  Postgres raise *"FOR UPDATE cannot be applied to the nullable side of an outer join."* Use
  `select_for_update(of=("self",))` to lock only the base row (see `apps/matches/views.py`).
  Always verify DB-touching changes against Postgres, not just the local SQLite default.
- **`skip_locked`** is a no-op on SQLite. Avoid pairing it with a `pk__gt` cursor (can skip a locked
  row permanently — see `rotate_keks`).
- **Encryption tests** fail without a key set (see Commands).
- **WhiteNoise manifest storage** in prod requires `collectstatic`; serve over HTTPS.
- **Django 6.0:** use `CheckConstraint(condition=…)`, not `check=`.
- **Don't hand-edit `output.css`** (generated, minified) — recompile instead.

## Workflow conventions

- **Branch, don't push to `main` without explicit approval.** Verify before merge:
  `ruff check . && ruff format --check .` · `makemigrations --check` · `pytest` (ideally on Postgres
  too) · `check --deploy` (prod) = 0 issues.
- **Safe-fail defaults:** archive not delete, draft not send, read not edit. Never send real
  email/SMS, spend money, delete data, or touch live community data without explicit approval.
- **Sensitive personal data** (real names, parish specifics, settlement details) stays out of git.
- **Tests** use `factory_boy` factories in `tests/conftest.py` and `apps/casework/tests/conftest.py`
  (`world`, `make_note`, `auth`, `u` fixtures). Add a regression test with every fix.

## Project roadmap

See `docs/INTEGRATION-PLAN.md` for the staged build (Lakes, envelope encryption, etc.). Steps 1–3
(people/§10, casework, `needs` envelope encryption) are built and on `main`. Casework envelope
encryption (extending Step 3) and its Stage E contract live in separate, gated PRs.
