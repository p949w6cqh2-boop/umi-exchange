#!/bin/bash
# UMI Exchange — health / TLS-cert-expiry / disk monitor + alerts.
#
# EXTENDS the existing monitoring (Uptime Kuma + Docker healthchecks); it does
# NOT stand up a second stack. Kuma covers HTTP health + cert-expiry for the
# public URL; this script covers what Kuma can't see from inside a container —
# the HOST's disk — and gives a self-hosted cert/health check for alerting paths
# that don't go through Kuma. Run it from cron on the host:
#     */5 * * * * /opt/umi-exchange/scripts/monitor.sh
#
# Alerts POST to $ALERT_WEBHOOK_URL (Slack/Discord-style, or a Kuma push URL).
# If unset, they print to stderr so cron emails them. Configure thresholds via env.
#
# NOTE: no `set -e` — one failing check must not abort the others.
set -uo pipefail

HEALTH_URL="${HEALTH_URL:-http://localhost:8000/health/}"
CERT_HOST="${CERT_HOST:-}"            # host:443 for TLS expiry, e.g. exchange.example.org:443
CERT_MIN_DAYS="${CERT_MIN_DAYS:-14}"
DISK_PATH="${DISK_PATH:-/}"
DISK_MAX_PCT="${DISK_MAX_PCT:-85}"
ALERT_WEBHOOK_URL="${ALERT_WEBHOOK_URL:-}"

alert() {
    local msg="[UMI monitor] $1"
    echo "$msg" >&2
    if [ -n "$ALERT_WEBHOOK_URL" ]; then
        # Minimal JSON; works for Slack/Discord/Kuma push. Never fail the run on a flaky webhook.
        curl -fsS -m 10 -X POST -H 'Content-Type: application/json' \
            --data "$(printf '{"text":"%s"}' "$msg")" "$ALERT_WEBHOOK_URL" >/dev/null 2>&1 || true
    fi
}

problems=0

# 1) Application health endpoint (2xx expected).
if ! curl -fsS -m 10 -o /dev/null "$HEALTH_URL"; then
    alert "HEALTH DOWN: $HEALTH_URL is not returning 2xx"
    problems=$((problems + 1))
fi

# 2) TLS certificate expiry (Caddy auto-TLS — warn before it lapses).
if [ -n "$CERT_HOST" ] && command -v openssl > /dev/null 2>&1; then
    end_date=$(echo | openssl s_client -servername "${CERT_HOST%%:*}" -connect "$CERT_HOST" 2> /dev/null \
        | openssl x509 -noout -enddate 2> /dev/null | cut -d= -f2)
    if [ -n "$end_date" ]; then
        days_left=$(( ($(date -d "$end_date" +%s) - $(date +%s)) / 86400 ))
        if [ "$days_left" -lt "$CERT_MIN_DAYS" ]; then
            alert "CERT EXPIRING: $CERT_HOST in ${days_left}d (threshold ${CERT_MIN_DAYS}d)"
            problems=$((problems + 1))
        fi
    else
        alert "CERT CHECK FAILED: could not read certificate for $CERT_HOST"
        problems=$((problems + 1))
    fi
fi

# 3) Host disk usage.
used_pct=$(df --output=pcent "$DISK_PATH" 2> /dev/null | tail -1 | tr -dc '0-9')
if [ -n "$used_pct" ] && [ "$used_pct" -ge "$DISK_MAX_PCT" ]; then
    alert "DISK HIGH: $DISK_PATH at ${used_pct}% (threshold ${DISK_MAX_PCT}%)"
    problems=$((problems + 1))
fi

if [ "$problems" -eq 0 ]; then
    echo "[$(date)] monitor OK — health, cert, disk all within thresholds."
fi
# Exit 0 always: cron alerting is via the webhook/stderr, not the exit code.
exit 0
