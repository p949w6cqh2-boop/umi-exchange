# UMI Exchange — Deployment Checklist

## Pre-Deployment

- [ ] **Server provisioned**: Ubuntu 22.04+ with 2+ CPU, 4+ GB RAM
- [ ] **Domain configured**: DNS A record pointing to server IP
- [ ] **SSH key**: Public key installed on server; password auth will be disabled
- [ ] **Run hardening**: `sudo bash scripts/harden.sh`
- [ ] **Environment file**: Copy `.env.example` to `.env` and set all values:
  - [ ] `SECRET_KEY`: Generate with `python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`
  - [ ] `ENCRYPTION_KEY`: Generate with `python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
  - [ ] `DATABASE_URL`: PostgreSQL connection string
  - [ ] `DB_PASSWORD`: Strong password (not `umi`)
  - [ ] `ALLOWED_HOSTS`: Your domain
  - [ ] `SITE_URL`: `https://yourdomain.org`
  - [ ] `SENTRY_DSN`: From sentry.io project settings (optional)
  - [ ] `DJANGO_SETTINGS_MODULE`: `config.settings.production`
  - [ ] `DEBUG`: `False`
- [ ] **SSL**: Caddy handles TLS automatically via Let's Encrypt
- [ ] **Caddyfile**: Update `DOMAIN` in `docker/Caddyfile.prod`

## Deployment

```bash
# Clone repository
git clone https://github.com/your-org/umi-exchange.git /opt/umi-exchange
cd /opt/umi-exchange

# Set environment
cp .env.example .env
# Edit .env with production values

# Start services
docker compose -f docker/docker-compose.prod.yml up -d

# Run migrations
docker compose -f docker/docker-compose.prod.yml exec app python manage.py migrate

# Create superuser
docker compose -f docker/docker-compose.prod.yml exec app python manage.py createsuperuser

# Collect static files
docker compose -f docker/docker-compose.prod.yml exec app python manage.py collectstatic --noinput

# Restrict audit log permissions
docker compose -f docker/docker-compose.prod.yml exec app python manage.py restrict_audit_permissions
```

## Post-Deployment

- [ ] **Health check**: `curl https://yourdomain.org/health/` returns `{"status": "ok"}`
- [ ] **Sentry**: Trigger a test error — verify it appears in Sentry dashboard
- [ ] **SSL**: Verify with `curl -vI https://yourdomain.org` — look for `HTTP/2 200`
- [ ] **Security headers**: Test at https://observatory.mozilla.org
- [ ] **Create test community**: Register, create community, post need, propose match, accept, verify contact revelation
- [ ] **Backup test**: Run `bash scripts/backup.sh`, then `bash scripts/restore.sh <file>` on a test database
- [ ] **Cron**: Schedule backups: `echo "0 3 * * * /opt/umi-exchange/scripts/backup.sh >> /var/log/umi-backup.log 2>&1" | crontab -`
- [ ] **Monitoring**: Set up Uptime Kuma or similar to ping `/health/` every 60 seconds

## Rollback Procedure

1. Stop the app: `docker compose -f docker/docker-compose.prod.yml stop app`
2. Pull the previous image: `docker compose -f docker/docker-compose.prod.yml pull app` (pin to previous tag)
3. Start: `docker compose -f docker/docker-compose.prod.yml up -d app`
4. If database migration was destructive: restore from backup with `scripts/restore.sh`
5. Verify: `curl https://yourdomain.org/health/`

## Ongoing Maintenance

| Task | Frequency | Command |
|------|-----------|---------|
| Apply security patches | Automatic (unattended-upgrades) | — |
| Database backup | Daily (cron) | `scripts/backup.sh` |
| Review logs | Weekly | `cat /var/log/logwatch-daily.txt` |
| Update Docker images | Monthly | `docker compose pull && docker compose up -d` |
| Test backup restore | Quarterly | `scripts/restore.sh` on test DB |
| Rotate secrets | Annually | Regenerate `SECRET_KEY`, `ENCRYPTION_KEY`; restart |
| SSL certificate | Automatic (Caddy + Let's Encrypt) | — |
