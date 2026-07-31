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
# DOCKER MODE (this is what the droplet needs):
#   The default path is HOST mode: host psql, host python3, a reachable db port. The droplet has
#   none of those — the stack is dockerized and the db container publishes no ports — so the
#   2026-07-29 rehearsal had to run this script's documented steps through the containers by hand.
#   Set DR_DOCKER=1 and the script routes psql and manage.py through `docker compose exec` itself.
#     DR_DOCKER=1
#     DR_COMPOSE_FILE=docker/docker-compose.prod.yml   (default)
#     DR_ENV_FILE=.env                                 (default; the canonical call carries it)
#     DR_DB_SERVICE=db  ·  DR_APP_SERVICE=app          (defaults)
#   In docker mode DR_DATABASE_URL is resolved INSIDE the db container, so its host is normally
#   localhost. That is a sharper knife than host mode: inside that container `localhost` IS the
#   production postgres server, and the DATABASE NAME is the only thing separating scratch from
#   prod. So docker mode adds a guard host mode does not need — it refuses when the target dbname
#   matches the app's, and warns when the name does not look like a scratch database.
#
#   Give the URL as the DB CONTAINER sees it (host localhost). The script rewrites the host to
#   the db service name for the app container by itself — one URL cannot serve both, and getting
#   that wrong is what made the first real rehearsal fail.
#   PW is DB_PASSWORD from .env, NOT POSTGRES_PASSWORD. On this droplet POSTGRES_PASSWORD is a
#   short unused leftover and compose feeds the db service `POSTGRES_PASSWORD: ${DB_PASSWORD}`.
#   Using the wrong one still restores (psql inside the container authenticates locally) and then
#   fails the schema gate, which reads like a broken backup and is not one.
#
# Usage (docker, on the droplet):
#   cd /opt/umi-exchange && DR_DOCKER=1 DR_CONFIRM=yes-restore-into-scratch \
#   DR_DATABASE_URL="postgres://umi:$(grep '^DB_PASSWORD=' .env | cut -d= -f2-)@localhost:5432/umi_scratch" \
#   DR_EXPECT_SLUG=st-brigids bash scripts/dr_sim.sh
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
# ---- Mode: host (default) or docker ----------------------------------------
# Everything below this block calls run_psql / run_manage, never psql / python3 directly, so the
# verification logic is identical in both modes and cannot drift apart.
DR_DOCKER="${DR_DOCKER:-0}"
# dbname = the path segment of a postgres URL, minus any query string.
dbname_of() { printf '%s' "${1##*/}" | cut -d'?' -f1; }

if [ "$DR_DOCKER" = "1" ]; then
    command -v docker > /dev/null 2>&1 || fail "DR_DOCKER=1 but docker not found."
    ENV_FILE="${DR_ENV_FILE:-.env}"

    # SAFETY BEFORE OPERATIONS. These guards run before the compose-file check on purpose: an
    # operator who has pointed this at prod must be told THAT, not that a yaml file is missing.
    # Docker-mode-only guard. Inside the db container `localhost` is the PROD server, so the
    # database NAME is the entire separation between scratch and prod. Host mode does not need
    # this because a wrong host there simply fails to connect; here it would connect and wipe.
    TARGET_DB="$(dbname_of "$DR_DATABASE_URL")"
    [ -n "$TARGET_DB" ] || fail "could not read a database name out of DR_DATABASE_URL."
    # NOTE, learned on the droplet 2026-07-30: this DATABASE_URL check can be INERT in production.
    # That .env carries `DATABASE_URL=sqlite:///db.sqlite3` (a dev leftover; compose overrides it
    # for the app service), so comparing against it protects nothing there. The POSTGRES_DB check
    # below is the one actually holding the line. Both are kept: neither is sufficient alone.
    APP_DB="$(dbname_of "${DATABASE_URL:-}")"
    if [ -n "$APP_DB" ] && [ "$TARGET_DB" = "$APP_DB" ]; then
        fail "target database '$TARGET_DB' is the app's own database — refusing."
    fi
    if [ -f "$ENV_FILE" ]; then
        ENV_DB="$(grep -E '^POSTGRES_DB=' "$ENV_FILE" 2> /dev/null | tail -1 | cut -d= -f2- | tr -d '"'"'"' ')"
        if [ -n "$ENV_DB" ] && [ "$TARGET_DB" = "$ENV_DB" ]; then
            fail "target database '$TARGET_DB' is POSTGRES_DB from $ENV_FILE — that is prod, refusing."
        fi
    fi
    case "$TARGET_DB" in
        *scratch*|*dr_*|*_test) : ;;
        *) log "WARNING: '$TARGET_DB' does not look like a scratch database. Continuing because
    DR_CONFIRM was given, but this script is about to DROP its public schema." ;;
    esac

    COMPOSE_FILE="${DR_COMPOSE_FILE:-docker/docker-compose.prod.yml}"
    [ -f "$COMPOSE_FILE" ] || fail "compose file not found: $COMPOSE_FILE (set DR_COMPOSE_FILE)."
    DB_SVC="${DR_DB_SERVICE:-db}"; APP_SVC="${DR_APP_SERVICE:-app}"
    COMPOSE=(docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE")

    # ONE URL CANNOT SERVE BOTH CONTAINERS. Found by the first real rehearsal, 2026-07-30.
    # psql runs inside the db container, where the server is `localhost`. manage.py runs inside
    # the APP container, where `localhost` is the app itself and postgres is the compose service
    # name. Sending the operator's URL unchanged to both made every docker-mode run fail its
    # schema gate with "Connection refused", which the gate then reported as pending migrations.
    # So: keep the host the operator gave for psql, and swap it to $DB_SVC for the app.
    # Split on the LAST '@' so a password containing '@' survives.
    _url_before_host="${DR_DATABASE_URL%@*}"        # postgres://user:pass
    _url_after_host="${DR_DATABASE_URL##*@}"        # host[:port]/dbname
    APP_DB_URL="${_url_before_host}@${DB_SVC}:5432/${_url_after_host#*/}"

    run_psql()   { "${COMPOSE[@]}" exec -T "$DB_SVC" psql "$@"; }
    run_manage() { "${COMPOSE[@]}" exec -T -e DATABASE_URL="$APP_DB_URL" "$APP_SVC" python manage.py "$@"; }
    schema_gate_available() { "${COMPOSE[@]}" exec -T "$APP_SVC" test -f manage.py > /dev/null 2>&1; }
    log "mode: docker ($COMPOSE_FILE, db=$DB_SVC app=$APP_SVC), target db '$TARGET_DB'."
    log "app-side db host rewritten to '$DB_SVC' (creds not echoed)."
else
    command -v psql > /dev/null 2>&1 || fail "psql not found (on a dockerized host set DR_DOCKER=1)."
    run_psql()   { psql "$@"; }
    run_manage() { DATABASE_URL="$DR_DATABASE_URL" python3 manage.py "$@"; }
    schema_gate_available() { [ -f manage.py ]; }
    log "mode: host."
fi
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
    command -v aws > /dev/null 2>&1 || fail "aws CLI not found (Ubuntu 24.04: sudo snap install aws-cli --classic)."
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
run_psql "$DR_DATABASE_URL" -v ON_ERROR_STOP=1 -q -c "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;" \
    || fail "could not reset scratch schema."
gunzip -c "$WORK/$LATEST" | run_psql "$DR_DATABASE_URL" -v ON_ERROR_STOP=1 -q \
    || fail "restore failed."

# ---- Verify: row counts + schema/health -------------------------------------
log "verifying restored data…"
ROWS_OK=1
for tbl in communities_community communities_member needs_need offers_offer audit_auditlog; do
    n=$(run_psql "$DR_DATABASE_URL" -tAc "SELECT count(*) FROM $tbl;" 2> /dev/null || echo "ERR")
    echo "    $tbl: $n"
    [ "$n" = "ERR" ] && ROWS_OK=0
done

# A restored backup of a live instance that contains NO communities and NO members
# is not a successful restore, it is an empty database that answered every query
# without erroring. Counting only query failures let that pass as PASS — which is
# exactly the shape of a backup you find out about on the day you need it.
COMMUNITIES=$(run_psql "$DR_DATABASE_URL" -tAc "SELECT count(*) FROM communities_community;" 2> /dev/null || echo 0)
MEMBERS=$(run_psql "$DR_DATABASE_URL" -tAc "SELECT count(*) FROM communities_member;" 2> /dev/null || echo 0)
if [ "${COMMUNITIES:-0}" -lt 1 ] || [ "${MEMBERS:-0}" -lt 1 ]; then
    echo "    !! restored database has no communities or no members — an empty restore is a failed restore"
    ROWS_OK=0
fi

# Known-record check: the strongest cheap assertion. Counts prove the tables are
# not empty; this proves the specific thing you expected to survive did.
if [ -n "${DR_EXPECT_SLUG:-}" ]; then
    FOUND=$(run_psql "$DR_DATABASE_URL" -tAc \
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
AUDIT=$(run_psql "$DR_DATABASE_URL" -tAc "SELECT count(*) FROM audit_auditlog;" 2> /dev/null || echo "ERR")

# Health: the restored schema must have no pending migrations (migrate --check).
if schema_gate_available; then
    MIGRATE_OUT="$(run_manage migrate --check 2>&1)" && MIGRATE_RC=0 || MIGRATE_RC=$?
    if [ "$MIGRATE_RC" = "0" ]; then
        HEALTH="ok (migrate --check: no pending migrations)"
    elif printf '%s' "$MIGRATE_OUT" | grep -qiE 'connection refused|connection failed|could not connect|could not translate host|OperationalError|authentication failed'; then
        # Name the failure correctly. Reporting "pending migrations" when the real problem is
        # that nothing could reach the database sends the operator to fix the wrong thing —
        # this exact misdiagnosis is what the first real rehearsal (2026-07-30) spent an hour on.
        HEALTH="FAIL (could NOT CONNECT to the restored db from '$APP_SVC' — NOT a migration problem)"
        echo "    connection error was: $(printf '%s' "$MIGRATE_OUT" | tail -1)"
        ROWS_OK=0
    else
        HEALTH="FAIL (migrate --check reports pending migrations)"
        echo "    migrate --check said: $(printf '%s' "$MIGRATE_OUT" | tail -1)"
        ROWS_OK=0
    fi
else
    # Never report PASS without running the schema gate.
    HEALTH="FAIL (manage.py not reachable — cannot verify schema health)"; ROWS_OK=0
fi
log "schema health: $HEALTH"

if [ "$ROWS_OK" = "1" ] && [ "$AUDIT" != "ERR" ]; then
    log "DR REHEARSAL PASSED — restored $LATEST into scratch, tables populated, schema healthy."
    exit 0
else
    fail "DR REHEARSAL FAILED — see counts/health above."
fi
