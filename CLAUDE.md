# CLAUDE.md

Guidance for Claude Code (and other AI agents) working in this repository.

## What this is

**UMI Exchange** — a reference implementation of the **UMI Protocol v0.1** (Core conformance):
an open-source platform for coordinating reciprocal exchange (mutual aid) in communities — a
Catholic parish, a secular mutual-aid group, a disaster-relief network, a timebank. Built so any
such community can adopt it as a starting point and re-skin it per community.

Stack: **Django 5.2** · PostgreSQL (prod/CI) / SQLite (local default) · Redis (optional) ·
HTMX + Alpine.js + Tailwind (compiled `static/css/output.css`) · WhiteNoise · gunicorn ·
django-q2 (optional background tasks) · Argon2 password hashing (PBKDF2 fallback when the `argon2`
lib is absent — base settings never list a hasher whose library is missing, which would hard-crash
password verification).

## Design context

- **`PRODUCT.md`** — strategic: register (product), users, purpose, brand personality, anti-references,
  design principles, a11y. The "who/what/why."
- **`DESIGN.md`** — visual: "The Wellspring" system (water-teal + gold, warm neutrals, editorial
  noticeboard), tokens, typography, components, motion. The "how it looks."
- Read both before any UI work so changes stay on-brand. (Generated via `/impeccable init`.)

## gstack

If you have **gstack** installed, use its skills when working in this repo:

- **Web browsing:** always use the **`/browse`** skill for all web browsing. **Never** use
  `mcp__claude-in-chrome__*` tools.
- **Available gstack skills:** `/office-hours` · `/plan-ceo-review` · `/plan-eng-review` ·
  `/plan-design-review` · `/design-consultation` · `/design-shotgun` · `/design-html` · `/review` ·
  `/ship` · `/land-and-deploy` · `/canary` · `/benchmark` · `/browse` · `/connect-chrome` · `/qa` ·
  `/qa-only` · `/design-review` · `/setup-browser-cookies` · `/setup-deploy` · `/setup-gbrain` ·
  `/retro` · `/investigate` · `/document-release` · `/document-generate` · `/codex` · `/cso` ·
  `/autoplan` · `/plan-devex-review` · `/devex-review` · `/careful` · `/freeze` · `/guard` ·
  `/unfreeze` · `/gstack-upgrade` · `/learn`

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
- **Deploy check:** `DJANGO_SETTINGS_MODULE=config.settings.production SECRET_KEY=… ENCRYPTION_KEY=… BLIND_INDEX_KEY=… ALLOWED_HOSTS=… python manage.py check --deploy` → must be **0 issues** (`BLIND_INDEX_KEY` must differ from the encryption keys or production refuses to boot).
- **CSS:** `output.css` is compiled, committed Tailwind — regenerate with
  `npx tailwindcss@3.4.14 -i static/css/input.css -o static/css/output.css --minify`. Never hand-edit it.

## Settings

`config/settings/{base,development,production}.py`, selected by `DJANGO_SETTINGS_MODULE`
(tests + local default to `development`).

- DB via `DATABASE_URL` (django-environ); defaults to `sqlite:///db.sqlite3`.
- Field encryption keys: `ENCRYPTION_KEYS` (list, primary first) or legacy `ENCRYPTION_KEY`.
- **`production.py` fails fast** (`ImproperlyConfigured`) on an insecure/empty `SECRET_KEY`, an
  empty `ENCRYPTION_KEY`, or a missing/encryption-key-colliding `BLIND_INDEX_KEY` — by design.
  It also sets HSTS, SSL redirect, secure cookies, `DEBUG=False`.
- Dev relaxes those, so `check --deploy` under *development* reports the expected W004/W008/W012/W016/W018 — not action items.

## Architecture

14 project apps under `apps/`:

- **Lake 1 — mutual aid:** `communities` (Community/Member/Category, feed, per-community theming),
  `needs`, `offers`, `matches` (propose→accept→fulfill), `households`, `notifications`, `dashboard`,
  `accounts` (auth + rate limiting), `tags` (member tags & verification).
- **Lake 2 — casework:** `casework` (CaseFile/CaseNote/FollowUp/WarmHandoff/CaseAccessGrant), backed by
  `people` (Person) and `consent`.
- **Cross-cutting:** `audit` (append-only log), `health` (load-balancer probe).

Key mechanisms (respect these — they're load-bearing):

- **State machines:** entities change state only via `transition_to(...)`; invalid transitions raise
  `ValidationError` (subclass `TransitionConflict`), which views map to HTTP 409. `StateMachineMixin`
  lives in `apps/common/state.py` (used by `casework` and `tags`; `apps/casework/state.py` re-exports
  it); `matches` defines its own `transition_to` in `apps/matches/models.py`. Note `TransitionConflict`
  subclasses `ValidationError`, so an `except` for it must come **before** any `except ValidationError`.
- **Append-only audit (§8.3):** `AuditLog` refuses UPDATE/DELETE; a Postgres migration
  (`audit/migrations/0002_append_only.py`) `REVOKE`s `UPDATE, DELETE, TRUNCATE` on the table too, and
  `manage.py restrict_audit_permissions` additionally `REVOKE`s `UPDATE, DELETE` on `audit_auditlog`
  from the app's runtime DB role (defense-in-depth). Write via `apps.audit.services.emit(action, resource, …)`
  or `AuditLog.log(...)`.
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

## Repositories & working directory

Two separate repos sit side by side: **`/home/umi/umi-exchange`** (this app) and
**`/home/umi/umi-brain`** (Jasiah's markdown brain). Before ANY git or file-writing command,
print the current working directory and state which repo you're in — CWD drift has created
branches in the wrong repo. Prefer absolute paths or an explicit `cd /home/umi/umi-exchange &&`
prefix; never assume the shell is where you left it.

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
- **Multi-line `{# … #}` is NOT a Django comment.** The template lexer's `tag_re` has no `DOTALL`, so
  `{# #}` only comments to end-of-line. A `{#`/`#}` spanning newlines leaves any `{% … %}`/`{{ … }}`
  on the inner lines **live** — a usage-example `{% include %}` inside such a block self-recursed to a
  `RecursionError`. Use `{% comment %}…{% endcomment %}` for multi-line comments.
- **Never judge a test suite through a pipe.** `pytest … | tail` exits with the pipe's status, not
  the suite's — chained `&& git commit` has shipped red gates. Write the summary line to a file,
  **Read the pass count**, then commit as a separate command (a PreToolUse hook warns on this; the
  `/gate` skill encodes the whole verified sequence).
- **Never blanket-stage here** (`-A` / `.`). It sweeps in whatever untracked files happen to be in
  the tree — scratch scripts, another session's WIP, secrets — none of which you are looking at when
  you type it. That committed a foreign WIP file and broke CI lint twice (`hgit_sync.py`, archived
  2026-07-27: the file is gone, the failure mode is not). Stage explicit paths (hook-enforced by
  `~/.claude/hooks/git-guardrails.sh`, which matches at command position so quoting the phrase in a
  commit message no longer trips it).
- **`MatchFactory` auto-creates an Offer with its own offerer.** A volunteer-proposer test must pin
  `offer=None`, or the proposer is a stranger to the match and §8.2 correctly returns None.
- **CI runs with `ENCRYPTION_KEY=""`.** Tests that write envelope PII need the hermetic autouse
  fixture (`settings.ENCRYPTION_KEY = Fernet.generate_key().decode()` — copy from
  `apps/casework/tests/conftest.py`), or they pass locally and fail in CI.
- **Django ≥4.1 caches templates even in DEBUG** — restart `runserver` to see template edits.
- **Auth endpoints are IP-throttled** (register 3/min, login 5/min, django_ratelimit) — tests that
  POST them repeatedly need a distinct `REMOTE_ADDR` per request or they collect 429s.
- **Known flake:** `test_reauth_returns_429_after_five_attempts` straddles a fixed-window minute
  boundary (~rare). Green in isolation ⇒ flake; anything else failing ⇒ real.
- **Prefer Edit over sed/heredoc for source changes** — sed has mangled apostrophes and
  duplicated content here; any quote in the text makes sed fragile. Edit tool, always, for code.
- **Crontab/scheduled jobs: absolute paths + explicit `cd /abs/repo/path &&` prefix, written
  via heredoc** — the missing-prefix bug has recurred (nightly brain-refresh took several tries).
- **No smart/curly quotes in Python source or f-strings** — they read as normal quotes to the eye
  and cascade into suite-wide syntax failures (~70 tests once).
- **No Tailwind opacity modifiers on arbitrary CSS-var colors** — `text-[var(--umi-accent)]/70`
  fails to compile; use a solid color or a pre-mixed token instead.

## Workflow conventions

- **TDD for all feature work:** write the failing test first, implement to green, and verify on
  the real stack (PostgreSQL 16 + Redis) before opening a PR — SQLite green is not done.
- **PR review checklist (recurring critical bugs):** prod-guards keyed off the settings module
  name instead of `DEBUG`; probe/health endpoints that redirect; User-row data leaks across
  communities. Check all three before any merge.
- **Summarizing a PR/branch diff:** use the three-dot form `git diff main...HEAD --stat` and
  confirm the file list against the PR view — two-dot diffs have produced false "22 files
  deleted" reports.
- **Branch, don't push to `main` without explicit approval.** Verify before merge with the
  **`/gate` skill** (canonical sequence: ruff check + `ruff format .`, `makemigrations --check`,
  FULL `pytest` on Postgres with the count read from a file, bandit/semgrep vs `main`,
  `check --deploy` = 0).
- **Checkpoint long pipelines** (`/checkpoint`): for any multi-stage flow (spec→TDD→PR→merge→deploy,
  a migration series, a batch of merges), write a handoff checkpoint to `.claude/checkpoint.md`
  (gitignored scratch) BEFORE stage 1 and update it after every stage/merge — remaining stages +
  current branch/PR/CI state + the literal resume command — so a rate-limit or session cutoff leaves
  a recoverable point, not a half-finished merge.
- **Update `CHANGELOG.md` with every merge** — plain language, written for the people who use the
  board; all product copy checks against the brain's `identity/voice.md`.
- **Safe-fail defaults:** archive not delete, draft not send, read not edit. Never send real
  email/SMS, spend money, delete data, or touch live community data without explicit approval.
- **Ethics & safety posture:** `docs/ethics-and-safety.md` — the harm analysis and the hard,
  unchecked gate that must pass before any real community with real PII onboards (fictional data only
  until then).
- **Sensitive personal data** (real names, parish specifics, settlement details) stays out of git.
- **Tests** use `factory_boy` factories in `tests/conftest.py` and `apps/casework/tests/conftest.py`
  (`world`, `make_note`, `auth`, `u` fixtures). Add a regression test with every fix.

## Project roadmap

See `docs/INTEGRATION-PLAN.md` for the staged build (Lakes, envelope encryption, etc.). Steps 1–3
(people/§10, casework, `needs` envelope encryption) are built and on `main`. Casework envelope
encryption (extending Step 3) and its Stage E contract live in separate, gated PRs.
