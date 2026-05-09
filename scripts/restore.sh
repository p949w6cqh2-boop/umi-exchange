#!/bin/bash
# UMI Exchange — Database Restore Script
# Usage: bash scripts/restore.sh /var/backups/umi/umi-20260325-030000.sql.gz
set -euo pipefail

BACKUP_FILE="${1:-}"
DB_CONTAINER="${DB_CONTAINER:-docker-db-1}"

if [ -z "$BACKUP_FILE" ]; then
    echo "Usage: $0 <backup-file.sql.gz>"
    echo ""
    echo "Available backups:"
    ls -lh /var/backups/umi/umi-*.sql.gz 2>/dev/null || echo "  No backups found in /var/backups/umi/"
    exit 1
fi

if [ ! -f "$BACKUP_FILE" ]; then
    echo "ERROR: File not found: $BACKUP_FILE"
    exit 1
fi

echo "=== UMI Database Restore ==="
echo "File: $BACKUP_FILE"
echo "Size: $(du -h "$BACKUP_FILE" | cut -f1)"
echo ""
echo "WARNING: This will REPLACE the current database."
read -p "Type 'RESTORE' to confirm: " CONFIRM

if [ "$CONFIRM" != "RESTORE" ]; then
    echo "Aborted."
    exit 0
fi

echo "[$(date)] Stopping application..."
docker compose stop app 2>/dev/null || true

echo "[$(date)] Restoring database..."
if command -v docker &> /dev/null && docker ps -q --filter "name=$DB_CONTAINER" | grep -q .; then
    gunzip -c "$BACKUP_FILE" | docker exec -i "$DB_CONTAINER" psql -U umi -d umi_exchange
else
    gunzip -c "$BACKUP_FILE" | psql "${DATABASE_URL:-postgres://umi:umi@localhost:5432/umi_exchange}"
fi

echo "[$(date)] Running migrations (in case schema changed)..."
docker compose exec -T app python manage.py migrate --noinput 2>/dev/null || python manage.py migrate --noinput

echo "[$(date)] Starting application..."
docker compose start app 2>/dev/null || true

echo "[$(date)] Restore complete."
echo "Verify: curl http://localhost:8000/health/"
