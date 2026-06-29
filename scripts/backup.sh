#!/bin/bash
# UMI Exchange — Database Backup Script
# Supports local storage and optional Backblaze B2 upload.
# Schedule via cron: 0 3 * * * /opt/umi-exchange/scripts/backup.sh
#
# SECURITY — keys are NEVER in the dump. pg_dump captures the DATABASE only;
#   ENCRYPTION_KEYS / SECRET_KEY live in the app's env, so a backup holds only
#   KEK-wrapped DEKs + ciphertext — opaque without the env key (this IS crypto-
#   shred). So: store backups on infrastructure that does NOT also hold the keys.
#   A backup + the keys together = full PII. (A defensive guard below refuses to
#   keep a dump that somehow contains a key value.)
#
# RETENTION & §5.8 ERASURE — crypto-shred deletes a record's DEK in the LIVE db.
#   A backup taken BEFORE the shred still contains that wrapped DEK + ciphertext,
#   and the KEK still exists in env — restoring it would resurrect the erased data.
#   §5.8 erasure is therefore only COMPLETE once every backup predating the shred
#   has aged out: locally after RETENTION_DAYS (below), and remotely via a B2
#   lifecycle rule on the bucket prefix (set the B2 rule's age == RETENTION_DAYS).
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

# Defensive: the dump must never contain the crypto keys (they're env, not db).
# If this host happens to expose them, fail loudly rather than ship a key-bearing
# backup that would defeat crypto-shred.
for _k in ENCRYPTION_KEY ENCRYPTION_KEYS SECRET_KEY; do
    _v="${!_k:-}"
    if [ -n "$_v" ] && zgrep -qaF -- "$_v" "$BACKUP_DIR/$FILENAME"; then
        echo "ERROR: $_k value found inside the dump — refusing to keep a key-bearing backup."
        rm -f "$BACKUP_DIR/$FILENAME"
        exit 1
    fi
done

# Optional: Upload to Backblaze B2 (S3-compatible). Use a SCOPED B2 application
# key — write access to THIS bucket/prefix only, never the master key.
if [ -n "${BACKUP_BUCKET:-}" ] && [ -n "${BACKUP_ACCESS_KEY:-}" ] && [ -n "${BACKUP_SECRET_KEY:-}" ]; then
    if ! command -v aws &> /dev/null; then
        echo "WARNING: aws CLI not installed; skipping remote upload (Install: pip install awscli)."
    else
        REMOTE_KEY="umi-backups/$FILENAME"
        ENDPOINT="${BACKUP_ENDPOINT:-https://s3.us-west-001.backblazeb2.com}"
        # Pass the scoped key explicitly (command-scoped env) so it never leaks wider.
        if AWS_ACCESS_KEY_ID="$BACKUP_ACCESS_KEY" AWS_SECRET_ACCESS_KEY="$BACKUP_SECRET_KEY" \
            aws s3 cp "$BACKUP_DIR/$FILENAME" "s3://$BACKUP_BUCKET/$REMOTE_KEY" \
            --endpoint-url "$ENDPOINT" --sse AES256 --only-show-errors; then
            # Verify the object is really there before trusting the backup.
            if AWS_ACCESS_KEY_ID="$BACKUP_ACCESS_KEY" AWS_SECRET_ACCESS_KEY="$BACKUP_SECRET_KEY" \
                aws s3api head-object --bucket "$BACKUP_BUCKET" --key "$REMOTE_KEY" \
                --endpoint-url "$ENDPOINT" > /dev/null 2>&1; then
                echo "[$(date)] Remote upload verified: s3://$BACKUP_BUCKET/$REMOTE_KEY (SSE-B2)"
            else
                echo "ERROR: B2 upload could not be verified (head-object failed)."
                exit 1
            fi
        else
            echo "ERROR: B2 upload failed."
            exit 1
        fi
    fi
elif [ -n "${BACKUP_BUCKET:-}" ]; then
    echo "WARNING: BACKUP_BUCKET set but BACKUP_ACCESS_KEY/BACKUP_SECRET_KEY missing; skipping remote upload."
fi

# Rotate old backups
DELETED=$(find "$BACKUP_DIR" -name "umi-*.sql.gz" -mtime +"$RETENTION_DAYS" -delete -print | wc -l)
echo "[$(date)] Cleaned $DELETED backups older than $RETENTION_DAYS days."
echo "[$(date)] Backup complete."
