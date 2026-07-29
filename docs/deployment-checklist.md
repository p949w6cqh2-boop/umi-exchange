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
  - [ ] `APP_DB_USER` / `APP_DB_PASSWORD`: the runtime role (`umi_app`) — created in the
        "Database roles" step below; keeps the append-only audit REVOKE binding
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

# ── Database roles (threat-model must-fix #1 — BEFORE migrating) ──────────
# The append-only audit log is enforced by REVOKE, and a REVOKE only binds a
# role that does NOT own the table: owners can re-grant themselves, and
# superusers ignore ACLs entirely. So `umi` (the compose POSTGRES_USER) stays
# the OWNER and runs migrations, while the app connects as `umi_app`, a plain
# non-owner role.
docker compose -f docker/docker-compose.prod.yml exec db psql -U umi -d umi_exchange -c "
  CREATE ROLE umi_app LOGIN PASSWORD '<strong password>' NOSUPERUSER NOCREATEDB NOCREATEROLE;
  GRANT USAGE ON SCHEMA public TO umi_app;
  GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO umi_app;
  GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO umi_app;
  ALTER DEFAULT PRIVILEGES FOR ROLE umi IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO umi_app;
  ALTER DEFAULT PRIVILEGES FOR ROLE umi IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO umi_app;"
# Then add to .env:  APP_DB_USER=umi_app  APP_DB_PASSWORD=<that password>
# and recreate the app service so DATABASE_URL / AUDIT_DB_APP_ROLE pick them up:
docker compose -f docker/docker-compose.prod.yml up -d app

# Run migrations — AS THE OWNER (umi), with AUDIT_DB_APP_ROLE pointing at the
# runtime role so audit migration 0002's REVOKE lands on umi_app:
docker compose -f docker/docker-compose.prod.yml exec \
  -e DATABASE_URL=postgres://umi:${DB_PASSWORD}@db:5432/umi_exchange \
  -e AUDIT_DB_APP_ROLE=umi_app \
  app python manage.py migrate

# Create superuser
docker compose -f docker/docker-compose.prod.yml exec app python manage.py createsuperuser

# Collect static files
docker compose -f docker/docker-compose.prod.yml exec app python manage.py collectstatic --noinput

# Restrict audit log permissions (idempotent re-assert — same owner-connection
# env override as the migrate step, targeting the runtime role)
docker compose -f docker/docker-compose.prod.yml exec \
  -e DATABASE_URL=postgres://umi:${DB_PASSWORD}@db:5432/umi_exchange \
  -e AUDIT_DB_APP_ROLE=umi_app \
  app python manage.py restrict_audit_permissions

# VERIFY the gate (both must hold, on every production instance):
docker compose -f docker/docker-compose.prod.yml exec db psql -U umi -d umi_exchange -c \
  "SELECT tableowner FROM pg_tables WHERE tablename='audit_auditlog';"      # must NOT be umi_app
docker compose -f docker/docker-compose.prod.yml exec db psql -U umi_app -d umi_exchange -c \
  "SELECT current_user, rolsuper FROM pg_roles WHERE rolname=current_user;" # rolsuper must be f

# Register background-job schedules (django-q2). Without this the recurring
# sweeps never run: need expiry (§4.1), match-proposal expiry (§10.6), the
# follow-up digest + stale-draft cleanup (§3.11). Idempotent (update_or_create).
docker compose -f docker/docker-compose.prod.yml exec app python manage.py shell -c "\
from apps.needs.tasks import register_schedule as _n; _n(); \
from apps.matches.tasks import register_schedule as _m; _m(); \
from apps.casework.tasks import register_schedule as _c; _c()"
# Federation's sweep is registered separately, only when FEDERATION_ENABLED=1
# (apps.federation.tasks.register_schedule) — see the federation runbook.
```

## Post-Deployment

- [ ] **Health check**: `curl https://yourdomain.org/health/` returns `{"status": "ok"}`
- [ ] **Email delivery (SMTP)**: set `EMAIL_HOST` / `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD`
      (parish/diocese mail server or a transactional provider) and `DEFAULT_FROM_EMAIL`. Production
      auto-switches to the SMTP backend once `EMAIL_HOST_USER` is set (no `EMAIL_BACKEND` needed).
      Confirm: `manage.py shell -c "from django.core.mail import send_mail; send_mail('UMI test','it works','$DEFAULT_FROM_EMAIL',['you@yourdomain.org'])"`
      lands in a real inbox (check SPF/DKIM so it isn't spam-filed). Notification email is consented
      per user — a member can opt out under Account settings, and the adapter honours it.
- [ ] **Sentry**: Trigger a test error — verify it appears in Sentry dashboard
- [ ] **SSL**: Verify with `curl -vI https://yourdomain.org` — look for `HTTP/2 200`
- [ ] **Security headers**: Test at https://observatory.mozilla.org
- [ ] **Create test community**: Register, create community, post need, propose match, accept, verify contact revelation
- [ ] **Backup test**: Run `bash scripts/backup.sh`, then rehearse the restore into a scratch database with `bash scripts/dr_sim.sh` (see vps-runbook §9.1 — it refuses to touch prod, asserts the restore is not empty, and checks a known record). `scripts/restore.sh` is the *production* restore, not the rehearsal.
- [ ] **Retention check**: Confirm nothing in `/var/backups/umi/` is older than `RETENTION_DAYS`, **and** that the B2 bucket lifecycle rule exists — `backup.sh` never deletes remote copies (vps-runbook §9.2)
- [ ] **Backup cron installed**: `( crontab -l 2>/dev/null; echo "0 3 * * * /opt/umi-exchange/scripts/backup.sh >> /var/log/umi-backup.log 2>&1" ) | crontab -` — then confirm `crontab -l` shows the line (the append form matters: a bare `echo … | crontab -` replaces the whole crontab)
- [ ] **B2 upload verified**: at least one run has printed `Remote upload verified` (in `/var/log/umi-backup.log` or a manual `bash scripts/backup.sh`); once B2 is provisioned, set `BACKUP_REQUIRE_REMOTE=1` in `.env` so a night without an off-site copy exits nonzero instead of passing silently (vps-runbook §9)
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
