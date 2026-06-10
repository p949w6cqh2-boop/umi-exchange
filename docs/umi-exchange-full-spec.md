# UMI Exchange — Full Specification (consolidated source of truth)

> Single reference document for an assistant designing **Lakes 2–8**. Reflects
> `main` @ `f78e2a0`. Sections 1, 3, and 4 are verified against the live
> codebase. **Section 2 (the Lakes 2–8 manual) must be pasted in — see the
> marked slot.**
>
> ⚠️ **Completeness note:** This file does **not** invent Lake 2–8 workflows. The
> authoritative descriptions of those lakes live in the "Lakes Complete Operating
> Manual," which must be pasted into Section 2 below. Everything outside Section 2
> is ground truth from the repository.

---

## 1. Current state (verified — from root `STATE.md`)

# UMI Exchange — Current State

> Authoritative project snapshot. Reflects `main`.

### Protocol
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

### Codebase
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

### Architecture conventions (mirror these in every new lake)
- **Endpoints are server-rendered Django views + HTMX**, NOT REST. DRF is
  installed but unused. Community-scoped routes under `/c/<slug>/…` with named
  routes; UUID primary keys; errors return real status codes (403 / 409 / 400),
  with HTMX requests also getting an `HX-Trigger: showToast` toast.
- **Multi-tenant by `communities.Community`**, acted on by `communities.Member`
  (FK user+community, `role ∈ {member, coordinator, admin}`, `is_active`).
- **Models:** `UUIDField` pk (`default=uuid.uuid4`), explicit `Meta.db_table`,
  string FK refs. Sensitive PII stored Fernet-encrypted in a `BinaryField`
  (see §3 of this doc / `apps/needs/models.py`).
- **State machines:** `STATUS_CHOICES` + `VALID_TRANSITIONS` dict +
  `transition_to()` raising `ValidationError`; terminal states enforced.
- **Audit:** `AuditLog.log(user, action, resource_type, resource_id, details=None,
  request=None)` for every state change AND every disclosure of sensitive data;
  reuse the `audit` app (append-only).
- **Consent:** reuse the `consent` app; cross-person/cross-lake data sharing
  requires an explicit `umi:Consent` first.

### Visual design — warm "parish atmosphere"
- Background `#FDFBF7` with a soft top-centre radial gradient; warm-brown ink `#2C2A29`.
- Accents: deep green `#2B5E2B` (primary), soft gold `#C49A3C` (secondary).
- Serif headings (**Lora → Georgia** fallback; **no external webfont loaded**),
  Open Sans body, generous line-height (1.6).
- 960px max content width; translucent **blurred header** with a hairline border.
- Bulletin-style cards: warm surface, **green (need) / gold (offer)** left border;
  urgency = **muted colour dots with dark-grey text**.
- **Green pill buttons** (primary solid / secondary outline).
- **Calm micro-interactions only:** contact-reveal crossfade (no rotation),
  timeline checkmark fade (no scaling), refresh spinner, toast slide-in/out,
  empty-state SVG (single-stroke church) fade-in. All respect `prefers-reduced-motion`.
- Tailwind compiled to `static/css/output.css`; served via WhiteNoise
  `CompressedManifestStaticFilesStorage` (needs `collectstatic`; `DEBUG` defaults `False`).

### Testing / CI / Deploy
- **73 tests passing**; `ruff check` + `ruff format` clean; `make lint` runs both.
- CI: `.github/workflows/ci.yml` (lint, tests, build); `deploy.yml` (GHCR + SSH).
- Deploy: `Dockerfile` + `docker-compose.yml` (+ `docker/docker-compose.prod.yml`,
  `Caddyfile`, `Caddyfile.prod`, logrotate); scripts: `harden.sh`, `backup.sh`,
  `restore.sh`, `security_check.sh`, `setup_hardening.sh`.

### NOT in this codebase (guard against scope creep)
From an earlier "Parish Aid Board / Lake 1" lineage and **not** part of UMI
Exchange — do not assume or reintroduce: Stripe billing, Twilio SMS, Chart.js
dashboards, PWA manifest/service worker, blog, scheduled email digests (only an
`email_digest` *config key* exists), account-deletion flow.

### Repo state / open items
- All feature work merged into `main`. Stale branches pending deletion (not yet
  cleaned). St. Patrick pilot: env scaffolding exists; implementation playbook
  written (`docs/st-patrick-playbook.md`).

---

## 2. Lakes Complete Operating Manual — Lakes 2–8

> 🛑 **PASTE THE OPERATING MANUAL HERE.** This document does not contain the
> authoritative Lake 2–8 definitions; they were not available when it was
> generated. Replace this entire block with the real manual text so the spec is
> complete. Do **not** rely on the summaries below as authoritative.

**Lakes referenced so far in this project (names/one-liners only — NOT a substitute
for the manual; confirm against the real document):**
- **Lake 1 — Parish Aid Board (UMI Exchange):** the implemented system in Section 1.
- **Lake 2 — Case Notes:** a private, structured way for a care team (e.g. St.
  Vincent de Paul) to track ongoing situations, under the same strict privacy and
  append-only audit rules. *(Most immediate post-pilot need.)*
- **Lake — Skills Directory:** an opt-in, searchable directory of parishioners'
  skills/trades for when a specific kind of help is needed.
- **Other lakes (3–8):** definitions unknown to this document — supply via the
  manual. (Workflows hinted elsewhere include offline visit recording, warm
  handoff, referral consent, attestations, skill-density mapping, and pantry
  tracking — confirm and complete from the manual.)

`<PASTE LAKES 2–8 MANUAL TEXT ABOVE THIS LINE>`

---

## 3. Warm parish design tokens (verified — from `static/css/input.css` + `tailwind.config.js`)

> The frontend design system already exists; do not regenerate CSS/HTML/JS. These
> tokens are provided so backend/data designs reference the correct names.

### Colour (CSS custom properties on `:root`, overridable per community)
| Token | Value | Use |
|---|---|---|
| `--umi-primary` | `#2B5E2B` | deep muted green — primary accent, buttons, need border |
| `--umi-primary-hover` | `#244F24` | button hover |
| `--umi-accent` | `#C49A3C` | soft gold — secondary accent, offer border |
| `--umi-bg` | `#FDFBF7` | warm off-white paper (page background) |
| `--umi-bg-soft` | `#F5F0E8` | soft cream (gradient stop) |
| `--umi-card` | `#FAF7F1` | light warm grey card surface |
| `--umi-border` | `#E6DED5` | subtle warm hairline border |
| `--umi-text` | `#2C2A29` | warm dark-brown ink |
| `--umi-text-soft` | `#6B6358` | muted warm grey (secondary text) |
| `--umi-need-accent` | `#2B5E2B` | needs → green left border |
| `--umi-offer-accent` | `#C49A3C` | offers → gold left border |

Tailwind palette (`tailwind.config.js`): `parish.{bg, soft, card, border, ink,
green, greendark, gold}` plus `umi-primary`/`umi-accent` mapped to the CSS vars.

### Typography
- **Headings:** serif stack `Lora → Georgia → Cambria → Times New Roman → serif`,
  `font-weight: 500`, `letter-spacing: -0.01em`. **No external webfont is loaded**
  (Georgia is the practical default).
- **Body:** `Open Sans → system-ui → -apple-system → … → sans-serif`,
  `line-height: 1.6`.
- Buttons/labels: body family, medium weight.

### Spacing & layout
- **Content width:** `max-width: 960px` (Tailwind `max-w-parish`), centered,
  `px-4 sm:px-6` (edge-to-edge on the smallest screens).
- **Cards:** padding `p-6`; **gap between cards `gap-6`**; `rounded-xl`; 1px
  `--umi-border`; soft shadow only on hover + a gentle `scale(1.01)`.
- **Header:** sticky, translucent (`rgba(253,251,247,0.8)`), `backdrop-blur`,
  hairline bottom border.
- **Background:** `radial-gradient(120% 60% at 50% -10%, #fff 0%, --umi-bg 55%,
  --umi-bg-soft 100%)`, fixed.

### Breakpoints (Tailwind defaults)
`sm` 640px · `md` 768px · `lg` 1024px. Mobile-first; buttons go full-width on the
narrowest screens where used as primary actions.

### Animation guidelines (calm only)
- **Fades only**, ~200ms ease. **No** rotation, scaling, bounce, or pulsing.
- Sanctioned interactions: contact-reveal **crossfade**; timeline checkmark
  **fade-in**; refresh **spinner** (while HTMX request in flight); **toast**
  slide-in (300ms) / slide-out (200ms); empty-state SVG **fade-in**.
- **Every** animation must be disabled under `@media (prefers-reduced-motion: reduce)`
  (global override in `base.html` + per-rule guards).
- New lakes add **no** new animations beyond this vocabulary.

---

## 4. Existing app structure (verified — `apps/`)

New lakes are normally **new Django apps in this same project**, reusing
`accounts`, `communities`, `consent`, `audit`, and `notifications`.

| App | Responsibility |
|---|---|
| `accounts` | Custom `User` (email/phone); registration, login (rate-limited), profile/settings, password-reset flow, optional 2FA hooks. |
| `audit` | Append-only `AuditLog` (SHA-256-hashed IPs); model-level save/delete blocks + Postgres `REVOKE` migration. The shared audit trail for the whole project. |
| `communities` | `Community`, `Member` (role: member/coordinator/admin), `Category`; community create/feed/settings, CSPRNG join code + QR, context processor. The multi-tenant backbone. |
| `consent` | `umi:Consent` entity; member views/revokes their consents. Reuse for any cross-person data sharing. |
| `dashboard` | Coordinator/admin-only: metrics, **stale needs**, category breakdown, **CSV export** (needs/matches). No models. |
| `health` | `/health/` endpoint (DB + cache checks); optional constant-time `HEALTH_CHECK_TOKEN`. |
| `households` | `Household` (CSPRNG join code); create/join; billing-by-household concept. |
| `matches` | `umi:Match`; state machine (`transition_to`), propose/accept/fulfill/cancel, contact revelation (§8.2) with disclosure auditing, optional sanitized notes, `SELECT FOR UPDATE` race handling. The reference implementation for new lakes' workflows. |
| `needs` | `umi:Need`; **Fernet-encrypted `on_behalf_of`** field; create/detail/delete with ownership + membership checks. |
| `notifications` | `Notification` model; list / mark-all-read / unread-count; `NotificationAdapter` (in-app + email, failures swallowed). Reuse to notify users. |
| `offers` | `umi:Offer`; create/detail/delete with ownership + membership checks. |

### Reference files worth reading before designing a lake
- `apps/matches/models.py` — state machine + contact-revelation pattern.
- `apps/matches/views.py` — auth (`_reject`/403), `select_for_update`→409, audit, notifications.
- `apps/needs/models.py` — Fernet encrypt/decrypt pattern for sensitive fields.
- `apps/audit/models.py` + `apps/audit/migrations/0002_append_only.py` — append-only enforcement.
- `apps/dashboard/views.py` — coordinator-only `dispatch` gate + CSV export.
- `config/settings/` — per-env settings; production secret fail-fast guards.

---

*End of consolidated spec. Replace Section 2 with the real Lakes manual before
treating this as complete.*
