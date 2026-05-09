#!/bin/bash
# UMI Exchange — Database Backup Script
# Supports local storage and optional Backblaze B2 upload.
# Schedule via cron: 0 3 * * * /opt/umi-exchange/scripts/backup.sh
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/var/backups/umi}"
DB_CONTAINER="${DB_CONTAINER:-docker-db-1}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
FILENAME="umi-${TIMESTAMP}.sql.gz"

mkdir -p "$BACKUP_DIR"

echo "[$(date)] Starting backup..."

# Dump database (works both inside and outside Docker)
if command -v docker &> /dev/null && docker ps -q --filter "name=$DB_CONTAINER" | grep -q .; then
    docker exec "$DB_CONTAINER" pg_dump -U umi umi_exchange | gzip > "$BACKUP_DIR/$FILENAME"
elif command -v pg_dump &> /dev/null; then
    pg_dump "${DATABASE_URL:-umi_exchange}" | gzip > "$BACKUP_DIR/$FILENAME"
else
    echo "ERROR: Neither docker nor pg_dump available."
    exit 1
fi

SIZE=$(du -h "$BACKUP_DIR/$FILENAME" | cut -f1)
echo "[$(date)] Local backup: $BACKUP_DIR/$FILENAME ($SIZE)"

# Optional: Upload to Backblaze B2 (or any S3-compatible storage)
if [ -n "${BACKUP_BUCKET:-}" ] && [ -n "${BACKUP_ACCESS_KEY:-}" ]; then
    if ! command -v aws &> /dev/null; then
        echo "WARNING: aws CLI not installed; skipping remote upload."
        echo "Install: pip install awscli"
    else
        aws s3 cp "$BACKUP_DIR/$FILENAME" \
            "s3://$BACKUP_BUCKET/umi-backups/$FILENAME" \
            --endpoint-url "${BACKUP_ENDPOINT:-https://s3.us-west-001.backblazeb2.com}" \
            --quiet
        echo "[$(date)] Remote upload: s3://$BACKUP_BUCKET/umi-backups/$FILENAME"
    fi
fi

# Rotate old backups
DELETED=$(find "$BACKUP_DIR" -name "umi-*.sql.gz" -mtime +"$RETENTION_DAYS" -delete -print | wc -l)
echo "[$(date)] Cleaned $DELETED backups older than $RETENTION_DAYS days."
echo "[$(date)] Backup complete."
