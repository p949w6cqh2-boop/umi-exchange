# Deploy Runbook — reciprocalaid.network

How to push a merged `main` to production. Companion to `DEPLOY.md` (first-time
server setup); this is the **recurring deploy** you run after every merge you want live.

> **Updated 2026-10-08 for key custody** (`docs/key-custody-design.md`), the same change #216
> made to the reseed runbook. The droplet is now `root@157.230.185.124` (the `143.244.167.7`
> host was destroyed 2026-09-05; never ssh to it). Its `.env` holds **no keys**: they live only in
> the running app container's stored config. So step 5 brings the app up **from the laptop with
> the custody rig**, which also runs `migrate`, and any management command runs **inside the
> running container** with `docker exec`. A plain `docker compose up -d app` on the droplet starts
> a container from `.env` alone, with no keys, and production refuses to boot.
> Until this update the steps below did exactly that, and the prerequisites asked for the keys to
> be in `.env`, which the rig's `check` now proves they are not.

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

- SSH access to the droplet as `root@157.230.185.124` — confirm the prompt is the droplet's
  before pasting (on the destroyed host it read `root@UMI-droplet`); your laptop is a different
  host, and steps 5 and 7's rig lines run on the laptop.
- The change is merged to `main` and CI is green.
- On the **laptop**: the age identity and `keys.env.age` under `~/.config/umi/` (the rig refuses
  without them), and the `umi-exchange` checkout with `scripts/deploy-with-keys.sh`.
  `SECRET_KEY`, `ENCRYPTION_KEYS` and `BLIND_INDEX_KEY` (distinct from the encryption keys) travel
  from there; production refuses to boot without all three.
- ~~`/opt/umi-exchange/.env` still carries `SECRET_KEY`, `ENCRYPTION_KEY` (or
  `ENCRYPTION_KEYS`), and `BLIND_INDEX_KEY`~~ *(pre-custody; the droplet `.env` must now hold none
  of them, and the rig refuses to deploy while it does).*

## The steps

```bash
# 1. Connect and enter the repo
ssh root@157.230.185.124
cd /opt/umi-exchange

# 2. Pull the merged code (fast-forwards cleanly since the PR #89 reconcile)
git pull --ff-only origin main
git rev-parse --short HEAD   # CHECK IT. Must equal the sha you are deploying.
#   Skipping or silently failing this step is the failure mode that hides best:
#   everything downstream then rebuilds and reports healthy from the OLD tree.

# 3. Back up the DB FIRST — this is your rollback point
bash scripts/backup.sh          # -> /var/backups/umi/umi-<timestamp>.sql.gz
#    expect "Remote upload verified" and the key ciphertext beside the dump

# 4. Rebuild the image. REQUIRED for any template/code change:
#    the app code is baked in via COPY (no source bind-mount, only a logs volume),
#    so pull + restart alone serves the OLD page. Unchanged layers stay cached, so
#    a no-op rebuild is fast.
#    Always pass -f docker/Dockerfile: that is the file CI's Docker Build Test and
#    the GHCR push build, so this is the image CI has actually proved. The root
#    Dockerfile is a convenience alias kept identical to it — a bare `docker build .`
#    is fine, but name the canonical one here so the two can never quietly diverge.
docker build -t umi-exchange:local -f docker/Dockerfile .

# 5. Recreate the app container FROM THE LAPTOP, with the custody rig. It decrypts the
#    keys there, pipes them to droplet tmpfs, merges them with the key-free .env, runs
#    `compose up -d app`, shreds tmpfs on every exit path, then runs migrate inside the
#    new container. Never `docker compose ... up -d app` on the droplet itself: that
#    container reads .env alone, has no keys, and production refuses to boot.
#    (Pre-custody this step was: docker compose --env-file .env -f docker/docker-compose.prod.yml up -d app)
#        # on the laptop, in the umi-exchange checkout
#        UMI_DROPLET=root@157.230.185.124 scripts/deploy-with-keys.sh deploy
#        UMI_DROPLET=root@157.230.185.124 scripts/deploy-with-keys.sh check
#        #   -> "clean: droplet .env holds no plaintext key material"
#    The deploy ends with "migrations applied; deploy done". MIGRATE FAILED means the new
#    app is running on a schema it does not match: read the error, fix it, re-run the
#    migrate below; the step 3 backup is the fallback.

# 6. Migrate + collect static. The rig already ran migrate, and the image collected static
#    at build time (docker/Dockerfile), so both are no-ops here; re-run them only inside
#    the RUNNING container, which holds the keys:
docker exec docker-app-1 python manage.py migrate --noinput
docker exec docker-app-1 python manage.py collectstatic --noinput

# 7. Verify — and make one check prove NEW code is running.
#    On 2026-07-27 a deploy reported perfectly healthy while running the OLD tree:
#    the pull step hadn't run, and `ps app` said healthy and the site returned 200
#    the whole time, because nothing behaves differently when the code is merely
#    stale. Health and status codes cannot tell "deployed" from "believed
#    deployed". Always assert some string that ONLY exists in the new commit —
#    and get its expected count by grepping the merged tree, never from memory.
docker compose --env-file .env -f docker/docker-compose.prod.yml ps app   # want "healthy"
curl -sf https://reciprocalaid.network/about/ | grep -o "<a string you changed>"
```

## Rollback

If a deploy goes bad, restore the dump from step 3 and rebuild the previous commit. The restore
runs in the `db` container, which needs no app keys; the app comes back up from the laptop, as in
step 5:

```bash
# on the droplet
gunzip -c /var/backups/umi/umi-<timestamp>.sql.gz | \
  docker compose --env-file .env -f docker/docker-compose.prod.yml exec -T db \
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"
git checkout <previous-sha> && docker build -t umi-exchange:local -f docker/Dockerfile .

# then on the laptop
UMI_DROPLET=root@157.230.185.124 scripts/deploy-with-keys.sh deploy
```

(Pre-custody the last droplet line ended `&& docker compose --env-file .env -f
docker/docker-compose.prod.yml up -d app`, which now starts the app without keys.)

## Turning on real auto-deploy (later)

Set the repo variable `DEPLOY_ENABLED=true`. From then on, **every** push to `main`
deploys itself via the workflow's SSH job (host/user/key live in repo secrets
`DEPLOY_HOST` / `DEPLOY_USER` / `DEPLOY_SSH_KEY`). This is a standing change — leave it
off while you still want a hand on the wheel per deploy.

⚠️ **Under key custody, do not turn it on as it stands.** The workflow's job runs
`scripts/deploy.sh` on the droplet, which brings the app up with a plain `compose up -d app` and no
keys, so the first automatic deploy would take production down. The age identity lives only on the
steward's laptop by design, so no workflow can decrypt the keys. Auto-deploy needs a change to the
custody design first (`docs/key-custody-design.md`), decided by the steward.
