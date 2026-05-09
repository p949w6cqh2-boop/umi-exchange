wget https://repo.protonvpn.com/debian/dists/stable/main/binary-all/protonvpn-stable-release_1.0.8_all.deb
sudo dpkg -i ./protonvpn-stable-release_1.0.8_all.deb && sudo apt update
echo "0b14e71586b22e498eb20926c48c7b434b751149b1f2af9902ef1cfe6b03e180 protonvpn-stable-release_1.0.8_all.deb" | sha256sum --check -
sudo apt install proton-vpn-gnome-desktop
sudo apt install gnome-shell-extension-appindicator gnome-shell-extension-prefs
cd ~/Downloads
ls -la *.tar*
tar -xvf Umi exchange finale .tar -C ~/
tar -xvf Umiexchangefinale.tar -C ~/
tar -xvf 'Umi exchange finale .tar' -C ~/
cd `/umi-exchange ls -la
cd ~/umi-exchange ls -la

cd ~/Downloads
sudo apt update
/help
cd ~/Downloads
ls -la *.tar*
ta -xvf 'Umi exchange finale .tar' -C ~/
tar -xvf "Umi exchange finale .tar' -C ~/
tar -xvf "Umi exchange finale .tar" -C ~/
cd ~umi-exchange
cd ~'Umi exchange finale .tar'
cd ~/umi-exchange ls -la
cd ~/umi-exchange
ls -la
sudo apt update
sudo apt install docker.io docker-compose -y
sudo systemctl start docker
sudo systemctl enable docker
sudo usermod -aG docker $USER
cd ~/umi-exchange
cp .env.example .env
echo "SECRET_KEY=$(python3 -c 'from django.core.managment.utils import get_random_secret_key; print(get_random_secret_key())')">> .env
cd ~/umi-exchange
sudo systemctl status docker
cd ~/umi-exchange
sudo systemctl status docker
sudo systemctl is-active docker
cd ~/umi-exchange
ls -la
find ~ -name "docker-compose.yml" 2>/dev/null
docker compose up -d --build
docker-compose up -d --build
docker compose exec app python manage.py migrate
docker-compose exec app python manage.py migrate
docker-compose version
sudo apt remove docker-compose
sudo apt update
apt list --upgradble
apt list --upgradable
sudo apt install docker-compose-plugin
sudo apt update
docker compose version
docker-compose version
sudo apt update
sudo apt install docker-compose-plugin
sudo apt install ca-certificates
curl -y
sudo apt install ca-certificates curl -y
sudo install -m 0755 -d /etc/apt/keyrings
mkdir -p ~/.docker/cli-plugins/
curl -SL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64 -o
curl -SL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64 -o ~/.docker/cli-plugins/docker-compose
chmod +x ~/.docker/cli-plugins/docker-compose
docker-compose version
docker compose version
sudo apt install docker-compose
cd ~/umi-exchange
docker compose up -d --build
docker-compose up -d --build
sudo apt remove docker-compose
which docker-compose 
sudo rm /user/local/bin/docker-compose
which docker-compose sudo rm /user/local/bin/docker-compose
mkdir -p ~/.docker/cli-plugins/
curl -SL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64 -o ~/.docker/cli-plugins/docker-compose
chmod +x ~/.docker/cli-plugins/docker-compose
docker compose version
echo 'export PATH="$HOME/.docker/cli-plugins:$PATH"' >> ~/.bashrc source ~/.bashrc
cd ~/umi-exchange docker compose up -d --build
cd ~/umi-exchange
docker compose up -d --build
docker compose ps
pwd
ls -la
find ~ -name "*.tar" -type f 2>/dev/null
mkdir -p ~/umi-exchange
cd ~/umi-exhange
cd ~/umiexchange
cd ~/umi-exchange
tar -xvf /path/to/'Umi exchange finale .tar'
tar -xvf /path/to/umi-exchange
tar -xvf /path/to/'Umi exchange .tar'
ls -la
ms umi-exchange/* ./ rmdir umi-exchange
cd ~/umi-exchange
cp .env.example .env 
nano .env
pwd
ls -la
nano docker-compose.yml
nano .env.example
python3 -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'
ls -la
cd umi-exchange
ls -la
cat > docker-compose.yml << 'EOF'
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER}"]
    networks:
      - backend

  redis:
    image: redis:7-alpine
    command: redis-server --requirepass ${REDIS_PASSWORD}
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "-a", "${REDIS_PASSWORD}", "ping"]
    networks:
      - backend

  app:
    build: .
    command: gunicorn config.wsgi:application --bind 0.0.0.0:8000
    env_file:
      - .env
    volumes:
      - static_files:/app/staticfiles
      - media_files:/app/mediafiles
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    networks:
      - backend

  caddy:
    image: caddy:2-alpine
    ports:
      - "80:80"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - static_files:/srv/static:ro
      - media_files:/srv/media:ro
    depends_on:
      - app
    networks:
      - backend
      - frontend

volumes:
  postgres_data:
  redis_data:
  static_files:
  media_files:

networks:
  backend:
    internal: true
  frontend:
EOF

cat > Dockerfile << 'EOF'
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
EOF

docker compose up -d --build
rm .env
cp .env.example.env
rm .env
sudo apt update && sudo apt upgrade -y
sudo apt install -y git python3 python3-pip python3-venv docker.io docker-compose curl
sudo usermod -aG docker $USER
sudo snap install code --classic
sudo apt update && sudo apt upgrade -y
sudo apt install -y git python3 python3-pip python3-venv docker.io docker-compose curl
sude usermod -aG docker $USER
sudo usermod -aG docker $USER
xurl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
source ~/.bashrc
unzip umi-exchange.zip
tar -xzf umi-exchange.tar.gz
curl -o- https:// raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
export ANTHROPIC_API_KEY="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"
echo 'export ANTHROPIC_API_KEY="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"' >> ~/.bashrc
claude-code "Write a Python function that adds two numbers"
npm prefix -g
ls $(npm prefix -g)/bin
export PATH="$PATH:$(npm prefix -g)/bin"
claude --version
echo 'export PATH="$PATH:$(npm prefix -g)/bin"' >>~/.bashrc
source ~/.bashrc
sudo npm install -g @anthropic-ai/claude-code
$(npm prefix -g)/bin/claude --version
nom ptrfix -g
npm prefix -g
ls $(npm prefix -g)/bin/claude
export PATH="$PATH:$(npm prefix -g)/bin"
claude --version
echo 'export PATH="$PATH:$(npm prefix -g)/bin"' >> ~/.bashrc
source ~/.bashrc
npm install -g @anthropic-ai/claude-code --verbose
export PATH="$PATH:$(npm prefix -g)/bin"
echo 'export PATH="$PATH:$(npm prefix -g)/bin"' >> ~/.bashrc
export ANTHROPIC_API_KEY="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"
echo 'export ANTHROPIC_API__KEY="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"' >> ~/.bashrc source ~/.bashrc
kdir -p ~/umi-exchange cd ~/umi-exchange nano project-prompt.txt
mkdit -p ~umi-exchange cd ~/umi-exchange nano project-promt.txt
mkdir -p ~umi-exchange cd ~/umi-exchange nano project-prompt.txt
# TASK
Generate a complete, production‑ready Django project for the UMI Protocol v0.1 reference implementation at Core conformance level, including all optional refinements (QR join, households, VPS hardening script, optional 2FA, metadata privacy mitigations). The output must be a self‑contained project that can be deployed locally or on a server using Docker. Provide every file as a code block with its path from the project root.
## MENTAL MODEL
You are a senior full‑stack developer who has built many Django applications that scale from a single parish to a diocese. You write clean, secure, accessible code using the “boring technology” stack: Django, PostgreSQL, Redis, HTMX, Alpine.js, Tailwind CSS, Docker. You follow Django best practices: custom user model, environment‑based settings, class‑based views, and HTMX for dynamic interactions. You include comprehensive docstrings, comments, and error handling. You never compromise on privacy or accessibility.
## SOURCE MATERIAL
- The UMI Protocol v0.1 specification (entities: Need, Offer, Match, Consent, Referral, Attestation; state machines; security rules).
- The high‑fidelity visual specification (for UI hints – focus on functionality, not exact pixel perfection).
- The Core Exchange implementation plan (10‑week schedule, but we need the code now).
- The refinements: QR join, households, VPS hardening script, optional 2FA, metadata privacy (neighbourhood warnings, tooltips, community‑level config).
- The production hardening layer: health check, Sentry integration, security headers, structured logging, CI/CD pipelines (as `.github/workflows`), multi‑stage Dockerfile, production Docker Compose, backup/restore scripts, staging settings, scaling docs.
## DELIVERABLES
Generate the entire project as a set of files with paths and content. Include at minimum:
### 1. Configuration and Root Files
- `manage.py`
- `.env.example` (all environment variables: SECRET_KEY, DATABASE_URL, REDIS_URL, SENTRY_DSN, ENCRYPTION_KEY, etc.)
- `requirements.txt` (all dependencies: Django, DRF, psycopg, django‑redis, django‑htmx, django‑allauth, django‑guardian, django‑ratelimit, cryptography, django‑two‑factor‑auth, qrcode, sentry‑sdk, etc.)
- `pyproject.toml` (ruff configuration)
- `tailwind.config.js` (Tailwind setup)
- `docker-compose.yml` (development: PostgreSQL, Redis, app)
- `docker-compose.prod.yml` (production: app, db, redis, caddy, uptime‑kuma)
- `Dockerfile` (multi‑stage, non‑root user, healthcheck)
- `Caddyfile` (production reverse proxy with security headers)
- `LICENSE` (AGPL‑3.0)
- `README.md` (setup instructions, environment variables, deployment overview)
### 2. Django Project Configuration
- `config/settings/base.py`, `development.py`, `production.py`, `staging.py`
- `config/urls.py`, `wsgi.py`, `asgi.py`
### 3. Apps (complete with models, views, forms, templates, URLs)
- **accounts**: Custom User model (email optional, username login), registration/login (rate‑limited), profile settings (2FA toggle, household management).
- **households**: Household model, create/join views, registration integration.
- **communities**: Community, Member, Category models; join‑via‑code; community settings (QR code generation, neighbourhood mode).
- **needs**: Need model (with `on_behalf_of` encryption), create/detail views, soft validation for neighbourhood privacy.
- **offers**: Offer model (availability JSON, radius), create/detail views.
- **matches**: Match model with state machine, proposal/accept/fulfill/cancel views, contact revelation logic, race condition handling (SELECT FOR UPDATE).
- **notifications**: Notification model, adapter (in‑app and email), header badge.
- **dashboard**: Coordinator dashboard (metrics, stale needs, category chart, export CSV).
- **audit**: AuditLog model, middleware, management command to set DB permissions (INSERT only).
- **health**: Health check endpoint (db, cache).
- **consent**: Consent model (stub for Core, full UI for Extended).
### 4. Templates
- `base.html` (HTMX/Alpine includes, CSS variables, protocol badge, toast container)
- Components: `_need_card.html`, `_offer_card.html`, `_category_grid.html`, `_urgency_selector.html`, `_match_timeline.html`, `_contact_info_box.html`, `_metric_card.html`, `_filter_bar.html`, `_notification_badge.html`, `_primary_button.html`, `_protocol_badge.html`, `_trust_badge.html`, `_empty_state.html`
- Page templates: `landing.html`, `login.html`, `register.html`, `join.html`, `feed.html`, `need_create.html`, `need_detail.html`, `offer_create.html`, `offer_detail.html`, `match_detail.html`, `dashboard.html`, `settings.html`, `household_create.html`, `household_join.html`, `technology.html`
### 5. Static Assets
- `static/css/input.css` (Tailwind directives)
- `static/js/alpine.js` (placeholder, use CDN in prod)
- `static/img/` (SVG illustrations – provide simple placeholders: hands.svg, ripple.svg, house.svg, bridge.svg, lock.svg, seedling.svg, network.svg, gear.svg)
### 6. Scripts (executable)
- `scripts/harden.sh` (VPS hardening: unattended‑upgrades, ufw, fail2ban, ssh hardening, logwatch)
- `scripts/backup.sh` (pg_dump to compressed file, optionally upload to Backblaze B2)
- `scripts/restore.sh` (restore from backup, stops app, runs migrations)
- `scripts/deploy.sh` (backup, pull new image, restart, health check, rollback on failure)
### 7. CI/CD
- `.github/workflows/ci.yml` (lint, security scan, tests, coverage, Docker test build)
- `.github/workflows/deploy.yml` (build, push to GHCR, deploy via SSH)
### 8. Documentation
- `docs/deployment-checklist.md` (pre‑deployment, deployment, post‑deployment, rollback, maintenance)
- `docs/scaling.md` (connection pooling, worker scaling, horizontal scaling, S3 for media)
## CONSTRAINTS
- All code must be production‑ready (error handling, logging, security).
- Use Django’s built‑in auth (session‑based, not JWT).
- HTMX for all dynamic updates; Alpine.js only for client‑side state (mobile menu, confirmation dialogs).
- All templates must work without JavaScript (progressive enhancement).
- Tailwind CSS must be compiled via the CLI (include instructions in `README.md`).
- The project must pass `manage.py check --deploy` after configuration.
- The Docker setup must be minimal and self‑hostable by a technical volunteer.
## OUTPUT FORMAT
Produce a single response containing a list of files, each preceded by `### FILE: path/to/file` and the file content in a code block. Use relative paths from the project root (e.g., `config/settings/base.py`). For executable scripts, include the shebang and make them executable via `chmod +x` in the README.
## SUCCESS CRITERIA
- A developer can clone the generated project, set environment variables, run `docker-compose up -d db redis`, then `python manage.py migrate && python manage.py runserver`, and see the app at `http://localhost:8000`.
- The app implements the Core conformance level of UMI Protocol v0.1: needs, offers, matches, notifications, dashboard, audit log.
- All refinements are present: QR code generation, households, VPS hardening script, optional 2FA (via django‑two‑factor‑auth), neighbourhood privacy warnings.
- The production hardening layer (health check, Sentry, security headers, CI/CD, backup scripts) is included and documented.
# TASK
Generate a complete, production‑ready Django project for the UMI Protocol v0.1 reference implementation at Core conformance level, including all optional refinements (QR join, households, VPS hardening script, optional 2FA, metadata privacy mitigations). The output must be a self‑contained project that can be deployed locally or on a server using Docker. Provide every file as a code block with its path from the project root.
## MENTAL MODEL
You are a senior full‑stack developer who has built many Django applications that scale from a single parish to a diocese. You write clean, secure, accessible code using the “boring technology” stack: Django, PostgreSQL, Redis, HTMX, Alpine.js, Tailwind CSS, Docker. You follow Django best practices: custom user model, environment‑based settings, class‑based views, and HTMX for dynamic interactions. You include comprehensive docstrings, comments, and error handling. You never compromise on privacy or accessibility.
## SOURCE MATERIAL
- The UMI Protocol v0.1 specification (entities: Need, Offer, Match, Consent, Referral, Attestation; state machines; security rules).
- The high‑fidelity visual specification (for UI hints – focus on functionality, not exact pixel perfection).
- The Core Exchange implementation plan (10‑week schedule, but we need the code now).
- The refinements: QR join, households, VPS hardening script, optional 2FA, metadata privacy (neighbourhood warnings, tooltips, community‑level config).
- The production hardening layer: health check, Sentry integration, security headers, structured logging, CI/CD pipelines (as `.github/workflows`), multi‑stage Dockerfile, production Docker Compose, backup/restore scripts, staging settings, scaling docs.
## DELIVERABLES
Generate the entire project as a set of files with paths and content. Include at minimum:
### 1. Configuration and Root Files
- `manage.py`
- `.env.example` (all environment variables: SECRET_KEY, DATABASE_URL, REDIS_URL, SENTRY_DSN, ENCRYPTION_KEY, etc.)
- `requirements.txt` (all dependencies: Django, DRF, psycopg, django‑redis, django‑htmx, django‑allauth, django‑guardian, django‑ratelimit, cryptography, django‑two‑factor‑auth, qrcode, sentry‑sdk, etc.)
- `pyproject.toml` (ruff configuration)
- `tailwind.config.js` (Tailwind setup)
- `docker-compose.yml` (development: PostgreSQL, Redis, app)
- `docker-compose.prod.yml` (production: app, db, redis, caddy, uptime‑kuma)
- `Dockerfile` (multi‑stage, non‑root user, healthcheck)
- `Caddyfile` (production reverse proxy with security headers)
- `LICENSE` (AGPL‑3.0)
- `README.md` (setup instructions, environment variables, deployment overview)
### 2. Django Project Configuration
- `config/settings/base.py`, `development.py`, `production.py`, `staging.py`
- `config/urls.py`, `wsgi.py`, `asgi.py`
### 3. Apps (complete with models, views, forms, templates, URLs)
- **accounts**: Custom User model (email optional, username login), registration/login (rate‑limited), profile settings (2FA toggle, household management).
- **households**: Household model, create/join views, registration integration.
- **communities**: Community, Member, Category models; join‑via‑code; community settings (QR code generation, neighbourhood mode).
- **needs**: Need model (with `on_behalf_of` encryption), create/detail views, soft validation for neighbourhood privacy.
- **offers**: Offer model (availability JSON, radius), create/detail views.
- **matches**: Match model with state machine, proposal/accept/fulfill/cancel views, contact revelation logic, race condition handling (SELECT FOR UPDATE).
- **notifications**: Notification model, adapter (in‑app and email), header badge.
- **dashboard**: Coordinator dashboard (metrics, stale needs, category chart, export CSV).
- **audit**: AuditLog model, middleware, management command to set DB permissions (INSERT only).
- **health**: Health check endpoint (db, cache).
- **consent**: Consent model (stub for Core, full UI for Extended).
### 4. Templates
- `base.html` (HTMX/Alpine includes, CSS variables, protocol badge, toast container)
- Components: `_need_card.html`, `_offer_card.html`, `_category_grid.html`, `_urgency_selector.html`, `_match_timeline.html`, `_contact_info_box.html`, `_metric_card.html`, `_filter_bar.html`, `_notification_badge.html`, `_primary_button.html`, `_protocol_badge.html`, `_trust_badge.html`, `_empty_state.html`
- Page templates: `landing.html`, `login.html`, `register.html`, `join.html`, `feed.html`, `need_create.html`, `need_detail.html`, `offer_create.html`, `offer_detail.html`, `match_detail.html`, `dashboard.html`, `settings.html`, `household_create.html`, `household_join.html`, `technology.html`
### 5. Static Assets
- `static/css/input.css` (Tailwind directives)
- `static/js/alpine.js` (placeholder, use CDN in prod)
- `static/img/` (SVG illustrations – provide simple placeholders: hands.svg, ripple.svg, house.svg, bridge.svg, lock.svg, seedling.svg, network.svg, gear.svg)
### 6. Scripts (executable)
- `scripts/harden.sh` (VPS hardening: unattended‑upgrades, ufw, fail2ban, ssh hardening, logwatch)
- `scripts/backup.sh` (pg_dump to compressed file, optionally upload to Backblaze B2)
- `scripts/restore.sh` (restore from backup, stops app, runs migrations)
- `scripts/deploy.sh` (backup, pull new image, restart, health check, rollback on failure)
### 7. CI/CD
- `.github/workflows/ci.yml` (lint, security scan, tests, coverage, Docker test build)
- `.github/workflows/deploy.yml` (build, push to GHCR, deploy via SSH)
### 8. Documentation
- `docs/deployment-checklist.md` (pre‑deployment, deployment, post‑deployment, rollback, maintenance)
- `docs/scaling.md` (connection pooling, worker scaling, horizontal scaling, S3 for media)
## CONSTRAINTS
- All code must be production‑ready (error handling, logging, security).
- Use Django’s built‑in auth (session‑based, not JWT).
- HTMX for all dynamic updates; Alpine.js only for client‑side state (mobile menu, confirmation dialogs).
- All templates must work without JavaScript (progressive enhancement).
- Tailwind CSS must be compiled via the CLI (include instructions in `README.md`).
- The project must pass `manage.py check --deploy` after configuration.
- The Docker setup must be minimal and self‑hostable by a technical volunteer.
## OUTPUT FORMAT
Produce a single response containing a list of files, each preceded by `### FILE: path/to/file` and the file content in a code block. Use relative paths from the project root (e.g., `config/settings/base.py`). For executable scripts, include the shebang and make them executable via `chmod +x` in the README.
## SUCCESS CRITERIA
- A developer can clone the generated project, set environment variables, run `docker-compose up -d db redis`, then `python manage.py migrate && python manage.py runserver`, and see the app at `http://localhost:8000`.
- The app implements the Core conformance level of UMI Protocol v0.1: needs, offers, matches, notifications, dashboard, audit log.
- All refinements are present: QR code generation, households, VPS hardening script, optional 2FA (via django‑two‑factor‑auth), neighbourhood privacy warnings.
- The production hardening layer (health check, Sentry, security headers, CI/CD, backup scripts) is included and documented.
Generate a complete, production‑ready Django project for the UMI Protocol v0.1 reference implementation at Core conformance level, including all optional refinements (QR join, households, VPS hardening script, optional 2FA, metadata privacy mitigations). The output must be a self‑contained project that can be deployed locally or on a server using Docker. Provide every file as a code block with its path from the project root.
claude -prompt-file project-prompt.txt
# TASK
Generate a complete, production‑ready Django project for the UMI Protocol v0.1 reference implementation at Core conformance level, including all optional refinements (QR join, households, VPS hardening script, optional 2FA, metadata privacy mitigations). The output must be a self‑contained project that can be deployed locally or on a server using Docker. Provide every file as a code block with its path from the project root.
## MENTAL MODEL
You are a senior full‑stack developer who has built many Django applications that scale from a single parish to a diocese. You write clean, secure, accessible code using the “boring technology” stack: Django, PostgreSQL, Redis, HTMX, Alpine.js, Tailwind CSS, Docker. You follow Django best practices: custom user model, environment‑based settings, class‑based views, and HTMX for dynamic interactions. You include comprehensive docstrings, comments, and error handling. You never compromise on privacy or accessibility.
## SOURCE MATERIAL
- The UMI Protocol v0.1 specification (entities: Need, Offer, Match, Consent, Referral, Attestation; state machines; security rules).
- The high‑fidelity visual specification (for UI hints – focus on functionality, not exact pixel perfection).
- The Core Exchange implementation plan (10‑week schedule, but we need the code now).
- The refinements: QR join, households, VPS hardening script, optional 2FA, metadata privacy (neighbourhood warnings, tooltips, community‑level config).
- The production hardening layer: health check, Sentry integration, security headers, structured logging, CI/CD pipelines (as `.github/workflows`), multi‑stage Dockerfile, production Docker Compose, backup/restore scripts, staging settings, scaling docs.
## DELIVERABLES
Generate the entire project as a set of files with paths and content. Include at minimum:
### 1. Configuration and Root Files
- `manage.py`
- `.env.example` (all environment variables: SECRET_KEY, DATABASE_URL, REDIS_URL, SENTRY_DSN, ENCRYPTION_KEY, etc.)
- `requirements.txt` (all dependencies: Django, DRF, psycopg, django‑redis, django‑htmx, django‑allauth, django‑guardian, django‑ratelimit, cryptography, django‑two‑factor‑auth, qrcode, sentry‑sdk, etc.)
- `pyproject.toml` (ruff configuration)
- `tailwind.config.js` (Tailwind setup)
- `docker-compose.yml` (development: PostgreSQL, Redis, app)
- `docker-compose.prod.yml` (production: app, db, redis, caddy, uptime‑kuma)
- `Dockerfile` (multi‑stage, non‑root user, healthcheck)
- `Caddyfile` (production reverse proxy with security headers)
- `LICENSE` (AGPL‑3.0)
- `README.md` (setup instructions, environment variables, deployment overview)
### 2. Django Project Configuration
- `config/settings/base.py`, `development.py`, `production.py`, `staging.py`
- `config/urls.py`, `wsgi.py`, `asgi.py`
### 3. Apps (complete with models, views, forms, templates, URLs)
- **accounts**: Custom User model (email optional, username login), registration/login (rate‑limited), profile settings (2FA toggle, household management).
- **households**: Household model, create/join views, registration integration.
- **communities**: Community, Member, Category models; join‑via‑code; community settings (QR code generation, neighbourhood mode).
- **needs**: Need model (with `on_behalf_of` encryption), create/detail views, soft validation for neighbourhood privacy.
- **offers**: Offer model (availability JSON, radius), create/detail views.
- **matches**: Match model with state machine, proposal/accept/fulfill/cancel views, contact revelation logic, race condition handling (SELECT FOR UPDATE).
- **notifications**: Notification model, adapter (in‑app and email), header badge.
- **dashboard**: Coordinator dashboard (metrics, stale needs, category chart, export CSV).
- **audit**: AuditLog model, middleware, management command to set DB permissions (INSERT only).
- **health**: Health check endpoint (db, cache).
- **consent**: Consent model (stub for Core, full UI for Extended).
### 4. Templates
- `base.html` (HTMX/Alpine includes, CSS variables, protocol badge, toast container)
- Components: `_need_card.html`, `_offer_card.html`, `_category_grid.html`, `_urgency_selector.html`, `_match_timeline.html`, `_contact_info_box.html`, `_metric_card.html`, `_filter_bar.html`, `_notification_badge.html`, `_primary_button.html`, `_protocol_badge.html`, `_trust_badge.html`, `_empty_state.html`
- Page templates: `landing.html`, `login.html`, `register.html`, `join.html`, `feed.html`, `need_create.html`, `need_detail.html`, `offer_create.html`, `offer_detail.html`, `match_detail.html`, `dashboard.html`, `settings.html`, `household_create.html`, `household_join.html`, `technology.html`
### 5. Static Assets
- `static/css/input.css` (Tailwind directives)
- `static/js/alpine.js` (placeholder, use CDN in prod)
- `static/img/` (SVG illustrations – provide simple placeholders: hands.svg, ripple.svg, house.svg, bridge.svg, lock.svg, seedling.svg, network.svg, gear.svg)
### 6. Scripts (executable)
- `scripts/harden.sh` (VPS hardening: unattended‑upgrades, ufw, fail2ban, ssh hardening, logwatch)
- `scripts/backup.sh` (pg_dump to compressed file, optionally upload to Backblaze B2)
- `scripts/restore.sh` (restore from backup, stops app, runs migrations)
- `scripts/deploy.sh` (backup, pull new image, restart, health check, rollback on failure)
### 7. CI/CD
- `.github/workflows/ci.yml` (lint, security scan, tests, coverage, Docker test build)
- `.github/workflows/deploy.yml` (build, push to GHCR, deploy via SSH)
### 8. Documentation
- `docs/deployment-checklist.md` (pre‑deployment, deployment, post‑deployment, rollback, maintenance)
- `docs/scaling.md` (connection pooling, worker scaling, horizontal scaling, S3 for media)
## CONSTRAINTS
- All code must be production‑ready (error handling, logging, security).
- Use Django’s built‑in auth (session‑based, not JWT).
- HTMX for all dynamic updates; Alpine.js only for client‑side state (mobile menu, confirmation dialogs).
- All templates must work without JavaScript (progressive enhancement).
- Tailwind CSS must be compiled via the CLI (include instructions in `README.md`).
- The project must pass `manage.py check --deploy` after configuration.
- The Docker setup must be minimal and self‑hostable by a technical volunteer.
## OUTPUT FORMAT
Produce a single response containing a list of files, each preceded by `### FILE: path/to/file` and the file content in a code block. Use relative paths from the project root (e.g., `config/settings/base.py`). For executable scripts, include the shebang and make them executable via `chmod +x` in the README.
## SUCCESS CRITERIA
- A developer can clone the generated project, set environment variables, run `docker-compose up -d db redis`, then `python manage.py migrate && python manage.py runserver`, and see the app at `http://localhost:8000`.
- The app implements the Core conformance level of UMI Protocol v0.1: needs, offers, matches, notifications, dashboard, audit log.
- All refinements are present: QR code generation, households, VPS hardening script, optional 2FA (via django‑two‑factor‑auth), neighbourhood privacy warnings.
- The production hardening layer (health check, Sentry, security headers, CI/CD, backup scripts) is included and documented.
mkdir -p ~/umi-exchange
cd ~/umi exchange
mkdir -p ~/umi-exchange cd ~/umi-exchange nano project-prompt.txt
# TASK
Generate a complete, production‑ready Django project for the UMI Protocol v0.1 reference implementation at Core conformance level, including all optional refinements (QR join, households, VPS hardening script, optional 2FA, metadata privacy mitigations). The output must be a self‑contained project that can be deployed locally or on a server using Docker. Provide every file as a code block with its path from the project root.
## MENTAL MODEL
You are a senior full‑stack developer who has built many Django applications that scale from a single parish to a diocese. You write clean, secure, accessible code using the “boring technology” stack: Django, PostgreSQL, Redis, HTMX, Alpine.js, Tailwind CSS, Docker. You follow Django best practices: custom user model, environment‑based settings, class‑based views, and HTMX for dynamic interactions. You include comprehensive docstrings, comments, and error handling. You never compromise on privacy or accessibility.
## SOURCE MATERIAL
- The UMI Protocol v0.1 specification (entities: Need, Offer, Match, Consent, Referral, Attestation; state machines; security rules).
- The high‑fidelity visual specification (for UI hints – focus on functionality, not exact pixel perfection).
- The Core Exchange implementation plan (10‑week schedule, but we need the code now).
- The refinements: QR join, households, VPS hardening script, optional 2FA, metadata privacy (neighbourhood warnings, tooltips, community‑level config).
- The production hardening layer: health check, Sentry integration, security headers, structured logging, CI/CD pipelines (as `.github/workflows`), multi‑stage Dockerfile, production Docker Compose, backup/restore scripts, staging settings, scaling docs.
## DELIVERABLES
Generate the entire project as a set of files with paths and content. Include at minimum:
### 1. Configuration and Root Files
- `manage.py`
- `.env.example` (all environment variables: SECRET_KEY, DATABASE_URL, REDIS_URL, SENTRY_DSN, ENCRYPTION_KEY, etc.)
- `requirements.txt` (all dependencies: Django, DRF, psycopg, django‑redis, django‑htmx, django‑allauth, django‑guardian, django‑ratelimit, cryptography, django‑two‑factor‑auth, qrcode, sentry‑sdk, etc.)
- `pyproject.toml` (ruff configuration)
- `tailwind.config.js` (Tailwind setup)
- `docker-compose.yml` (development: PostgreSQL, Redis, app)
- `docker-compose.prod.yml` (production: app, db, redis, caddy, uptime‑kuma)
- `Dockerfile` (multi‑stage, non‑root user, healthcheck)
- `Caddyfile` (production reverse proxy with security headers)
- `LICENSE` (AGPL‑3.0)
- `README.md` (setup instructions, environment variables, deployment overview)
### 2. Django Project Configuration
- `config/settings/base.py`, `development.py`, `production.py`, `staging.py`
- `config/urls.py`, `wsgi.py`, `asgi.py`
### 3. Apps (complete with models, views, forms, templates, URLs)
- **accounts**: Custom User model (email optional, username login), registration/login (rate‑limited), profile settings (2FA toggle, household management).
- **households**: Household model, create/join views, registration integration.
- **communities**: Community, Member, Category models; join‑via‑code; community settings (QR code generation, neighbourhood mode).
- **needs**: Need model (with `on_behalf_of` encryption), create/detail views, soft validation for neighbourhood privacy.
- **offers**: Offer model (availability JSON, radius), create/detail views.
- **matches**: Match model with state machine, proposal/accept/fulfill/cancel views, contact revelation logic, race condition handling (SELECT FOR UPDATE).
- **notifications**: Notification model, adapter (in‑app and email), header badge.
- **dashboard**: Coordinator dashboard (metrics, stale needs, category chart, export CSV).
- **audit**: AuditLog model, middleware, management command to set DB permissions (INSERT only).
- **health**: Health check endpoint (db, cache).
- **consent**: Consent model (stub for Core, full UI for Extended).
### 4. Templates
- `base.html` (HTMX/Alpine includes, CSS variables, protocol badge, toast container)
- Components: `_need_card.html`, `_offer_card.html`, `_category_grid.html`, `_urgency_selector.html`, `_match_timeline.html`, `_contact_info_box.html`, `_metric_card.html`, `_filter_bar.html`, `_notification_badge.html`, `_primary_button.html`, `_protocol_badge.html`, `_trust_badge.html`, `_empty_state.html`
- Page templates: `landing.html`, `login.html`, `register.html`, `join.html`, `feed.html`, `need_create.html`, `need_detail.html`, `offer_create.html`, `offer_detail.html`, `match_detail.html`, `dashboard.html`, `settings.html`, `household_create.html`, `household_join.html`, `technology.html`
### 5. Static Assets
- `static/css/input.css` (Tailwind directives)
- `static/js/alpine.js` (placeholder, use CDN in prod)
- `static/img/` (SVG illustrations – provide simple placeholders: hands.svg, ripple.svg, house.svg, bridge.svg, lock.svg, seedling.svg, network.svg, gear.svg)
### 6. Scripts (executable)
- `scripts/harden.sh` (VPS hardening: unattended‑upgrades, ufw, fail2ban, ssh hardening, logwatch)
- `scripts/backup.sh` (pg_dump to compressed file, optionally upload to Backblaze B2)
- `scripts/restore.sh` (restore from backup, stops app, runs migrations)
- `scripts/deploy.sh` (backup, pull new image, restart, health check, rollback on failure)
### 7. CI/CD
- `.github/workflows/ci.yml` (lint, security scan, tests, coverage, Docker test build)
- `.github/workflows/deploy.yml` (build, push to GHCR, deploy via SSH)
### 8. Documentation
- `docs/deployment-checklist.md` (pre‑deployment, deployment, post‑deployment, rollback, maintenance)
- `docs/scaling.md` (connection pooling, worker scaling, horizontal scaling, S3 for media)
## CONSTRAINTS
- All code must be production‑ready (error handling, logging, security).
- Use Django’s built‑in auth (session‑based, not JWT).
- HTMX for all dynamic updates; Alpine.js only for client‑side state (mobile menu, confirmation dialogs).
- All templates must work without JavaScript (progressive enhancement).
- Tailwind CSS must be compiled via the CLI (include instructions in `README.md`).
- The project must pass `manage.py check --deploy` after configuration.
- The Docker setup must be minimal and self‑hostable by a technical volunteer.
## OUTPUT FORMAT
Produce a single response containing a list of files, each preceded by `### FILE: path/to/file` and the file content in a code block. Use relative paths from the project root (e.g., `config/settings/base.py`). For executable scripts, include the shebang and make them executable via `chmod +x` in the README.
## SUCCESS CRITERIA
- A developer can clone the generated project, set environment variables, run `docker-compose up -d db redis`, then `python manage.py migrate && python manage.py runserver`, and see the app at `http://localhost:8000`.
- The app implements the Core conformance level of UMI Protocol v0.1: needs, offers, matches, notifications, dashboard, audit log.
- All refinements are present: QR code generation, households, VPS hardening script, optional 2FA (via django‑two‑factor‑auth), neighbourhood privacy warnings.
- The production hardening layer (health check, Sentry, security headers, CI/CD, backup scripts) is included and documented.
Generate a complete, production‑ready Django project for the UMI Protocol v0.1 reference implementation at Core conformance level, including all optional refinements (QR join, households, VPS hardening script, optional 2FA, metadata privacy mitigations). The output must be a self‑contained project that can be deployed locally or on a server using Docker. Provide every file as a code block with its path from the project root.
claude --prompt.file project-prompt.txt
claude --prompt-file project-prompt.txt
claude --help
claude --file project-prompt.txt
claude auth
claude "Write a hello world script"
ls ~/umi-exchange
cd /home/umi/umi-exchange
git init
git add .
git commit -m "baseline before completing production gaps"
git config --global user.email "jasiahcw9@gmail.com"
git config --global [200~UMI Exchange — Complete to Production-Ready
Background
The existing project at /home/umi/umi-exchange already has a substantial foundation with ~80% of the required files. After a thorough audit of every file, I've identified specific gaps that need to be filled to reach the production-ready state described in the requirements.

What Already Exists (✅ Complete)
ComponentStatus
manage.py, .env.example, requirements.txt ✅ Solid
pyproject.toml, tailwind.config.js ✅ Solid
config/settings/base.py, development.py, production.py, staging.py✅ Complete
config/urls.py, wsgi.py, asgi.py✅ Complete
accounts app (User model, registration, login, settings, forms)✅ Complete
communities app (Community, Member, Category, views, QR code, feed)✅ Complete
needs app (Need model with encryption, forms, views, tasks)✅ Complete
offers app (Offer model, forms, views)✅ Complete
matches app (Match model with state machine, views, race condition handling)✅ Complete
notifications app (Notification model, adapter, views, template tags)✅ Complete
dashboard app (Coordinator dashboard with metrics)✅ Complete
audit app (AuditLog model, management command)✅ Complete
health app (Health check endpoint)✅ Complete
consent app (Consent model stub)✅ Complete
households app (Household model, forms, views, URLs)✅ Complete
Docker files (docker/Dockerfile, docker/docker-compose.prod.yml, docker/Caddyfile.prod)✅ Complete
Scripts (harden.sh, backup.sh, restore.sh, deploy.sh)✅ Complete
CI/CD (.github/workflows/ci.yml, deploy.yml)✅ Complete
Docs (deployment-checklist.md, scaling.md)✅ Complete
Tests (conftest.py, test_matches.py)✅ Complete
Templates (base, landing, feed, login, register, settings, needs, offers, matches, dashboard, households, notifications, components)✅ Most exist
Gaps to Fill
1. Missing Template Components (Spec'd but not present)
templates/components/_category_grid.html — Category selection grid for need/offer creation
templates/components/_urgency_selector.html — Visual urgency picker
templates/components/_metric_card.html — Reusable metric card for dashboard
templates/components/_filter_bar.html — Reusable filter bar component
templates/components/_primary_button.html — Consistent button component
templates/components/_protocol_badge.html — UMI Protocol conformance badge
templates/components/_trust_badge.html — Trust/verification indicator
2. Missing SVG Placeholder Images
static/img/hands.svg — Community/helping hands
static/img/ripple.svg — Impact ripple effect
static/img/house.svg — Household icon
static/img/bridge.svg — Connection/bridging
static/img/lock.svg — Privacy/security
static/img/seedling.svg — Growth/new beginning
static/img/network.svg — Network/interconnection
static/img/gear.svg — Settings/configuration
3. Root Dockerfile is minimal
The root Dockerfile (15 lines) is a simple single-stage build. The multi-stage one is in docker/Dockerfile. The root one needs upgrading to match the spec (or we defer to docker/Dockerfile).
4. Root docker-compose.yml has some issues
References ${POSTGRES_DB}, ${POSTGRES_USER}, ${POSTGRES_PASSWORD} but .env.example has DATABASE_URL format instead
Missing port mapping for the app (for local dev without Caddy)
The Caddyfile reference points to ./Caddyfile (root) but the dev Caddyfile is at docker/Caddyfile
5. 2FA Integration (Optional but requested)
Requirements specify 2FA should be un-commented/enabled. Currently it's commented out in requirements.txt and not wired in settings or views. Need to:

Uncomment 2FA in requirements
Add conditional 2FA settings in base.py
Add 2FA setup view in accounts app
6. Dashboard CSV Export
The dashboard spec mentions "export CSV" but no export view exists.

7. Needs app missing URLs file
The needs app has views but no urls.py — URLs are defined in communities/urls.py. This is intentional (needs are scoped under /c/<slug>/needs/), but there's no apps/needs/urls.py file.
8. Missing apps/__init__.py
No apps/__init__.py file (may or may not be needed depending on how Django resolves the apps).
9. Audit Middleware
The spec mentions "audit middleware" but no middleware file exists in the audit app.
Proposed Changes
Component 1: Missing Template Components
[NEW] 
_category_grid.html
Grid of emoji-labelled category buttons for need/offer creation forms. Uses HTMX to set hidden category field.
[NEW] 
_urgency_selector.html
Visual urgency picker with color-coded buttons and accessibility labels.
[NEW] 
_metric_card.html
Reusable dashboard metric card with label, value, and optional trend indicator.
[NEW] 
_filter_bar.html
Extractable filter bar used in feed and dashboard.
[NEW] 
_primary_button.html
Consistent primary action button with href, label, and optional icon.
[NEW] 
_protocol_badge.html
UMI Protocol conformance badge shown in footer.
[NEW] 
_trust_badge.html
Trust/verification indicator for coordinators and verified members.
Component 2: SVG Placeholder Images
[NEW] Eight SVG files in static/img/
Simple, clean SVG illustrations: hands.svg, ripple.svg, house.svg, bridge.svg, lock.svg, seedling.svg, network.svg, gear.svg.
Component 3: Root Docker Files Fix
[MODIFY] 
Dockerfile
Replace minimal single-stage Dockerfile with proper multi-stage build matching docker/Dockerfile patterns.
[MODIFY] 
docker-compose.yml
Fix env var references, add port mapping for local dev, fix Caddyfile path.
Component 4: 2FA Integration
[MODIFY] 
requirements.txt
Uncomment django-otp and django-two-factor-auth.
[MODIFY] 
base.py
Add conditional 2FA app/middleware integration.
[MODIFY] 
urls_settings.py
Add 2FA setup URL.
[MODIFY] 
settings.html
Add 2FA toggle section.
Component 5: Dashboard CSV Export
[MODIFY] 
views.py
Add DashboardCSVExportView for coordinator data export.
[MODIFY] 
urls.py
Add CSV export URL.
Component 6: Audit Middleware
[NEW] 
middleware.py
Request logging middleware for state-changing operations.
[MODIFY] 
base.py
Add audit middleware to MIDDLEWARE list.
Component 7: Missing Init File
[NEW] 
init
.py
Empty init file for the apps package.
Verification Plan
Automated Tests
bash
# Verify Django can start and check for deployment readiness
python manage.py check --deploy
python manage.py makemigrations --check --dry-run
pytest tests/ -v
Manual Verification
Run docker compose -f docker-compose.yml up -d db redis to start services
Run python manage.py migrate && python manage.py runserver
Visit http://localhost:8000 — landing page renders
Register a user, create a community, post a need, post an offer, propose a match
Open Questions
IMPORTANT
Scope confirmation: The existing project is ~80% complete. The gaps are primarily missing template components, SVG assets, Docker config fixes, 2FA wiring, CSV export, and audit middleware. Should I proceed with filling all these gaps, or would you prefer to focus on a specific subset?
NOTE
