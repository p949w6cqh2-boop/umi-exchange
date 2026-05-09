#!/bin/bash
# UMI Exchange — Server-Side Deploy Script
# Called by CI/CD or manually: bash scripts/deploy.sh
set -euo pipefail

cd /opt/umi-exchange

echo "[$(date)] Starting deployment..."

# Pull latest image
docker compose -f docker/docker-compose.prod.yml pull app

# Run database backup before deploy
bash scripts/backup.sh

# Restart with new image
docker compose -f docker/docker-compose.prod.yml up -d app

# Run migrations
docker compose -f docker/docker-compose.prod.yml exec -T app python manage.py migrate --noinput

# Collect static files
docker compose -f docker/docker-compose.prod.yml exec -T app python manage.py collectstatic --noinput

# Health check
sleep 5
if curl -sf http://localhost:8000/health/ > /dev/null; then
    echo "[$(date)] Health check PASSED."
else
    echo "[$(date)] Health check FAILED! Rolling back..."
    docker compose -f docker/docker-compose.prod.yml rollback app 2>/dev/null || true
    exit 1
fi

echo "[$(date)] Deployment complete."
