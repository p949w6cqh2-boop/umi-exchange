# UMI Exchange — Completion Tasks

## 1. Missing Template Components
- [ ] `_category_grid.html`
- [ ] `_urgency_selector.html`
- [ ] `_metric_card.html`
- [ ] `_filter_bar.html`
- [ ] `_primary_button.html`
- [ ] `_protocol_badge.html`
- [ ] `_trust_badge.html`

## 2. SVG Placeholder Images
- [ ] `hands.svg`, `ripple.svg`, `house.svg`, `bridge.svg`
- [ ] `lock.svg`, `seedling.svg`, `network.svg`, `gear.svg`

## 3. Docker Fixes
- [ ] Root `Dockerfile` — multi-stage build
- [ ] Root `docker-compose.yml` — fix env vars, ports, Caddyfile path

## 4. 2FA Integration (opt-in, toggle in settings)
- [ ] Uncomment 2FA in `requirements.txt`
- [ ] Conditional 2FA in `base.py` (apps, middleware, env flag for coordinator requirement)
- [ ] 2FA setup URL in `urls_settings.py`
- [ ] 2FA toggle in `settings.html`

## 5. Dashboard CSV Export
- [ ] `DashboardCSVExportView` in `apps/dashboard/views.py`
- [ ] CSV export URL in `apps/communities/urls.py`

## 6. Audit Middleware
- [ ] `apps/audit/middleware.py`
- [ ] Add to MIDDLEWARE in `base.py`

## 7. Missing Init
- [ ] `apps/__init__.py`
