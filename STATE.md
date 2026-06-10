# UMI Exchange — Current State

> Authoritative project snapshot. Paste this into a fresh chat (or share the
> file) so an assistant compares against ground truth instead of guessing.
> Reflects `main` @ `294b13b` (2026-06-09).

## Protocol
- **UMI Protocol v0.1, Core conformance.**
- **Entities implemented:** `umi:Need`, `umi:Offer`, `umi:Match`, `umi:Consent`.
- **Not implemented:** referrals, attestations. (A trust-badge UI component
  exists but is a placeholder — no attestation model/logic behind it.)
- **Match state machine:** `proposed → accepted | cancelled | expired`;
  `accepted → fulfilled | unfulfilled | cancelled`. Terminal states enforced.
- **Security / consent rules enforced in code:**
  - Contact info revealed only after acceptance (§8.2), to participants/coordinators.
  - Self-match prevention (§8.6): proposer ≠ requester **and** offer-owner ≠ requester.
  - Authorization on match updates: only requester / offer-owner / proposer
    (direct volunteer) / coordinator; others get **HTTP 403**.
  - Race handling (§8.7): `SELECT FOR UPDATE` locks the **Need**; second
    concurrent accept → **HTTP 409**.
  - Append-only audit log (§8.3): model-level `save`/`delete` blocks + a Postgres
    `REVOKE` migration; IPs SHA-256 hashed; **contact-info disclosures are audited**.
  - Match status changes persist an optional **sanitized note**.
  - Join codes generated with a **CSPRNG** (`secrets`); health-check token compared
    in constant time.
  - Production **refuses to boot** on an insecure `SECRET_KEY` / empty `ENCRYPTION_KEY`.

## Codebase
- **Stack:** Django 5.x, PostgreSQL, Redis, HTMX, Alpine.js, Tailwind CSS,
  WhiteNoise, gunicorn. Argon2 password hashing (`argon2-cffi`, PBKDF2 fallback).
- **11 Django apps:** accounts, audit, communities, consent, dashboard, health,
  households, matches, needs, notifications, offers.
- **Features:** needs, offers, matches (propose / accept / fulfill / cancel),
  consents (list / revoke), community feed (HTMX filter / search / refresh),
  coordinator dashboard + **CSV export**, notifications, append-only audit log,
  households (CSPRNG join codes), QR community-join, optional **2FA**
  (`django-two-factor-auth`, off by default), health endpoint, a public landing
  page, and a **Category** model under `communities`.
- **Optional background queue:** django-q2 (added to `INSTALLED_APPS` only if
  installed; `Q_CLUSTER` configured with the ORM broker — no Redis required).
- **Migrations:** present for all model apps (audit has `0002` append-only;
  dashboard has none — no models).

## Visual design — warm "parish atmosphere"
- Background `#FDFBF7` with a soft top-centre radial gradient; warm-brown ink `#2C2A29`.
- Accents: deep green `#2B5E2B` (primary), soft gold `#C49A3C` (secondary).
- Serif headings (**Lora → Georgia** fallback; **no external webfont loaded**),
  Open Sans body, generous line-height.
- 960px max content width; translucent **blurred header** with a hairline border.
- Bulletin-style cards: warm surface, **green (need) / gold (offer)** left border;
  urgency shown as **muted colour dots with dark-grey text**.
- **Green pill buttons** (primary solid / secondary outline).
- **Calm micro-interactions only:** contact-reveal crossfade (no rotation),
  timeline checkmark fade (no scaling), refresh spinner, toast slide-in/out,
  empty-state SVG (single-stroke church) fade-in. All respect `prefers-reduced-motion`.
- Tailwind compiled to `static/css/output.css` (config carries the parish palette);
  served via WhiteNoise `CompressedManifestStaticFilesStorage` (**needs
  `collectstatic`**; `DEBUG` defaults to `False`).

## Testing / CI / Deploy
- **73 tests passing**; `ruff check` + `ruff format` clean; `make lint` runs both.
- CI: `.github/workflows/ci.yml` (lint, tests, build); `deploy.yml` (GHCR + SSH).
- Deploy: `Dockerfile` + `docker-compose.yml` (+ `docker/docker-compose.prod.yml`,
  `Caddyfile`, `Caddyfile.prod`, logrotate); scripts: `harden.sh`, `backup.sh`,
  `restore.sh`, `security_check.sh`, `setup_hardening.sh`.

## NOT in this codebase (guard against scope creep)
The following belonged to an earlier "Parish Aid Board / Lake 1" lineage and are
**not** part of UMI Exchange — do not assume or reintroduce them: Stripe billing,
Twilio SMS, Chart.js dashboards, PWA manifest/service worker, blog, scheduled
email digests (only an `email_digest` *config key* exists), and an account-deletion
flow.

## Repo state / open items
- All feature work is merged into `main` (security fixes, lint/test cleanup,
  parish redesign, contact-read auditing + match notes).
- Stale branches still exist pending deletion — repo is **not** fully cleaned up yet.
- **St. Patrick pilot:** environment scaffolding exists; implementation playbook
  not yet generated.
