# Deploy Runbook — reciprocalaid.network

How to push a merged `main` to production. Companion to `DEPLOY.md` (first-time
server setup); this is the **recurring deploy** you run after every merge you want live.

## Why deploy is manual

`.github/workflows/deploy.yml` runs on every push to `main`, but its **deploy job is
gated**: `if: vars.DEPLOY_ENABLED == 'true'` (default unset ⇒ **skipped**). This is a
deliberate 2026-07-16 ruling — a permanently-red deploy check on every push trains us to
ignore red, and red must mean *stop*. So a merge only:

- builds the app image and pushes it to GHCR (**Build & Push Image**, always runs), and
- **skips** the SSH-to-droplet step.

Nothing reaches production until a human runs the steps below. (The droplet also runs a
**locally built** `umi-exchange:local`, not the GHCR image — so `scripts/deploy.sh`'s
`docker compose pull app` is not the path this droplet uses. Build locally, as below.)

## Prerequisites

- SSH access to the droplet as `root@143.244.167.7` (prompt reads `root@UMI-droplet` —
  confirm it before pasting; your laptop is a different host).
- The change is merged to `main` and CI is green.

## The steps

```bash
# 1. Connect and enter the repo
ssh root@143.244.167.7
cd /opt/umi-exchange

# 2. Pull the merged code (fast-forwards cleanly since the PR #89 reconcile)
git pull --ff-only origin main

# 3. Back up the DB FIRST — this is your rollback point
bash scripts/backup.sh          # -> /var/backups/umi/umi-<timestamp>.sql.gz

# 4. Rebuild the image. REQUIRED for any template/code change:
#    the app code is baked in via COPY (no source bind-mount, only a logs volume),
#    so pull + restart alone serves the OLD page. Unchanged layers stay cached, so
#    a no-op rebuild is fast.
#    Always pass -f docker/Dockerfile: that is the file CI's Docker Build Test and
#    the GHCR push build, so this is the image CI has actually proved. The root
#    Dockerfile is a convenience alias kept identical to it — a bare `docker build .`
#    is fine, but name the canonical one here so the two can never quietly diverge.
docker build -t umi-exchange:local -f docker/Dockerfile .

# 5. Recreate the app container. ALWAYS pass --env-file .env — without it, compose
#    interpolates a blank DB password from docker/ and the app breaks.
docker compose --env-file .env -f docker/docker-compose.prod.yml up -d app

# 6. Migrate + collect static (both no-ops when nothing changed; safe to always run)
docker compose --env-file .env -f docker/docker-compose.prod.yml exec -T app \
  python manage.py migrate --noinput
docker compose --env-file .env -f docker/docker-compose.prod.yml exec -T app \
  python manage.py collectstatic --noinput

# 7. Verify
docker compose --env-file .env -f docker/docker-compose.prod.yml ps app   # want "healthy"
curl -sf https://reciprocalaid.network/about/ | grep -o "<a string you changed>"
```

## Rollback

If a deploy goes bad, restore the dump from step 3 and rebuild the previous commit:

```bash
gunzip -c /var/backups/umi/umi-<timestamp>.sql.gz | \
  docker compose --env-file .env -f docker/docker-compose.prod.yml exec -T db \
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"
git checkout <previous-sha> && docker build -t umi-exchange:local -f docker/Dockerfile . && \
  docker compose --env-file .env -f docker/docker-compose.prod.yml up -d app
```

## Turning on real auto-deploy (later)

Set the repo variable `DEPLOY_ENABLED=true`. From then on, **every** push to `main`
deploys itself via the workflow's SSH job (host/user/key live in repo secrets
`DEPLOY_HOST` / `DEPLOY_USER` / `DEPLOY_SSH_KEY`). This is a standing change — leave it
off while you still want a hand on the wheel per deploy.
