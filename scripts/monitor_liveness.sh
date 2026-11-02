#!/bin/bash
# UMI Exchange — liveness check for the UPTIME MONITOR ITSELF.
#
# `scripts/monitor.sh` watches the app. NOTHING watched the watcher, and that is
# the gap that cost the project its worst outage. Recorded in
# docs/ethics-and-safety.md box 1: the UptimeRobot monitor detected outages
# correctly for over two weeks while its E-mail notification channel was switched
# OFF. In the 30 days before anyone noticed: 84.416% uptime, 4 incidents,
# 4d 19h 56m down, and not one of them reached a human.
#
# Detection working with alerting disabled is worse than no monitoring: it
# produces confidence without coverage. So this asserts the WHOLE chain:
#   1. the API answers at all (a revoked key is a dead control);
#   2. the monitor exists and is not paused;
#   3. at least one alert contact is ATTACHED;
#   4. at least one attached contact is ENABLED;
#   5. at least one enabled contact is an INTERRUPTING channel, not e-mail alone.
#
# Run it from cron on the host, alongside monitor.sh:
#     17 * * * * /opt/umi-exchange/scripts/monitor_liveness.sh
#
# Alerts POST to $ALERT_WEBHOOK_URL (same shape as monitor.sh); without it they
# go to stderr so cron mails them. Exit code is NON-ZERO on any failure, because
# this script's whole purpose is to be loud.
set -uo pipefail

API_URL="${UPTIMEROBOT_API_URL:-https://api.uptimerobot.com/v2/getMonitors}"
API_KEY="${UPTIMEROBOT_API_KEY:-}"
# UptimeRobot alert-contact types that do NOT interrupt a human. 2 is E-mail —
# the channel that was off for the 30 days above. 5 is Web-Hook: a post into a
# room nobody is looking at has the same shape as an unread inbox.
# Override only with a reason; widening this list is how box 1 re-opens.
NON_INTERRUPTING_TYPES="${UMI_NON_INTERRUPTING_TYPES:-2 5}"
ALERT_WEBHOOK_URL="${ALERT_WEBHOOK_URL:-}"

alert() {
    local msg="[UMI monitor-liveness] $1"
    echo "$msg" >&2
    if [ -n "$ALERT_WEBHOOK_URL" ]; then
        local esc=${msg//\\/\\\\}
        esc=${esc//\"/\\\"}
        curl -fsS -m 10 -X POST -H 'Content-Type: application/json' \
            --data "{\"text\":\"$esc\"}" "$ALERT_WEBHOOK_URL" > /dev/null 2>&1 || true
    fi
}

if [ -z "$API_KEY" ]; then
    alert "NOT CONFIGURED: UPTIMEROBOT_API_KEY is unset — this control is OFF and cannot report"
    exit 2
fi

# The key goes in a 0600 temp file, never on the command line: an argument is
# readable by any user via ps while curl runs.
umask 077
body=$(mktemp) || { alert "could not create a temp file for the request body"; exit 2; }
response=$(mktemp) || { rm -f "$body"; alert "could not create a temp file for the response"; exit 2; }
trap 'rm -f "$body" "$response"' EXIT

printf 'api_key=%s&format=json&alert_contacts=1&logs=0' "$API_KEY" > "$body"

if ! curl -fsS -m 20 -X POST \
    -H 'Content-Type: application/x-www-form-urlencoded' \
    -H 'Cache-Control: no-cache' \
    --data "@$body" "$API_URL" > "$response"; then
    alert "API UNREACHABLE: no answer from the UptimeRobot API — the monitor's state is UNKNOWN"
    exit 1
fi

# Verdict in python3: the response is nested JSON and bash has no business
# parsing it. Prints human lines; its exit code is the verdict.
NON_INTERRUPTING_TYPES="$NON_INTERRUPTING_TYPES" python3 - "$response" <<'PY'
import json
import os
import sys

non_interrupting = {int(t) for t in os.environ["NON_INTERRUPTING_TYPES"].split()}

with open(sys.argv[1]) as fh:
    try:
        data = json.load(fh)
    except json.JSONDecodeError:
        print("API MALFORMED: the response was not JSON — the monitor's state is UNKNOWN")
        sys.exit(1)

if data.get("stat") != "ok":
    message = (data.get("error") or {}).get("message", "no message")
    print(f"API ERROR: UptimeRobot refused the request ({message})")
    sys.exit(1)

monitors = data.get("monitors") or []
if not monitors:
    print("NO MONITOR: the account has no monitors — nothing is watching the site")
    sys.exit(1)

problems = 0
for monitor in monitors:
    name = monitor.get("friendly_name", "unnamed")
    # UptimeRobot status: 0 paused, 1 not checked yet, 2 up, 8/9 down.
    if monitor.get("status") == 0:
        print(f"PAUSED: monitor {name!r} is paused and is detecting nothing")
        problems += 1
        continue

    contacts = monitor.get("alert_contacts") or []
    if not contacts:
        print(f"NO ALERT CONTACT: monitor {name!r} detects outages and tells nobody")
        problems += 1
        continue

    # Contact status 0 means the channel is switched off. This is the exact
    # production failure: contacts attached, channel toggled off, silence.
    enabled = [c for c in contacts if str(c.get("status")) != "0"]
    seen = " ".join(f"type={c.get('type')}/status={c.get('status')}" for c in contacts)
    print(f"  {name}: {len(contacts)} contact(s) — {seen}")

    if not enabled:
        print(f"NO ENABLED ALERT CONTACT: every channel on {name!r} is switched OFF")
        problems += 1
        continue

    interrupting = [c for c in enabled if int(c.get("type", -1)) not in non_interrupting]
    if not interrupting:
        print(
            f"NO INTERRUPTING CHANNEL: {name!r} can only reach a passive channel "
            f"(types {sorted(non_interrupting)}). An outage will not wake anyone."
        )
        problems += 1
        continue

    print(f"  {name}: OK — {len(interrupting)} interrupting channel(s) enabled")

if problems:
    print(f"{problems} problem(s) found")
    sys.exit(1)

print("LIVENESS OK — monitor active, alert contacts enabled, an interrupting channel is live")
PY
verdict=$?

if [ "$verdict" -ne 0 ]; then
    # The python half printed the detail to stdout; the alert carries the headline
    # so a webhook/cron mail is actionable on its own.
    alert "CHECK FAILED: the uptime monitor's alerting chain is broken — see the run output"
    exit "$verdict"
fi

exit 0
