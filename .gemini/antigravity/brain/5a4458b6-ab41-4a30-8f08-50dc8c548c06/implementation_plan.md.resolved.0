# UMI Exchange — Complete to Production-Ready

## Background

The existing project at `/home/umi/umi-exchange` already has a substantial foundation with ~80% of the required files. After a thorough audit of every file, I've identified specific gaps that need to be filled to reach the production-ready state described in the requirements.

## What Already Exists (✅ Complete)

| Component | Status |
|-----------|--------|
| `manage.py`, `.env.example`, `requirements.txt` | ✅ Solid |
| `pyproject.toml`, `tailwind.config.js` | ✅ Solid |
| `config/settings/base.py`, `development.py`, `production.py`, `staging.py` | ✅ Complete |
| `config/urls.py`, `wsgi.py`, `asgi.py` | ✅ Complete |
| **accounts** app (User model, registration, login, settings, forms) | ✅ Complete |
| **communities** app (Community, Member, Category, views, QR code, feed) | ✅ Complete |
| **needs** app (Need model with encryption, forms, views, tasks) | ✅ Complete |
| **offers** app (Offer model, forms, views) | ✅ Complete |
| **matches** app (Match model with state machine, views, race condition handling) | ✅ Complete |
| **notifications** app (Notification model, adapter, views, template tags) | ✅ Complete |
| **dashboard** app (Coordinator dashboard with metrics) | ✅ Complete |
| **audit** app (AuditLog model, management command) | ✅ Complete |
| **health** app (Health check endpoint) | ✅ Complete |
| **consent** app (Consent model stub) | ✅ Complete |
| **households** app (Household model, forms, views, URLs) | ✅ Complete |
| Docker files (`docker/Dockerfile`, `docker/docker-compose.prod.yml`, `docker/Caddyfile.prod`) | ✅ Complete |
| Scripts (`harden.sh`, `backup.sh`, `restore.sh`, `deploy.sh`) | ✅ Complete |
| CI/CD (`.github/workflows/ci.yml`, `deploy.yml`) | ✅ Complete |
| Docs (`deployment-checklist.md`, `scaling.md`) | ✅ Complete |
| Tests (`conftest.py`, `test_matches.py`) | ✅ Complete |
| Templates (base, landing, feed, login, register, settings, needs, offers, matches, dashboard, households, notifications, components) | ✅ Most exist |

## Gaps to Fill

### 1. Missing Template Components (Spec'd but not present)
- `templates/components/_category_grid.html` — Category selection grid for need/offer creation
- `templates/components/_urgency_selector.html` — Visual urgency picker
- `templates/components/_metric_card.html` — Reusable metric card for dashboard
- `templates/components/_filter_bar.html` — Reusable filter bar component
- `templates/components/_primary_button.html` — Consistent button component
- `templates/components/_protocol_badge.html` — UMI Protocol conformance badge
- `templates/components/_trust_badge.html` — Trust/verification indicator

### 2. Missing SVG Placeholder Images
- `static/img/hands.svg` — Community/helping hands
- `static/img/ripple.svg` — Impact ripple effect
- `static/img/house.svg` — Household icon
- `static/img/bridge.svg` — Connection/bridging
- `static/img/lock.svg` — Privacy/security
- `static/img/seedling.svg` — Growth/new beginning
- `static/img/network.svg` — Network/interconnection
- `static/img/gear.svg` — Settings/configuration

### 3. Root `Dockerfile` is minimal
The root `Dockerfile` (15 lines) is a simple single-stage build. The multi-stage one is in `docker/Dockerfile`. The root one needs upgrading to match the spec (or we defer to `docker/Dockerfile`).

### 4. Root `docker-compose.yml` has some issues
- References `${POSTGRES_DB}`, `${POSTGRES_USER}`, `${POSTGRES_PASSWORD}` but `.env.example` has `DATABASE_URL` format instead
- Missing port mapping for the app (for local dev without Caddy)
- The Caddyfile reference points to `./Caddyfile` (root) but the dev Caddyfile is at `docker/Caddyfile`

### 5. 2FA Integration (Optional but requested)
Requirements specify 2FA should be un-commented/enabled. Currently it's commented out in `requirements.txt` and not wired in settings or views. Need to:
- Uncomment 2FA in requirements
- Add conditional 2FA settings in base.py
- Add 2FA setup view in accounts app

### 6. Dashboard CSV Export
The dashboard spec mentions "export CSV" but no export view exists.

### 7. Needs app missing URLs file
The needs app has views but no `urls.py` — URLs are defined in `communities/urls.py`. This is intentional (needs are scoped under `/c/<slug>/needs/`), but there's no `apps/needs/urls.py` file.

### 8. Missing `apps/__init__.py`
No `apps/__init__.py` file (may or may not be needed depending on how Django resolves the apps).

### 9. Audit Middleware
The spec mentions "audit middleware" but no middleware file exists in the audit app.

## Proposed Changes

### Component 1: Missing Template Components

#### [NEW] [_category_grid.html](file:///home/umi/umi-exchange/templates/components/_category_grid.html)
Grid of emoji-labelled category buttons for need/offer creation forms. Uses HTMX to set hidden category field.

#### [NEW] [_urgency_selector.html](file:///home/umi/umi-exchange/templates/components/_urgency_selector.html)
Visual urgency picker with color-coded buttons and accessibility labels.

#### [NEW] [_metric_card.html](file:///home/umi/umi-exchange/templates/components/_metric_card.html)
Reusable dashboard metric card with label, value, and optional trend indicator.

#### [NEW] [_filter_bar.html](file:///home/umi/umi-exchange/templates/components/_filter_bar.html)
Extractable filter bar used in feed and dashboard.

#### [NEW] [_primary_button.html](file:///home/umi/umi-exchange/templates/components/_primary_button.html)
Consistent primary action button with href, label, and optional icon.

#### [NEW] [_protocol_badge.html](file:///home/umi/umi-exchange/templates/components/_protocol_badge.html)
UMI Protocol conformance badge shown in footer.

#### [NEW] [_trust_badge.html](file:///home/umi/umi-exchange/templates/components/_trust_badge.html)
Trust/verification indicator for coordinators and verified members.

---

### Component 2: SVG Placeholder Images

#### [NEW] Eight SVG files in `static/img/`
Simple, clean SVG illustrations: `hands.svg`, `ripple.svg`, `house.svg`, `bridge.svg`, `lock.svg`, `seedling.svg`, `network.svg`, `gear.svg`.

---

### Component 3: Root Docker Files Fix

#### [MODIFY] [Dockerfile](file:///home/umi/umi-exchange/Dockerfile)
Replace minimal single-stage Dockerfile with proper multi-stage build matching `docker/Dockerfile` patterns.

#### [MODIFY] [docker-compose.yml](file:///home/umi/umi-exchange/docker-compose.yml)
Fix env var references, add port mapping for local dev, fix Caddyfile path.

---

### Component 4: 2FA Integration

#### [MODIFY] [requirements.txt](file:///home/umi/umi-exchange/requirements.txt)
Uncomment django-otp and django-two-factor-auth.

#### [MODIFY] [base.py](file:///home/umi/umi-exchange/config/settings/base.py)
Add conditional 2FA app/middleware integration.

#### [MODIFY] [urls_settings.py](file:///home/umi/umi-exchange/apps/accounts/urls_settings.py)
Add 2FA setup URL.

#### [MODIFY] [settings.html](file:///home/umi/umi-exchange/templates/accounts/settings.html)
Add 2FA toggle section.

---

### Component 5: Dashboard CSV Export

#### [MODIFY] [views.py](file:///home/umi/umi-exchange/apps/dashboard/views.py)
Add `DashboardCSVExportView` for coordinator data export.

#### [MODIFY] [urls.py](file:///home/umi/umi-exchange/apps/communities/urls.py)
Add CSV export URL.

---

### Component 6: Audit Middleware

#### [NEW] [middleware.py](file:///home/umi/umi-exchange/apps/audit/middleware.py)
Request logging middleware for state-changing operations.

#### [MODIFY] [base.py](file:///home/umi/umi-exchange/config/settings/base.py)
Add audit middleware to MIDDLEWARE list.

---

### Component 7: Missing Init File

#### [NEW] [__init__.py](file:///home/umi/umi-exchange/apps/__init__.py)
Empty init file for the apps package.

## Verification Plan

### Automated Tests
```bash
# Verify Django can start and check for deployment readiness
python manage.py check --deploy
python manage.py makemigrations --check --dry-run
pytest tests/ -v
```

### Manual Verification
1. Run `docker compose -f docker-compose.yml up -d db redis` to start services
2. Run `python manage.py migrate && python manage.py runserver`
3. Visit http://localhost:8000 — landing page renders
4. Register a user, create a community, post a need, post an offer, propose a match

## Open Questions

> [!IMPORTANT]
> **Scope confirmation**: The existing project is ~80% complete. The gaps are primarily missing template components, SVG assets, Docker config fixes, 2FA wiring, CSV export, and audit middleware. Should I proceed with filling all these gaps, or would you prefer to focus on a specific subset?

> [!NOTE]
> **2FA approach**: The `django-two-factor-auth` package adds TOTP-based 2FA. It's currently commented out. I'll wire it conditionally so it's opt-in per the spec. Should I make it active by default or keep it opt-in?
