#!/bin/bash
# UMI Exchange — Disaster-Recovery rehearsal.
#
# Wipes a SCRATCH database, restores the latest Backblaze B2 backup into it, and
# verifies row counts + schema/health. It NEVER touches prod and reads ONLY the
# scratch DB url + a READ-scoped B2 key — never prod creds.
#
# HARD GUARD — refuses to run unless you explicitly point it at a non-prod target:
#   DR_CONFIRM=yes-restore-into-scratch   (required; proves intent)
#   DR_DATABASE_URL=postgres://…/umi_scratch   (required; the scratch DB. NO
#                                                fallback to the app's DATABASE_URL)
#   PROD_DB_HOST=<prod host>              (optional blocklist; abort if it matches)
#
# B2 (read-scoped key; can be the same scoped key as backup.sh if it has read):
#   DR_BUCKET, DR_ACCESS_KEY, DR_SECRET_KEY, DR_ENDPOINT (default Backblaze us-west)
#
# Usage:
#   DR_CONFIRM=yes-restore-into-scratch DR_DATABASE_URL=postgres://umi:pw@localhost:5433/umi_scratch \
#   DR_BUCKET=umi-backups DR_ACCESS_KEY=… DR_SECRET_KEY=… bash scripts/dr_sim.sh
set -euo pipefail

# Run from the repo root so manage.py (the schema-health gate) is always found,
# regardless of the caller's CWD.
cd "$(dirname "$0")/.." || exit 1

fail() { echo "DR-SIM ABORT: $1" >&2; exit 1; }
log()  { echo "[$(date +%H:%M:%S)] dr-sim: $1"; }

# ---- HARD GUARD: never prod -------------------------------------------------
[ "${DR_CONFIRM:-}" = "yes-restore-into-scratch" ] \
    || fail "set DR_CONFIRM=yes-restore-into-scratch to run (refusing by default)."
DR_DATABASE_URL="${DR_DATABASE_URL:-}"
[ -n "$DR_DATABASE_URL" ] || fail "DR_DATABASE_URL (a SCRATCH db) is required — there is no fallback to prod."
# Never let the scratch target be the live app DB.
if [ -n "${DATABASE_URL:-}" ] && [ "$DR_DATABASE_URL" = "${DATABASE_URL:-}" ]; then
    fail "DR_DATABASE_URL equals the app's DATABASE_URL — that is prod, refusing."
fi
if [ -n "${PROD_DB_HOST:-}" ] && printf '%s' "$DR_DATABASE_URL" | grep -qF "$PROD_DB_HOST"; then
    fail "DR_DATABASE_URL points at PROD_DB_HOST ($PROD_DB_HOST) — refusing."
fi
command -v psql > /dev/null 2>&1 || fail "psql not found."
log "scratch target accepted (creds not echoed)."

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# ---- Fetch the latest B2 backup (read-only) ---------------------------------
[ -n "${DR_BUCKET:-}" ] && [ -n "${DR_ACCESS_KEY:-}" ] && [ -n "${DR_SECRET_KEY:-}" ] \
    || fail "DR_BUCKET / DR_ACCESS_KEY / DR_SECRET_KEY are required to pull from B2."
command -v aws > /dev/null 2>&1 || fail "aws CLI not found (pip install awscli)."
ENDPOINT="${DR_ENDPOINT:-https://s3.us-west-001.backblazeb2.com}"
export AWS_ACCESS_KEY_ID="$DR_ACCESS_KEY" AWS_SECRET_ACCESS_KEY="$DR_SECRET_KEY"

log "finding latest backup in s3://$DR_BUCKET/umi-backups/ …"
LATEST=$(aws s3 ls "s3://$DR_BUCKET/umi-backups/" --endpoint-url "$ENDPOINT" \
    | awk '{print $4}' | { grep -E '^umi-.*\.sql\.gz$' || true; } | sort | tail -1)
[ -n "$LATEST" ] || fail "no backups found in the bucket."
log "latest: $LATEST"
aws s3 cp "s3://$DR_BUCKET/umi-backups/$LATEST" "$WORK/$LATEST" --endpoint-url "$ENDPOINT" --only-show-errors \
    || fail "download failed."

# ---- Wipe the scratch DB and restore ----------------------------------------
log "wiping scratch schema + restoring (this is the scratch DB only)…"
psql "$DR_DATABASE_URL" -v ON_ERROR_STOP=1 -q -c "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;" \
    || fail "could not reset scratch schema."
gunzip -c "$WORK/$LATEST" | psql "$DR_DATABASE_URL" -v ON_ERROR_STOP=1 -q \
    || fail "restore failed."

# ---- Verify: row counts + schema/health -------------------------------------
log "verifying restored data…"
ROWS_OK=1
for tbl in communities_community communities_member needs_need offers_offer audit_auditlog; do
    n=$(psql "$DR_DATABASE_URL" -tAc "SELECT count(*) FROM $tbl;" 2> /dev/null || echo "ERR")
    echo "    $tbl: $n"
    [ "$n" = "ERR" ] && ROWS_OK=0
done
# Append-only audit table must exist and be readable — it's the integrity canary.
AUDIT=$(psql "$DR_DATABASE_URL" -tAc "SELECT count(*) FROM audit_auditlog;" 2> /dev/null || echo "ERR")

# Health: the restored schema must have no pending migrations (migrate --check).
if [ -f manage.py ]; then
    if DATABASE_URL="$DR_DATABASE_URL" python3 manage.py migrate --check > /dev/null 2>&1; then
        HEALTH="ok (migrate --check: no pending migrations)"
    else
        HEALTH="FAIL (migrate --check reports pending migrations)"; ROWS_OK=0
    fi
else
    # Never report PASS without running the schema gate.
    HEALTH="FAIL (manage.py not found — cannot verify schema health)"; ROWS_OK=0
fi
log "schema health: $HEALTH"

if [ "$ROWS_OK" = "1" ] && [ "$AUDIT" != "ERR" ]; then
    log "DR REHEARSAL PASSED — restored $LATEST into scratch, tables populated, schema healthy."
    exit 0
else
    fail "DR REHEARSAL FAILED — see counts/health above."
fi
