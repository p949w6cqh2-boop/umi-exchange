#!/bin/bash
# UMI Exchange — Database Backup Script
# Supports local storage and optional Backblaze B2 upload.
# Schedule via cron: 0 3 * * * /opt/umi-exchange/scripts/backup.sh >> /var/log/umi-backup.log 2>&1
#
# REMOTE UPLOAD (Backblaze B2) — BACKUP_BUCKET / BACKUP_ACCESS_KEY / BACKUP_SECRET_KEY /
#   BACKUP_ENDPOINT are taken from the environment, falling back to the repo's .env
#   (cron runs this script with a bare environment, so the .env fallback is what makes
#   the nightly upload actually happen). The aws CLI on Ubuntu 24.04 is installed with
#   `sudo snap install aws-cli --classic` (there is no awscli apt package).
#   Set BACKUP_REQUIRE_REMOTE=1 in .env (recommended in production once B2 is
#   provisioned): any night the off-site copy cannot be made then exits nonzero
#   instead of quietly keeping a local-only backup.
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

# ── Configuration ──────────────────────────────────────────────────────────────
# Cron gives this script an almost-empty environment, so the B2 settings in .env
# never used to reach it — the upload was silently skipped. Fall back to the
# repo's .env for any BACKUP_* var the caller didn't provide. Do NOT `source`
# .env: it holds non-shell lines (e.g. DEFAULT_FROM_EMAIL=UMI Exchange <…>).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${ENV_FILE:-$SCRIPT_DIR/../.env}"

# Read one KEY=value from .env (last match wins). `|| true`: a missing key or
# file must yield an empty string — grep's exit 1 would trip set -e/pipefail.
env_file_val() {
    grep -E "^${1}=" "$ENV_FILE" 2>/dev/null | tail -n 1 | cut -d= -f2- || true
}

# ${VAR-…} (no colon): a var the caller set — even set-but-empty — wins; only a
# truly unset var falls back to .env (so `BACKUP_BUCKET= bash backup.sh` still
# means "local-only this run").
BACKUP_BUCKET="${BACKUP_BUCKET-$(env_file_val BACKUP_BUCKET)}"
BACKUP_ACCESS_KEY="${BACKUP_ACCESS_KEY-$(env_file_val BACKUP_ACCESS_KEY)}"
BACKUP_SECRET_KEY="${BACKUP_SECRET_KEY-$(env_file_val BACKUP_SECRET_KEY)}"
BACKUP_ENDPOINT="${BACKUP_ENDPOINT-$(env_file_val BACKUP_ENDPOINT)}"
BACKUP_REQUIRE_REMOTE="${BACKUP_REQUIRE_REMOTE-$(env_file_val BACKUP_REQUIRE_REMOTE)}"
RETENTION_DAYS="${RETENTION_DAYS-$(env_file_val RETENTION_DAYS)}"

BACKUP_DIR="${BACKUP_DIR:-/var/backups/umi}"
DB_CONTAINER="${DB_CONTAINER:-docker-db-1}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
FILENAME="umi-${TIMESTAMP}.sql.gz"

# ── Preflight: the B2 credential trio must be all-set or all-empty ─────────────
#   all empty → remote upload not configured (a fresh install); noticed below.
#   all set   → remote upload configured.
#   between   → a misconfiguration that can never upload anywhere. Fail fast and
#               loud, before the dump, rather than let the nightly cron look green.
B2_SET=0
for _k in BACKUP_BUCKET BACKUP_ACCESS_KEY BACKUP_SECRET_KEY; do
    if [ -n "${!_k:-}" ]; then B2_SET=$((B2_SET + 1)); fi
done
if [ "$B2_SET" -gt 0 ] && [ "$B2_SET" -lt 3 ]; then
    echo "ERROR: B2 credentials are PARTIALLY configured — BACKUP_BUCKET, BACKUP_ACCESS_KEY and BACKUP_SECRET_KEY must be all set or all empty (checked the environment, then $ENV_FILE). Remote upload can never work like this; fix .env."
    exit 1
fi
if [ "$B2_SET" -eq 0 ] && [ "${BACKUP_REQUIRE_REMOTE:-}" = "1" ]; then
    echo "ERROR: BACKUP_REQUIRE_REMOTE=1 but no B2 credentials are configured (BACKUP_BUCKET/BACKUP_ACCESS_KEY/BACKUP_SECRET_KEY empty in the environment and $ENV_FILE) — refusing to call a local-only backup a success."
    exit 1
fi

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
# Every way this leg can silently not happen must say so on stdout — a local-only
# backup that looks like a success is how prod ran 11 days without an off-site copy.
if [ "$B2_SET" -eq 3 ]; then
    if ! command -v aws &> /dev/null; then
        if [ "${BACKUP_REQUIRE_REMOTE:-}" = "1" ]; then
            echo "ERROR: B2 credentials are set but the aws CLI is not installed — remote upload impossible (Ubuntu 24.04: sudo snap install aws-cli --classic). BACKUP_REQUIRE_REMOTE=1, so this is fatal."
            exit 1
        fi
        echo "WARNING: aws CLI not installed; skipping remote upload — this backup exists on this machine ONLY (Ubuntu 24.04: sudo snap install aws-cli --classic)."
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
else
    # B2_SET is 0 here (partial config already failed in preflight; REQUIRE_REMOTE
    # with no creds too). A fresh install lands here — notice, not error.
    echo "NOTICE: remote (B2) upload NOT configured — this backup exists on this machine ONLY. Set BACKUP_BUCKET/BACKUP_ACCESS_KEY/BACKUP_SECRET_KEY in .env for off-site copies."
fi

# Rotate old backups
DELETED=$(find "$BACKUP_DIR" -name "umi-*.sql.gz" -mtime +"$RETENTION_DAYS" -delete -print | wc -l)
echo "[$(date)] Cleaned $DELETED backups older than $RETENTION_DAYS days."
echo "[$(date)] Backup complete."
