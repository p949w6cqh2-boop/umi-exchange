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
# WHICH BACKUP (first match wins):
#   DR_BACKUP_FILE=/path/to/umi-….sql.gz   an explicit file — what you use after a
#                                          real incident, when "latest" is the one
#                                          you do NOT want
#   DR_BUCKET + DR_ACCESS_KEY + DR_SECRET_KEY (+ DR_ENDPOINT)   newest in B2; the
#                                          truest rehearsal, since it proves the
#                                          off-box copy is real
#   otherwise: newest local file in BACKUP_DIR (default /var/backups/umi) — weaker,
#                                          but a rehearsed local backup beats an
#                                          unrehearsed one
#
# OPTIONAL:
#   DR_EXPECT_SLUG=st-brigids   assert a known community survived the restore
#
# Usage (local, no B2 needed):
#   DR_CONFIRM=yes-restore-into-scratch DR_DATABASE_URL=postgres://umi:pw@localhost:5433/umi_scratch \
#   DR_EXPECT_SLUG=st-brigids bash scripts/dr_sim.sh
#
# Usage (from B2 — the real rehearsal):
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

# ---- Get a backup to restore ------------------------------------------------
# Three sources, in order. B2 is the truest rehearsal (it proves the off-box copy
# is real), but requiring it meant the rehearsal could not run at all without B2
# configured — so an untested backup stayed untested for want of a bucket.
if [ -n "${DR_BACKUP_FILE:-}" ]; then
    # 1. An explicit file. Restoring a NAMED backup is what you do after an
    #    incident, when "the latest" is precisely the one you do not want.
    [ -f "$DR_BACKUP_FILE" ] || fail "DR_BACKUP_FILE not found: $DR_BACKUP_FILE"
    LATEST="$(basename "$DR_BACKUP_FILE")"
    cp "$DR_BACKUP_FILE" "$WORK/$LATEST" || fail "could not read $DR_BACKUP_FILE"
    log "source: explicit file $DR_BACKUP_FILE"
elif [ -n "${DR_BUCKET:-}" ] && [ -n "${DR_ACCESS_KEY:-}" ] && [ -n "${DR_SECRET_KEY:-}" ]; then
    # 2. The off-box copy. This is the one that proves the backup would survive
    #    losing the machine.
    command -v aws > /dev/null 2>&1 || fail "aws CLI not found (pip install awscli)."
    ENDPOINT="${DR_ENDPOINT:-https://s3.us-west-001.backblazeb2.com}"
    export AWS_ACCESS_KEY_ID="$DR_ACCESS_KEY" AWS_SECRET_ACCESS_KEY="$DR_SECRET_KEY"
    log "finding latest backup in s3://$DR_BUCKET/umi-backups/ …"
    LATEST=$(aws s3 ls "s3://$DR_BUCKET/umi-backups/" --endpoint-url "$ENDPOINT" \
        | awk '{print $4}' | { grep -E '^umi-.*\.sql\.gz$' || true; } | sort | tail -1)
    [ -n "$LATEST" ] || fail "no backups found in the bucket."
    log "source: B2 s3://$DR_BUCKET/umi-backups/$LATEST"
    aws s3 cp "s3://$DR_BUCKET/umi-backups/$LATEST" "$WORK/$LATEST" --endpoint-url "$ENDPOINT" --only-show-errors \
        || fail "download failed."
else
    # 3. The newest local backup. Weaker — it proves the dump restores, not that
    #    the off-box copy exists — but a rehearsed local backup beats an
    #    unrehearsed one, and this is the path that works on a fresh droplet.
    BACKUP_DIR="${BACKUP_DIR:-/var/backups/umi}"
    LOCAL=$(ls -1t "$BACKUP_DIR"/umi-*.sql.gz 2> /dev/null | head -1 || true)
    [ -n "$LOCAL" ] || fail "no B2 creds and no local backups in $BACKUP_DIR — nothing to rehearse."
    LATEST="$(basename "$LOCAL")"
    cp "$LOCAL" "$WORK/$LATEST" || fail "could not read $LOCAL"
    log "source: local $LOCAL (NOTE: this does not prove the off-box B2 copy works)"
fi

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

# A restored backup of a live instance that contains NO communities and NO members
# is not a successful restore, it is an empty database that answered every query
# without erroring. Counting only query failures let that pass as PASS — which is
# exactly the shape of a backup you find out about on the day you need it.
COMMUNITIES=$(psql "$DR_DATABASE_URL" -tAc "SELECT count(*) FROM communities_community;" 2> /dev/null || echo 0)
MEMBERS=$(psql "$DR_DATABASE_URL" -tAc "SELECT count(*) FROM communities_member;" 2> /dev/null || echo 0)
if [ "${COMMUNITIES:-0}" -lt 1 ] || [ "${MEMBERS:-0}" -lt 1 ]; then
    echo "    !! restored database has no communities or no members — an empty restore is a failed restore"
    ROWS_OK=0
fi

# Known-record check: the strongest cheap assertion. Counts prove the tables are
# not empty; this proves the specific thing you expected to survive did.
if [ -n "${DR_EXPECT_SLUG:-}" ]; then
    FOUND=$(psql "$DR_DATABASE_URL" -tAc \
        "SELECT count(*) FROM communities_community WHERE slug = '${DR_EXPECT_SLUG//\'/\'\'}';" 2> /dev/null || echo 0)
    if [ "${FOUND:-0}" -ge 1 ]; then
        echo "    known record: community '$DR_EXPECT_SLUG' present ✓"
    else
        echo "    !! known record: community '$DR_EXPECT_SLUG' MISSING from the restore"
        ROWS_OK=0
    fi
else
    echo "    known record: not checked (set DR_EXPECT_SLUG=<a community slug> to assert one)"
fi
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
