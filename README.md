# UMI Exchange

**Reference implementation of the [UMI Protocol v0.1](docs/protocol/spec.md) at Core + Casework + Federation v1 conformance.**

An open-source tool for coordinating reciprocal exchange in communities. A Catholic parish, a secular mutual aid group, a disaster relief network, or a Buddhist timebank can each adopt this as their starting point.

## Quick Start (Local Development)

```bash
# Clone and enter the project
git clone https://github.com/your-org/umi-exchange.git
cd umi-exchange

# Run the interactive setup
bash scripts/setup.sh

# Or manually:
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Edit with your DB and Redis URLs
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Visit http://localhost:8000

## Docker Deployment

```bash
cd docker
docker compose up -d

# Run migrations inside the container
docker compose exec app python manage.py migrate
docker compose exec app python manage.py createsuperuser
```

Visit http://localhost (Caddy reverse proxy)

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SECRET_KEY` | Yes | — | Django secret key (50+ random chars) |
| `DATABASE_URL` | Yes | sqlite:///db.sqlite3 | PostgreSQL connection URL |
| `REDIS_URL` | No | — | Redis URL for cache/sessions/queue |
| `SITE_URL` | No | http://localhost:8000 | Public URL (used for QR code generation) |
| `ENCRYPTION_KEY` | Prod: Yes | — | Fernet key for encrypting sensitive fields; production refuses to boot without it (`ENCRYPTION_KEYS` list supported for rotation) |
| `BLIND_INDEX_KEY` | Prod: Yes | — | Dedicated secret for the Person name blind index — must differ from every encryption key; production refuses to boot without it |
| `ALLOWED_HOSTS` | No | localhost,127.0.0.1 | Comma-separated allowed hosts |
| `DEBUG` | No | True | Set False in production |
| `EMAIL_BACKEND` | No | console | Django email backend |
| `UMI_CONFORMANCE_LEVEL` | No | core | Protocol conformance level |

## Technology Stack

Every technology has 10+ years of production use:

- **Python 3.12** + **Django 5.x** — web framework
- **PostgreSQL 16** — database
- **Redis 7** — cache, sessions, task queue
- **HTMX** — dynamic interactions without heavy JS
- **Alpine.js** — minimal client-side state
- **Tailwind CSS** — utility-first styling
- **Docker** + **Caddy** — deployment

## Optional Refinements

### QR Code Join Flow
Enabled by default. Admin generates QR code from community settings page. Requires `qrcode[pil]` in requirements.

### Household Model
Enabled by default. Members can create/join households. Billing counts by households, not individual members.

### 2FA for Coordinators
Built in and active: once a user enrolls an authenticator app (TOTP), login requires the code — with printed static recovery codes as backup and per-device throttling. No settings changes needed; just enroll the coordinator accounts.

### VPS Hardening
```bash
sudo bash scripts/harden.sh
```
Configures UFW, fail2ban, unattended-upgrades, SSH hardening, and logwatch.

## Customisation

Override the visual theme via CSS custom properties in your instance's stylesheet:

```css
:root {
  --umi-primary: #1A3E5C;     /* Deep blue for a Catholic parish */
  --umi-accent: #D4A745;       /* Gold accent */
}
```

## Protocol Conformance

This implementation conforms to **UMI Protocol v0.1 at Core + Casework + Federation v1**:
- umi:Need, umi:Offer, umi:Match, umi:Consent entities
- State machines enforced in Python (Match.transition_to)
- Contact revelation only after match acceptance (Section 8.2)
- Self-matching prevention (Section 8.6)
- Race condition handling via SELECT FOR UPDATE (Section 8.7)
- Append-only audit log with hashed IPs (Section 8.3)
- Casework (Lake 2): case files and notes under envelope encryption with crypto-shred, a single access matrix, and 4-hour re-auth on sensitive views
- Federation v1: cross-instance listing exchange, default-OFF per community

## License

- **Code**: AGPL-3.0
- **Protocol Specification**: CC-BY-4.0

Built on UMI Protocol v0.1 — [build your own](docs/protocol/spec.md). Every running instance
also serves the protocol at `/protocol/` and the raw spec at `/protocol/spec.md`.

## Production Deployment

### Quick Production Setup

```bash
# On your server:
git clone https://github.com/your-org/umi-exchange.git /opt/umi-exchange
cd /opt/umi-exchange

# Harden the server first
sudo bash scripts/harden.sh

# Configure environment
cp .env.example .env
# Edit .env: set SECRET_KEY, ENCRYPTION_KEY, BLIND_INDEX_KEY (a dedicated secret,
# never the same value as an encryption key), DB_PASSWORD, ALLOWED_HOSTS, SITE_URL,
# DJANGO_SETTINGS_MODULE=config.settings.production, SENTRY_DSN.
# Production refuses to boot if any of the three keys is missing or the
# blind-index key collides with an encryption key.

# Update Caddyfile with your domain
export DOMAIN=yourdomain.org

# Launch
docker compose -f docker/docker-compose.prod.yml up -d
docker compose -f docker/docker-compose.prod.yml exec app python manage.py migrate
docker compose -f docker/docker-compose.prod.yml exec app python manage.py createsuperuser

# Verify
curl https://yourdomain.org/health/
```

See `docs/deployment-checklist.md` for the full checklist.

### Monitoring

- **Health check**: `GET /health/` returns `{"status": "ok", "db": "ok", "cache": "ok"}`
- **Sentry**: Set `SENTRY_DSN` in `.env` for error tracking (no PII sent)
- **Uptime Kuma**: `docker compose --profile monitoring up -d` starts a local uptime monitor on port 3001

### Backups

```bash
# Manual backup
bash scripts/backup.sh

# Schedule daily (cron)
( crontab -l 2>/dev/null; echo "0 3 * * * /opt/umi-exchange/scripts/backup.sh >> /var/log/umi-backup.log 2>&1" ) | crontab -

# Restore
bash scripts/restore.sh /var/backups/umi/umi-20260325-030000.sql.gz
```

### CI/CD

GitHub Actions workflows are provided:
- `.github/workflows/ci.yml`: Lint, security scan, tests, Docker build on every push
- `.github/workflows/deploy.yml`: Build, push to GHCR, deploy via SSH on merge to `main`

### Scaling

See `docs/scaling.md` for connection pooling, caching, horizontal scaling, and read replicas. For most communities (<5,000 members), a single $5–10/month VPS is sufficient.
