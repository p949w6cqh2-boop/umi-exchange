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
#   3. at least one alert contact is ATTACHED to it;
#   4. at least one attached contact is ACTIVE — UptimeRobot status 2, nothing else;
#   5. at least one active contact is an INTERRUPTING channel, not e-mail alone.
#
# ⚖️ 2026-11-03: the first version of this script was a false green. It read
# contact status from getMonitors, which does not return it, counted "no answer"
# as on, and treated status 1 — PAUSED — as on. It printed LIVENESS OK on the
# live account while every attached contact was off. The status values below are
# UptimeRobot's documented ones, and the responses are the shapes measured that
# night (tests/test_monitor_liveness.py).
#
# KEY: the account's READ-ONLY API key. A monitor-specific key may call
# getMonitors only, so it can never see whether a contact is on; this refuses it.
#
# Run it on the steward's LAPTOP, not the droplet (his call "a", 2026-11-03): it
# talks to UptimeRobot, not to the server, so production holds no third-party key.
#
# Alerts POST to $ALERT_WEBHOOK_URL (same shape as monitor.sh); without it they go
# to stderr. Exit code is NON-ZERO on any failure, because this script's whole
# purpose is to be loud.
set -uo pipefail

API_BASE="${UPTIMEROBOT_API_BASE:-https://api.uptimerobot.com/v2}"
API_KEY="${UPTIMEROBOT_API_KEY:-}"
# UptimeRobot alert-contact types that do NOT interrupt a human. 2 is E-mail —
# the channel that was off for the 30 days above. 5 is Web-Hook: a post into a
# room nobody is looking at has the same shape as an unread inbox.
# Override only with a recorded reason. NARROWING this list (counting e-mail as
# interrupting, say, because the phone's mail app pings) is the direction that can
# quietly re-open box 1, so the reason belongs in the box's own text when you do.
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
monitors=$(mktemp) || { rm -f "$body"; alert "could not create a temp file"; exit 2; }
contacts=$(mktemp) || { rm -f "$body" "$monitors"; alert "could not create a temp file"; exit 2; }
trap 'rm -f "$body" "$monitors" "$contacts"' EXIT

fetch() { # fetch <endpoint> <outfile> [extra form fields]
    printf 'api_key=%s&format=json%s' "$API_KEY" "${3:-}" > "$body"
    curl -fsS -m 20 -X POST \
        -H 'Content-Type: application/x-www-form-urlencoded' \
        -H 'Cache-Control: no-cache' \
        --data "@$body" "$API_BASE/$1" > "$2"
}

if ! fetch getMonitors "$monitors" '&alert_contacts=1&logs=0'; then
    alert "API UNREACHABLE: no answer from the UptimeRobot API — the monitor's state is UNKNOWN"
    exit 1
fi
# getAlertContacts is where on/off lives. If it cannot be read, the verdict says so.
fetch getAlertContacts "$contacts" || printf '{"stat":"fail","error":{"message":"no answer"}}' > "$contacts"

# Verdict in python3: the responses are nested JSON and bash has no business
# parsing them. Prints human lines; its exit code is the verdict.
NON_INTERRUPTING_TYPES="$NON_INTERRUPTING_TYPES" python3 - "$monitors" "$contacts" <<'PY'
import json
import os
import sys

# UptimeRobot's documented alert-contact status values. ONLY 2 delivers.
STATUS = {0: "not-activated", 1: "paused", 2: "active"}
non_interrupting = {int(t) for t in os.environ["NON_INTERRUPTING_TYPES"].split()}


def load(path):
    with open(path) as fh:
        try:
            return json.load(fh)
        except json.JSONDecodeError:
            return None


mon = load(sys.argv[1])
if mon is None:
    print("API MALFORMED: getMonitors was not JSON — the monitor's state is UNKNOWN")
    sys.exit(1)
if mon.get("stat") != "ok":
    print(f"API ERROR: UptimeRobot refused getMonitors ({(mon.get('error') or {}).get('message', 'no message')})")
    sys.exit(1)

con = load(sys.argv[2]) or {}
if con.get("stat") != "ok":
    message = (con.get("error") or {}).get("message", "no message")
    print(
        "CANNOT READ CONTACT STATUS: getAlertContacts refused or failed "
        f"({message}). Use the account's Read-Only API key — a monitor-specific key "
        "can call getMonitors only, so it can never see whether a contact is on."
    )
    sys.exit(1)
status_of = {str(c.get("id")): c.get("status") for c in con.get("alert_contacts") or []}

monitors = mon.get("monitors") or []
if not monitors:
    print("NO MONITOR: the account has no monitors — nothing is watching the site")
    sys.exit(1)

problems = 0
for monitor in monitors:
    name = monitor.get("friendly_name", "unnamed")
    # Monitor status: 0 paused, 1 not checked yet, 2 up, 8/9 down.
    if monitor.get("status") == 0:
        print(f"PAUSED: monitor {name!r} is paused and is detecting nothing")
        problems += 1
        continue

    attached = monitor.get("alert_contacts") or []
    if not attached:
        print(f"NO ALERT CONTACT: monitor {name!r} detects outages and tells nobody")
        problems += 1
        continue

    active, lines = [], []
    for contact in attached:
        cid, ctype = str(contact.get("id")), contact.get("type")
        state = STATUS.get(status_of.get(cid), "UNKNOWN") if cid in status_of else "UNKNOWN"
        lines.append(f"type={ctype} {state}")
        if state == "active":
            active.append(contact)
    print(f"  {name}: {len(attached)} attached — " + " · ".join(lines))
    if any(line.endswith("UNKNOWN") for line in lines):
        print(f"  UNKNOWN status on {name!r}: a contact is attached but getAlertContacts does not list it")

    if not active:
        print(f"NO ACTIVE ALERT CONTACT: every channel on {name!r} is paused, not activated or unknown")
        problems += 1
        continue

    interrupting = [c for c in active if int(c.get("type", -1)) not in non_interrupting]
    if not interrupting:
        print(
            f"NO INTERRUPTING CHANNEL: {name!r} can only reach a passive channel "
            f"(types {sorted(non_interrupting)}). An outage will not wake anyone."
        )
        problems += 1
        continue

    print(f"  {name}: OK — {len(interrupting)} interrupting channel(s) active")

if problems:
    print(f"{problems} problem(s) found")
    sys.exit(1)

print("LIVENESS OK — monitor active, an interrupting alert contact is ACTIVE (status 2)")
PY
verdict=$?

if [ "$verdict" -ne 0 ]; then
    alert "CHECK FAILED: the uptime monitor's alerting chain is broken — see the run output"
    exit "$verdict"
fi

exit 0
