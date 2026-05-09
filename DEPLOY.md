# UMI Exchange — Deploy Guide for Jasiah

**Time needed: ~1 hour. Cost: $5/month.**

## Option A: DigitalOcean (Easiest)

### Step 1: Create a Server (5 minutes)

1. Go to https://digitalocean.com and create an account
2. Click **Create → Droplet**
3. Choose: **Ubuntu 24.04**, **Basic**, **$6/month** (1 CPU, 1 GB RAM — enough to start)
4. Choose a region close to your community (e.g., San Francisco)
5. Under Authentication: **SSH Key** (recommended) or **Password**
6. Click **Create Droplet**
7. Copy the IP address shown (e.g., `164.90.xxx.xxx`)

### Step 2: Point Your Domain (5 minutes)

If you have a domain (e.g., `umifoundation.org`):
1. In your DNS provider, add an **A record**: `app` → `164.90.xxx.xxx`
2. This makes `app.umifoundation.org` point to your server

If you don't have a domain yet, you can use the IP address directly.

### Step 3: Connect to the Server (2 minutes)

```bash
ssh root@164.90.xxx.xxx
```

### Step 4: Install Docker (5 minutes)

```bash
# Install Docker
curl -fsSL https://get.docker.com | sh

# Install Docker Compose plugin
apt-get install -y docker-compose-plugin

# Verify
docker --version
docker compose version
```

### Step 5: Deploy UMI Exchange (10 minutes)

```bash
# Clone the project
git clone https://github.com/williams-umi/umi-exchange.git /opt/umi-exchange
cd /opt/umi-exchange

# Harden the server
sudo bash scripts/harden.sh

# Create your environment file
cp .env.example .env

# Generate secure keys
SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(50))")
sed -i "s/change-me-to-a-random-50-char-string/$SECRET/" .env

ENC_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
sed -i "s|generate-with-python.*|$ENC_KEY|" .env

# Set your domain (or IP address)
sed -i "s|SITE_URL=http://localhost:8000|SITE_URL=https://app.umifoundation.org|" .env
sed -i "s|ALLOWED_HOSTS=localhost,127.0.0.1|ALLOWED_HOSTS=app.umifoundation.org,localhost|" .env
sed -i "s|DEBUG=True|DEBUG=False|" .env

# Set a database password
DB_PASS=$(python3 -c "import secrets; print(secrets.token_urlsafe(24))")
sed -i "s|change-me-in-production|$DB_PASS|" .env

# Update Caddyfile with your domain
sed -i "s|\$DOMAIN:localhost|app.umifoundation.org|" docker/Caddyfile.prod

# Start everything
docker compose -f docker/docker-compose.prod.yml up -d

# Wait for database to be ready
sleep 10

# Run database setup
docker compose -f docker/docker-compose.prod.yml exec app python manage.py migrate
docker compose -f docker/docker-compose.prod.yml exec app python manage.py createsuperuser

# That's it. Visit https://app.umifoundation.org
```

### Step 6: Create Your First Community (5 minutes)

1. Visit your site and click "Join a Community"
2. First, register an account
3. Then click "create a new community" on the join page
4. Name it (e.g., "Williams Family Pilot" or your parish name)
5. You're now the admin
6. Go to Settings → copy the **Join Code** or download the **QR Code**
7. Share the QR code with your first 10 members

### Step 7: Set Up Daily Backups (2 minutes)

```bash
# Schedule daily backup at 3 AM
echo "0 3 * * * /opt/umi-exchange/scripts/backup.sh >> /var/log/umi-backup.log 2>&1" | crontab -
```

---

## Option B: Run Locally First (for testing)

If you want to test on your laptop before deploying:

```bash
git clone https://github.com/williams-umi/umi-exchange.git
cd umi-exchange

# Install Python dependencies
pip install django django-environ dj-database-url django-htmx django-ratelimit \
  django-guardian whitenoise cryptography djangorestframework qrcode pillow

# Run with SQLite (no PostgreSQL needed for testing)
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver

# Visit http://localhost:8000
```

---

## Verification Checklist

After deploying, verify everything works:

- [ ] Visit the site — landing page loads
- [ ] Register a new account
- [ ] Create a community
- [ ] QR code generates on the settings page
- [ ] Post a need
- [ ] Post an offer (from a second account)
- [ ] Propose a match
- [ ] Accept the match — **contact info appears** (the lock opens!)
- [ ] Mark the match as fulfilled
- [ ] Check the coordinator dashboard — metrics show correctly
- [ ] Health check: `curl https://yoursite/health/` returns `{"status": "ok"}`

## If Something Goes Wrong

```bash
# Check if containers are running
docker compose -f docker/docker-compose.prod.yml ps

# View app logs
docker compose -f docker/docker-compose.prod.yml logs app --tail 50

# Restart everything
docker compose -f docker/docker-compose.prod.yml restart

# Nuclear option: rebuild from scratch
docker compose -f docker/docker-compose.prod.yml down
docker compose -f docker/docker-compose.prod.yml up -d --build
```

## Monthly Maintenance

| Task | Command |
|------|---------|
| Update the app | `cd /opt/umi-exchange && git pull && docker compose -f docker/docker-compose.prod.yml up -d --build` |
| Check backups | `ls -la /var/backups/umi/` |
| View server security | `sudo ufw status && sudo fail2ban-client status sshd` |
| Check disk space | `df -h` |
