# Contributing to UMI Exchange

Django 5.2 · PostgreSQL (prod/CI) / SQLite (local default) · Redis (optional) · HTMX + Alpine +
Tailwind · WhiteNoise · gunicorn · django-q2 (optional) · Argon2. Server-rendered HTML; **no REST API**.

## Setup on a fresh clone

```bash
git clone <repo> && cd umi-exchange
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

# REQUIRED: field-encryption key. Envelope/crypto tests FAIL CLOSED without it
# (production refuses to boot without it, by design). Generate one for local use:
export ENCRYPTION_KEY="$(python -c 'from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())')"

python manage.py migrate
python manage.py runserver        # http://127.0.0.1:8000/
```

## Running tests — read this or they fail

```bash
export ENCRYPTION_KEY="$(python -c 'from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())')"
pytest -q
```

Two gotchas that will bite a fresh clone:

1. **`ENCRYPTION_KEY` must be exported.** The envelope/crypto suites fail closed without it. (The
   `apps/casework` tests set one in their conftest; top-level runs need it exported.)
2. **SQLite ≠ Postgres — verify DB-touching changes on Postgres.** SQLite (the local default)
   **silently ignores `select_for_update`**; Postgres enforces it (and rejects `FOR UPDATE` on the
   nullable side of an outer join — use `select_for_update(of=("self",))`). CI runs on **Postgres 16**:
   ```bash
   DATABASE_URL="postgres://user:pass@127.0.0.1:5432/umi_test" pytest -q
   ```

**CSS — never hand-edit `static/css/output.css`** (it's compiled + minified). Recompile:
```bash
npx tailwindcss@3.4.14 -i static/css/input.css -o static/css/output.css --minify
```

## Verify gate (mirrors CI; pass all before a PR)

`ruff check . && ruff format --check .` · `python manage.py makemigrations --check` ·
`bandit` + `semgrep --baseline-commit main` (no NEW findings) · **full `pytest` on Postgres** ·
`DJANGO_SETTINGS_MODULE=config.settings.production … manage.py check --deploy` = **0 issues**.

Branch, don't push `main`. Add a regression test with every fix.

## App map — 14 project apps (+ `apps/common`)

> Count comes from `INSTALLED_APPS` (`config/settings/base.py`) / the real `apps/` dir — **14 project
> apps**. `apps/common` is a 15th *directory* but **not** an installed app: it's the shared
> `StateMachineMixin` module (`apps/common/state.py`), re-exported by `casework`/`tags`.

**Lake 1 — mutual aid:** `communities` (Community/Member/Category, feed, per-community theming) ·
`needs` · `offers` · `matches` (propose→accept→fulfill) · `households` · `notifications` · `dashboard` ·
`accounts` (auth + rate limiting) · `tags` (member tags & clergy verification).

**Lake 2 — casework:** `casework` (CaseFile/CaseNote/FollowUp/WarmHandoff/CaseAccessGrant) ·
`people` (Person) · `consent`.

**Cross-cutting:** `audit` (append-only log) · `health` (load-balancer probe).
**Not an app:** `apps/common` — `StateMachineMixin`.

## Security conventions (load-bearing — respect these)

- **Audit — `apps.audit.services.emit(action, resource, *, user, request, details)`.** Action names are
  **dotted and ≤32 chars** (`emit` *raises* if longer, never truncates). **No PII in `details`** (ids /
  enums only — never titles, names, contact values). `user` is stored only when authenticated (else NULL
  = system event). Client IP is taken from the trusted **`X-Real-IP`** (reverse proxy) and stored as a
  **salted SHA-256** — never the spoofable left-most `X-Forwarded-For`, never raw.
- **State machines — change state only via `transition_to(...)`.** It raises on an invalid transition,
  but **the exception type differs**: `apps/matches` raises a plain `ValidationError`; `casework` and
  `tags` (via `apps/common/state.py`) raise **`TransitionConflict`** (a `ValidationError` subclass with
  `status_code=409`). So an `except TransitionConflict` **must come before** any `except ValidationError`.
- **Encryption — `apps/people/crypto.py`, two layers.** *Direct-KEK* (`encrypt_str`/`decrypt_str`,
  MultiFernet over the `ENCRYPTION_KEYS` list → rotation-ready) and *envelope* (per-record **DEK** wrapped
  by the KEKs → enables **crypto-shred**: delete the DEK and the ciphertext is permanently opaque even
  with the KEK). **Always read/write encrypted fields through their model property** (e.g.
  `Need.on_behalf_of_name`, `CaseFile.summary`) — **never** touch the raw `*_enc` / `*_enc_dek` columns,
  and never pass pre-encrypted bytes to a setter. Key rotation: `docs/runbooks/key-rotation.md`.
- **Append-only audit (§8.3).** `AuditLog` refuses `UPDATE`/`DELETE` at the model layer **and** via a
  Postgres `REVOKE` migration — an attacker can't edit or erase the trail. No PII in it.

## Routes

There's **no OpenAPI/Swagger** (no REST API; DRF was removed in PR #16). The route contract is
**[`docs/routes.md`](routes.md)**, generated from the live URLconf — regenerate with
`.venv/bin/python scripts/gen_routes.py > docs/routes.md` (and diff in review so it can't drift). The
`Auth` column is the view's `LoginRequiredMixin`; finer role-gating lives in the view's logic
(`dispatch()` / `get_object()` / `case_access()`), so read the view for coordinator/admin/owner rules.
