# UMI Exchange — VPS Deploy Runbook (fresh Ubuntu 24.04 droplet)

Written and verified against the **actual repo** (this checkout), not the old placeholder
runbook. Every command below has been checked line-by-line against
`docker/docker-compose.prod.yml`, `.env.example`, `docker/Caddyfile.prod`, `docker/Dockerfile`,
`config/settings/production.py`, and `scripts/`.

**Your situation (assumed by this runbook):**

- Droplet IP: **`143.244.167.7`**, fresh Ubuntu 24.04, you log in as **root**.
- Repo already cloned at **`/opt/umi-exchange`**.
- Docker + `docker compose` plugin already installed.
- `scripts/harden.sh` has **already run**: UFW + fail2ban are on. Its SSH step **failed**
  (Ubuntu 24 uses `ssh.service`, not `sshd.service`), which has consequences — see §0.

**What the old runbook got wrong (do not reuse it):** owner `williams-umi` (real owner is
`p949w6cqh2-boop`), image `ghcr.io/your-org/...` (placeholder), domain `umifoundation.org` (not
yours), and `.env` edits against variable names that don't match `.env.example`. This runbook
replaces all of that.

---

## ⚠️ §0 — FIRST: fix the SSH lock-out risk left by harden.sh (do this before anything else)

`scripts/harden.sh` runs under `set -euo pipefail`. Its SSH step is:

```
sed -i 's/#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/PasswordAuthentication yes/PasswordAuthentication no/'  /etc/ssh/sshd_config
sed -i 's/#PermitRootLogin yes/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config
systemctl restart sshd        # <-- FAILS on Ubuntu 24 (unit is ssh.service)
```

Because `systemctl restart sshd` failed, `set -e` **aborted the script at that line**. Consequences:

1. `/etc/ssh/sshd_config` was **already edited**: `PasswordAuthentication no` and
   `PermitRootLogin prohibit-password` are now written to disk.
2. The SSH daemon was **not restarted**, so the *running* daemon may still be using the old
   (password-allowed) config. **The moment SSH restarts or the box reboots, key-only login
   becomes mandatory.**
3. Step 1 of the script already enabled **unattended-upgrades with automatic reboot at 02:00**
   (`Unattended-Upgrade::Automatic-Reboot "true"`). So the box can reboot on its own tonight and
   apply the new SSH config — **if your key isn't working, that reboot locks you out.**
4. Steps 5–6 of harden.sh (logwatch, sysctl kernel params) never ran. Minor; §11 finishes them.

**Fix it safely now — do NOT close your current root session until every check passes.**

**0.1 — Confirm your public key is actually installed (in your current session):**

```bash
cat /root/.ssh/authorized_keys
```

You must see **your** public key here. If this file is empty or missing, **STOP** — paste your
public key in before going further, or you will be locked out:

```bash
# only if your key is NOT already present:
mkdir -p /root/.ssh && chmod 700 /root/.ssh
echo "ssh-ed25519 AAAA...your-actual-public-key... you@laptop" >> /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys
```

**0.2 — Confirm what harden.sh wrote and that the config is valid:**

```bash
grep -E '^\s*(PasswordAuthentication|PermitRootLogin)' /etc/ssh/sshd_config
sshd -t && echo "sshd config OK"
```

Expect `PasswordAuthentication no`, `PermitRootLogin prohibit-password`, and `sshd config OK`.

**0.3 — From a SECOND terminal on your laptop, prove key login works BEFORE you restart SSH:**

```bash
ssh root@143.244.167.7 'echo key-login-works'
```

If that prints `key-login-works` without asking for a password, your key is good.
**If it asks for a password or fails, do NOT proceed — fix your key first (§0.1).**

**0.4 — Only after 0.3 succeeds, apply the SSH config using the correct unit name:**

```bash
systemctl restart ssh        # Ubuntu 24: the unit is ssh.service (NOT sshd.service)
systemctl status ssh --no-pager | head -5
```

**0.5 — From a THIRD fresh terminal, confirm you can still get in:**

```bash
ssh root@143.244.167.7 'echo still-in'
```

Keep your original session open until this prints `still-in`. Now the SSH state is consistent and
the 02:00 auto-reboot is safe.

**0.6 — Confirm the firewall (set by harden.sh) allows the ports Caddy needs:**

```bash
ufw status verbose
```

You need `22/tcp` (or `OpenSSH`), `80/tcp`, and `443/tcp` **ALLOW**. harden.sh opens all three, so
this should already be correct. Ports 80 and 443 are required for Caddy and for Let's Encrypt's
HTTP-01 certificate challenge.

> **DigitalOcean note:** if you attached a **Cloud Firewall** to the droplet in the DO control
> panel, that is *separate* from UFW. Make sure it also allows inbound **22, 80, 443**, or TLS
> issuance and the site will fail even though UFW looks correct.

---

## §1 — Real values you must provide

You cannot deploy without these. Fill them in as you go.

| What | Example | Notes |
|------|---------|-------|
| **Domain name** | `app.example.org` | You must own it and be able to edit DNS. Caddy gets a free Let's Encrypt cert for this name automatically. |
| **DNS A record** | `app.example.org → 143.244.167.7` | Set this **before** launching Caddy (§6), or cert issuance fails until it propagates. |
| **`SECRET_KEY`** | *(generated in §4)* | Django signing key. Generated, never chosen. |
| **`ENCRYPTION_KEY`** | *(generated in §4)* | Fernet key for field encryption. Production **refuses to boot** if empty. |
| **`DB_PASSWORD`** | *(generated in §4)* | Postgres password. Generated, never chosen. |
| **GHCR token** *(only if you use Option B in §3)* | a GitHub PAT with `read:packages` | Only needed to pull the prebuilt image from a **private** GHCR package. |

Optional (leave blank to skip): SMTP mail (`EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD`), Sentry
(`SENTRY_DSN`), off-site backups (Backblaze B2 keys).

Set your domain once as a shell variable so the rest of the runbook is copy-paste:

```bash
export DOMAIN="app.example.org"     # <-- replace with YOUR real domain
```

---

## §2 — Point DNS at the droplet

In your DNS provider, add an **A record**:

```
app        A        143.244.167.7
```

(Use the host/name that matches `$DOMAIN`. For an apex like `example.org`, use `@`.)

Verify it resolves before continuing (Caddy needs this to get a TLS cert):

```bash
dig +short "$DOMAIN"      # must print 143.244.167.7
```

If `dig` isn't installed: `apt-get install -y dnsutils`. Propagation can take a few minutes.

---

## §3 — Get the application image

The prod compose file ships with a **placeholder** image line:
`image: ghcr.io/your-org/umi-exchange:latest`. Pick **one** option below and point the compose
file at a real image.

### Option A — Build the image locally on the droplet (recommended: no registry dependency)

The build copies the whole repo into the image (`COPY . .`). **Your `.env` will hold secrets** and
the local `.venv` is large — create a `.dockerignore` first so neither is baked into the image:

```bash
cd /opt/umi-exchange
cat > .dockerignore <<'EOF'
.env
.env.*
.venv
.git
*.sqlite3
node_modules
__pycache__
EOF
```

Build and tag it (the canonical Dockerfile is `docker/Dockerfile`; context is the repo root):

```bash
cd /opt/umi-exchange
docker build -t umi-exchange:local -f docker/Dockerfile .
```

Point the compose file at your local tag:

```bash
sed -i 's#ghcr.io/your-org/umi-exchange:latest#umi-exchange:local#' docker/docker-compose.prod.yml
grep 'image:' docker/docker-compose.prod.yml | head -1   # verify: image: umi-exchange:local
```

> **1 GB droplet?** Building `cryptography`/`psycopg` can exhaust RAM and get the build OOM-killed.
> If `docker build` dies, add temporary swap first (safe, reversible):
> ```bash
> fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
> ```
> To make it permanent: `echo '/swapfile none swap sw 0 0' >> /etc/fstab`. To remove later:
> `swapoff /swapfile && rm /swapfile` (and delete the fstab line).

### Option B — Pull the prebuilt image from GHCR

The real package is **`ghcr.io/p949w6cqh2-boop/umi-exchange`** (owner `p949w6cqh2-boop`).

If the package is **public**, no login is needed. If it's **private**, log in with a GitHub
Personal Access Token that has the `read:packages` scope:

```bash
# create the PAT at github.com → Settings → Developer settings → Personal access tokens
export GHCR_PAT="ghp_your_token_here"
echo "$GHCR_PAT" | docker login ghcr.io -u p949w6cqh2-boop --password-stdin
```

Point the compose file at the real image and pull it:

```bash
cd /opt/umi-exchange
sed -i 's#ghcr.io/your-org/umi-exchange:latest#ghcr.io/p949w6cqh2-boop/umi-exchange:latest#' docker/docker-compose.prod.yml
grep 'image:' docker/docker-compose.prod.yml | head -1   # verify the new image path
docker compose -f docker/docker-compose.prod.yml pull app
```

> If `pull` returns `denied` / `manifest unknown`, the tag doesn't exist or the package is private
> and your token lacks `read:packages`. Use Option A (build locally) instead.

---

## §4 — Configure `.env`

`.env` lives at the repo root (`/opt/umi-exchange/.env`); the compose file loads it via
`env_file: ../.env`. It is git-ignored, so your secrets never get committed.

Start from the example and fill in the real values. The commands below **generate** the three
secrets and write them with `printf` (safe for any special characters):

```bash
cd /opt/umi-exchange
cp .env.example .env

# --- generate the three secrets (pure python3 stdlib; no extra libs needed) ---
SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(64))')"
ENCRYPTION_KEY="$(python3 -c 'import os,base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())')"
DB_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"

# --- write the REQUIRED values into .env (delete any existing line, then append) ---
set_env() { sed -i "/^$1=/d" .env; printf '%s=%s\n' "$1" "$2" >> .env; }

set_env SECRET_KEY       "$SECRET_KEY"
set_env ENCRYPTION_KEY   "$ENCRYPTION_KEY"
set_env DB_PASSWORD      "$DB_PASSWORD"
set_env ALLOWED_HOSTS    "$DOMAIN,localhost,127.0.0.1"
set_env SITE_URL         "https://$DOMAIN"
set_env DEBUG            "False"
set_env DJANGO_SETTINGS_MODULE "config.settings.production"
set_env DEFAULT_FROM_EMAIL "UMI Exchange <noreply@$DOMAIN>"
```

**Which `.env` variables actually matter** (verified against the compose file and settings):

- **Generate (secrets):** `SECRET_KEY`, `ENCRYPTION_KEY`, `DB_PASSWORD`.
  - `SECRET_KEY` — production **refuses to start** if it's empty or the dev default.
  - `ENCRYPTION_KEY` — production **refuses to start** if empty (it would silently disable PII
    encryption). A Fernet key = 32 random bytes, url-safe-base64 encoded (what the command makes).
  - `DB_PASSWORD` — used by **both** the `db` service (`POSTGRES_PASSWORD`) **and** the app's DB
    connection string. Must be set or Postgres won't come up.
- **Set (real values):** `ALLOWED_HOSTS` (your domain — Django rejects requests otherwise when
  `DEBUG=False`), `SITE_URL` (`https://your-domain`), `DEBUG=False`,
  `DJANGO_SETTINGS_MODULE=config.settings.production`.
- **Ignore — the compose file overrides these for the app container, so `.env` values don't apply:**
  `DATABASE_URL`, `REDIS_URL`. The compose `environment:` block sets
  `DATABASE_URL=postgres://umi:<DB_PASSWORD>@db:5432/umi_exchange` and
  `REDIS_URL=redis://redis:6379/0` directly. (This also means Redis is always wired in, so the
  "production requires a shared cache" boot-guard is satisfied automatically — good.)
- **Optional:** `EMAIL_HOST_USER`+`EMAIL_HOST_PASSWORD` (production auto-switches to real SMTP the
  moment these are set), `SENTRY_DSN`, `HEALTH_CHECK_TOKEN`, the `BACKUP_*` Backblaze keys.
- **Leave commented:** `APP_DB_USER` / `APP_DB_PASSWORD` / `AUDIT_DB_APP_ROLE`. These enable the
  optional two-role hardening (app role ≠ DB owner). The default single-role setup (app connects as
  `umi`) works out of the box; see §10 if you later want the split.

Sanity-check that the three secrets are non-empty in `.env`:

```bash
grep -E '^(SECRET_KEY|ENCRYPTION_KEY|DB_PASSWORD)=' .env | sed 's/=.*/=<set>/'
```

---

## §5 — Fix the Caddy config (3 real corrections)

The shipped `docker/Caddyfile.prod` has **three problems** that would break a real deploy, because
the compose file never wires up what the Caddyfile assumes:

1. **Domain is never set.** The site block is `{$DOMAIN:localhost}`, but the `caddy` service in the
   compose file has **no** `environment`/`env_file`, so `DOMAIN` is unset → Caddy would serve as
   `localhost` and get **no TLS cert for your domain**. → We hardcode your real domain.
2. **Static files 404.** The Caddyfile serves `/static/*` from `/srv/static`, but that path is
   **never mounted** into the caddy container → every CSS/JS request 404s and the site renders
   unstyled. → We remove that block and let the app's **WhiteNoise** (already configured and
   compiled into the image) serve `/static/`.
3. **Caddy fails to start on the file-log block.** The Caddyfile logs to `/var/log/caddy/access.log`,
   but that directory isn't mounted/created in the container → Caddy errors at startup. → We drop
   it and use Caddy's default stdout logging (view with `docker compose logs caddy`).

Write the corrected file (this preserves the reverse-proxy, the trusted `X-Real-IP` handling, and
all security headers — it only removes the two broken blocks and hardcodes your domain):

```bash
cd /opt/umi-exchange
cat > docker/Caddyfile.prod <<EOF
# Corrected for this deployment (see docs/deploy/vps-runbook.md §5).
# Domain hardcoded; /static served by the app's WhiteNoise; logs go to stdout.
$DOMAIN {
    reverse_proxy app:8000 {
        # Caddy REPLACES X-Real-IP with the real connecting IP on every request.
        # Django trusts this header for rate-limiting and salted audit-log IP hashing.
        # Only safe while Caddy is the edge (no CDN/LB in front of it).
        header_up X-Real-IP {remote_host}
    }

    encode gzip zstd

    header {
        -Server
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
        Referrer-Policy "strict-origin-when-cross-origin"
        Permissions-Policy "camera=(), microphone=(), geolocation=(), payment=()"
        # CSP is set by Django; Caddy does not override it.
    }

    # Health check (no auth). Same trusted X-Real-IP replacement as the main block.
    handle /health/* {
        reverse_proxy app:8000 {
            header_up X-Real-IP {remote_host}
        }
    }
}
EOF

# verify the domain landed correctly (should print:  app.example.org {)
head -3 docker/Caddyfile.prod
```

> The heredoc is intentionally **unquoted** so `$DOMAIN` expands. Nothing else in the file uses a
> `$`, so Caddy placeholders like `{remote_host}` pass through untouched — confirm with the
> `head -3` output above.

---

## §6 — Launch the stack

DNS (§2) should already point at the droplet so Caddy can get its certificate.

```bash
cd /opt/umi-exchange
docker compose -f docker/docker-compose.prod.yml up -d
```

This starts five containers: `app` (gunicorn), `db` (Postgres 16), `redis`, `caddy` (TLS + reverse
proxy). Check them:

```bash
docker compose -f docker/docker-compose.prod.yml ps
```

Wait for `db` to become **healthy** and `app` to be **running** before the next step:

```bash
docker compose -f docker/docker-compose.prod.yml logs -f app     # Ctrl-C to stop tailing
```

> If `app` restart-loops with `ImproperlyConfigured: SECRET_KEY must be set...` or `ENCRYPTION_KEY
> must be set...`, your `.env` didn't get those values — recheck §4.

---

## §7 — Initialize the database, static files, and admin user

Run these **after** the containers are up. `manage.py` inside the container already runs with
`config.settings.production` (set by the compose `environment`), using the secrets from `.env`:

```bash
cd /opt/umi-exchange
C="docker compose -f docker/docker-compose.prod.yml"

# 1. Database schema
$C exec app python manage.py migrate

# 2. Collect static into WhiteNoise's STATIC_ROOT (ensures the manifest exists so
#    {% static %} tags resolve; harmless if the image already collected them)
$C exec app python manage.py collectstatic --noinput

# 3. Create your admin account (interactive — asks for username/email/password)
$C exec app python manage.py createsuperuser
```

---

## §8 — Verify

```bash
cd /opt/umi-exchange
C="docker compose -f docker/docker-compose.prod.yml"

# Django's own production audit — should report 0 issues
$C exec app python manage.py check --deploy

# Health endpoint from the droplet itself (app listens on 8000 inside the network)
$C exec app python -c "import urllib.request; print(urllib.request.urlopen(urllib.request.Request('http://localhost:8000/health/', headers={'X-Forwarded-Proto':'https'})).read())"

# Public health check over HTTPS (real cert + Caddy in front)
curl -sf "https://$DOMAIN/health/" && echo   # expect: {"status": "ok"} (or similar)
```

Then in a browser:

- `https://$DOMAIN/` loads with a valid padlock (Let's Encrypt cert) and **styled** pages
  (confirms §5 static fix worked).
- Register an account, create a community, post a need — full checklist mirrors the app's
  own `DEPLOY.md` "Verification Checklist".

> **Cert not issued yet?** `docker compose ... logs caddy` will show the ACME attempts. The usual
> causes are DNS not yet pointing at `143.244.167.7` (§2) or port 80/443 blocked (§0.6). Caddy
> retries automatically once DNS/ports are correct.

---

## §8.1 — External uptime + SSL monitoring (UptimeRobot)

Local structured logs (in `config/settings/production.py`) capture errors on the box. For
outside-in "is it up + is the cert valid" monitoring, use **UptimeRobot** (free tier: 50 monitors,
5-min checks). It only pings the public `/health/` endpoint — **no parishioner data leaves the box**.
(Decision + rationale, incl. why not hosted Sentry/GlitchTip, is in `docs/monitoring-decision.md`.)

1. Sign up at **uptimerobot.com**, then verify an email **Alert Contact**
   (My Settings → Add Alert Contact → Email).
2. Dashboard → **+ New Monitor**:
   - **Monitor Type:** `HTTP(s)`
   - **Friendly Name:** `Reciprocal Aid Network`
   - **URL:** `https://<your DOMAIN>/health/`
   - **Monitoring Interval:** `5 minutes`
   - **Alert Contacts:** tick your email
3. **Enable the SSL / certificate-expiry alert** on the monitor (notify before expiry). Caddy
   auto-renews the Let's Encrypt cert, so this is a backstop, not the primary renewal path.
4. **Optional (recommended):** add **Keyword monitoring** — type `exists`, keyword `ok` — so a
   `200` with a broken body still alerts (the health endpoint returns `{"status": "ok"}`).
5. **Create Monitor.**

**Healthy:** the monitor shows green **Up**, pinging `/health/` every 5 min; you get an email if it
goes down or the cert nears expiry.

> `/health/` is intentionally public and unauthenticated (returns 200 without a token) so an external
> pinger can reach it. If you ever set `HEALTH_CHECK_TOKEN` in `.env`, the endpoint stops being open
> and this monitor breaks — point the monitor at the apex `/` instead, or leave the token empty.

---

## §9 — Daily backups

`scripts/backup.sh` dumps the Postgres DB (gzip) to `/var/backups/umi/`. It expects the DB
container to be named **`docker-db-1`**, which is exactly what this compose project produces (the
compose project name defaults to the `docker/` directory), so it works as-is. Note: the dump
contains only KEK-wrapped ciphertext — it is **not** decryptable without `ENCRYPTION_KEY` from
`.env`, so store backups somewhere that does **not** also hold that key.

Run once to confirm it works, then schedule it:

```bash
bash /opt/umi-exchange/scripts/backup.sh
ls -la /var/backups/umi/                         # you should see a umi-<timestamp>.sql.gz

# schedule daily at 03:00 (appends to root's crontab)
( crontab -l 2>/dev/null; echo "0 3 * * * /opt/umi-exchange/scripts/backup.sh >> /var/log/umi-backup.log 2>&1" ) | crontab -
crontab -l
```

Off-site copies (optional): fill `BACKUP_BUCKET` / `BACKUP_ACCESS_KEY` / `BACKUP_SECRET_KEY` /
`BACKUP_ENDPOINT` in `.env` (Backblaze B2) — `backup.sh` uploads when those are set.

### §9.1 — Rehearse the restore (an untested backup is a guess)

Taking backups and never restoring one means you find out whether they work on the day you cannot
afford to find out. `scripts/dr_sim.sh` restores into a **scratch** database and checks the result.
It refuses to run without an explicit scratch target, and refuses outright if that target is the
live database.

```bash
# a scratch database to restore into — NOT the app's
docker compose --env-file .env -f docker/docker-compose.prod.yml exec -T db \
  psql -U umi -c "CREATE DATABASE umi_scratch;"

# rehearse from the newest LOCAL backup, asserting a known community survives
cd /opt/umi-exchange
DR_CONFIRM=yes-restore-into-scratch \
DR_DATABASE_URL=postgres://umi:$DB_PASSWORD@localhost:5432/umi_scratch \
DR_EXPECT_SLUG=st-brigids \
  bash scripts/dr_sim.sh
```

It prints row counts, asserts the database is not empty, asserts your known community is present,
and runs `migrate --check` so a restore onto a stale schema cannot report success. **A rehearsal
from B2 is the stronger one** — it proves the off-box copy is real, not just that the dump parses.
Add `DR_BUCKET` / `DR_ACCESS_KEY` / `DR_SECRET_KEY` to do that.

Drop the scratch database afterwards: `psql -U umi -c "DROP DATABASE umi_scratch;"`.

### §9.2 — Confirm old backups actually disappear

Retention is a promise in `docs/privacy-retention.md`, and an unbounded pile of backups quietly
defeats crypto-shred: a record erased from the live database still sits in every dump taken before
the erasure. Two halves, and **both** have to be checked:

```bash
# local: backup.sh prunes on every run, so a file older than RETENTION_DAYS should be gone
ls -la --time-style=long-iso /var/backups/umi/ | head
# nothing here should be older than RETENTION_DAYS (default 30)
```

**The B2 half is not automatic.** `backup.sh` never deletes anything remote — it relies on a bucket
**lifecycle rule** you must create by hand in the Backblaze console, set to the same age as
`RETENTION_DAYS`. Until that rule exists, remote backups accumulate forever. Verify it by listing
the bucket and confirming nothing predates the window:

```bash
aws s3 ls "s3://$BACKUP_BUCKET/umi-backups/" --endpoint-url "$BACKUP_ENDPOINT" | head
```

---

## §10 — Updates & maintenance

Because you're running a **specific image** (local build or a pinned GHCR tag), updates depend on
which option you chose in §3. Note: the shipped `scripts/deploy.sh` is written for the **GHCR
(pull)** flow and calls a non-existent `docker compose rollback` — use the explicit commands below
instead.

**If you built locally (Option A):**

```bash
cd /opt/umi-exchange
git pull
bash scripts/backup.sh                                             # snapshot first
docker build -t umi-exchange:local -f docker/Dockerfile .
docker compose -f docker/docker-compose.prod.yml up -d
docker compose -f docker/docker-compose.prod.yml exec app python manage.py migrate
docker compose -f docker/docker-compose.prod.yml exec app python manage.py collectstatic --noinput
```

**If you pull from GHCR (Option B):**

```bash
cd /opt/umi-exchange
git pull
bash scripts/backup.sh
docker compose -f docker/docker-compose.prod.yml pull app
docker compose -f docker/docker-compose.prod.yml up -d
docker compose -f docker/docker-compose.prod.yml exec app python manage.py migrate
docker compose -f docker/docker-compose.prod.yml exec app python manage.py collectstatic --noinput
```

> **After any `git pull`:** it will try to overwrite your edited `docker/Caddyfile.prod` and
> `docker/docker-compose.prod.yml`. If git reports a conflict or refuses to pull, re-apply the §3
> `sed` (image line) and §5 (Caddyfile) edits afterward. Consider committing them on a local branch
> so pulls rebase cleanly.

Optional audit hardening (defense-in-depth; not required for the app to run):

```bash
docker compose -f docker/docker-compose.prod.yml exec app python manage.py restrict_audit_permissions
```

Handy checks:

| Task | Command |
|------|---------|
| Container status | `docker compose -f docker/docker-compose.prod.yml ps` |
| App logs | `docker compose -f docker/docker-compose.prod.yml logs app --tail 100` |
| Caddy / TLS logs | `docker compose -f docker/docker-compose.prod.yml logs caddy --tail 100` |
| Restart all | `docker compose -f docker/docker-compose.prod.yml restart` |
| Firewall / fail2ban | `ufw status && fail2ban-client status sshd` |
| Disk space | `df -h` |

---

## §11 — Finish the hardening harden.sh didn't complete (optional)

harden.sh aborted after the SSH step, so its logwatch + kernel-param steps never ran. Re-running
the whole script is safe (it's idempotent) **and** now that the SSH unit issue is understood, its
`systemctl restart sshd` will still fail on Ubuntu 24 — so either re-run and ignore that one error,
or just apply the two leftover pieces directly:

```bash
# kernel hardening params (harden.sh step 6)
sysctl -w net.ipv4.conf.all.accept_source_route=0
sysctl -w net.ipv4.conf.all.accept_redirects=0
sysctl -w net.ipv4.conf.all.log_martians=1
```

(logwatch in step 5 is just daily log summaries — install with `apt-get install -y logwatch` if you
want them.)

---

## §12 — If you get locked out (recovery)

If SSH ever refuses your key and you're shut out:

1. **DigitalOcean → your droplet → Access → Launch Droplet Console** (or "Recovery Console"). This
   is an out-of-band console that does **not** use SSH, so the SSH config can't lock it out. Log in
   as `root` with the root password (set one under **Access → Reset Root Password** if you never
   did; DO emails a temporary password).
2. In that console, re-enable password login temporarily or fix your key:
   ```bash
   sed -i 's/^PasswordAuthentication no/PasswordAuthentication yes/' /etc/ssh/sshd_config
   systemctl restart ssh
   ```
3. Fix `/root/.ssh/authorized_keys`, then re-tighten (`PasswordAuthentication no`) and
   `systemctl restart ssh` — after re-verifying key login per §0.

---

## Appendix — every value that differs from the old (placeholder) runbook

| Old placeholder | Correct value (this repo) |
|-----------------|---------------------------|
| owner `williams-umi` | `p949w6cqh2-boop` |
| `git clone .../williams-umi/umi-exchange` | already at `/opt/umi-exchange` (skip clone) |
| image `ghcr.io/your-org/umi-exchange:latest` | build `umi-exchange:local` **or** `ghcr.io/p949w6cqh2-boop/umi-exchange:latest` |
| domain `app.umifoundation.org` | **your** domain (`$DOMAIN`) → A record to `143.244.167.7` |
| `.env` var `generate-with-python...` (doesn't exist) | real key is `ENCRYPTION_KEY=` in `.env.example` |
| `sed` on `SITE_URL`/`ALLOWED_HOSTS`/`DEBUG` (fragile) | `set_env` helper writes the real keys safely (§4) |
| `systemctl restart sshd` | `systemctl restart ssh` (Ubuntu 24) |
| Caddyfile `{$DOMAIN:localhost}` unset | hardcoded to `$DOMAIN` (§5) — otherwise no TLS |
| Caddy `/static` from unmounted `/srv/static` | removed; WhiteNoise serves `/static` (§5) |
| Caddy file-log to unmounted `/var/log/caddy` | removed; stdout logging (§5) |
| `scripts/deploy.sh` (`docker compose rollback` — not real) | explicit update commands in §10 |
