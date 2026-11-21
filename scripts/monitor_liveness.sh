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
#   1. the API answers, and accepts the key;
#   2. the monitor exists and is not paused;
#   3. at least one alert contact is ATTACHED to it;
#   4. at least one attached contact is "Active" — that word, nothing else;
#   5. at least one active contact is an INTERRUPTING channel, not e-mail alone.
#
# ⚖️ 2026-11-03, in this order: the first version read UptimeRobot's legacy v2
# API and was a FALSE GREEN (it counted a missing status as on). Recoding it to
# the legacy docs would have made it a FALSE RED: read against the live account,
# v2 reported status 1, documented as "paused", for the e-mail and push contacts
# the dashboard shows ON, and v3 reported both as "Active". So this uses v3, the
# API the dashboard runs on, where status and type are words.
#
# KEY: the account's READ-ONLY API key, sent as a bearer token from a 0600 temp
# file, so it is never on the command line where ps would show it.
#
# Run it on the steward's LAPTOP, not the droplet (his call "a", 2026-11-03): it
# talks to UptimeRobot, not to the server, so production holds no third-party key.
#
# Alerts POST to $ALERT_WEBHOOK_URL (same shape as monitor.sh); without it they go
# to stderr. Exit code is NON-ZERO on any failure, because this script's whole
# purpose is to be loud.
set -uo pipefail

API_BASE="${UPTIMEROBOT_API_BASE:-https://api.uptimerobot.com/v3}"
API_KEY="${UPTIMEROBOT_API_KEY:-}"
# v3 alert-contact types that do NOT interrupt a human. Email is the channel that
# was off for the 30 days above; Webhook posts into a room nobody may be watching.
# Override only with a recorded reason. NARROWING this list (counting e-mail as
# interrupting, say, because the phone's mail app pings) is the direction that can
# quietly re-open box 1, so the reason belongs in the box's own text when you do.
NON_INTERRUPTING_TYPES="${UMI_NON_INTERRUPTING_TYPES:-Email Webhook}"
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

umask 077
hdr=$(mktemp) || { alert "could not create a temp file for the request headers"; exit 2; }
monitors=$(mktemp) || { rm -f "$hdr"; alert "could not create a temp file"; exit 2; }
contacts=$(mktemp) || { rm -f "$hdr" "$monitors"; alert "could not create a temp file"; exit 2; }
trap 'rm -f "$hdr" "$monitors" "$contacts"' EXIT
printf 'Authorization: Bearer %s\nAccept: application/json\n' "$API_KEY" > "$hdr"

fetch() { # fetch <path> <outfile>  -> prints the HTTP status code (000 if unreachable)
    local code
    code=$(curl -sS -m 20 -H @"$hdr" -o "$2" -w '%{http_code}' "$API_BASE$1" 2>/dev/null)
    echo "${code:-000}"
}

monitors_code=$(fetch /monitors "$monitors")
contacts_code=$(fetch /user/alert-contacts "$contacts")

# Verdict in python3: the responses are nested JSON and bash has no business
# parsing them. Prints human lines; its exit code is the verdict.
NON_INTERRUPTING_TYPES="$NON_INTERRUPTING_TYPES" python3 - "$monitors" "$monitors_code" "$contacts" "$contacts_code" <<'PY'
import json
import os
import sys

monitors_file, monitors_code, contacts_file, contacts_code = sys.argv[1:5]
non_interrupting = set(os.environ["NON_INTERRUPTING_TYPES"].split())


def load(path):
    with open(path) as fh:
        try:
            return json.load(fh)
        except json.JSONDecodeError:
            return None


if monitors_code == "000":
    print("API UNREACHABLE: no answer from the UptimeRobot API — the monitor's state is UNKNOWN")
    sys.exit(1)
if monitors_code != "200":
    print(f"API ERROR: UptimeRobot refused GET /monitors (HTTP {monitors_code}) — key invalid, revoked or expired?")
    sys.exit(1)
mon = load(monitors_file)
monitors = mon.get("data") if isinstance(mon, dict) else mon
if not isinstance(monitors, list):
    print("API MALFORMED: GET /monitors did not return a monitor list — the monitor's state is UNKNOWN")
    sys.exit(1)

con = load(contacts_file)
if contacts_code != "200" or not isinstance(con, list):
    print(
        f"CANNOT READ CONTACT STATUS: GET /user/alert-contacts answered HTTP {contacts_code}. "
        "Use the account's Read-Only API key — without the contact list, nothing can "
        "say whether an alert would reach anyone."
    )
    sys.exit(1)
by_id = {str(c.get("id")): c for c in con}

if not monitors:
    print("NO MONITOR: the account has no monitors — nothing is watching the site")
    sys.exit(1)

problems = 0
for monitor in monitors:
    name = monitor.get("friendlyName", "unnamed")
    if monitor.get("status") == "PAUSED":
        print(f"PAUSED: monitor {name!r} is paused and is detecting nothing")
        problems += 1
        continue

    attached = [str(a.get("alertContactId")) for a in monitor.get("assignedAlertContacts") or []]
    if not attached:
        print(f"NO ALERT CONTACT: monitor {name!r} detects outages and tells nobody")
        problems += 1
        continue

    active, lines, unknown = [], [], False
    for cid in attached:
        contact = by_id.get(cid)
        if contact is None:
            lines.append(f"{cid} UNKNOWN")
            unknown = True
            continue
        ctype, status = contact.get("type"), contact.get("status")
        lines.append(f"{ctype} {status}")
        # Only the word. The legacy API's numeric status did not mean what its
        # docs said, so a value we cannot name is not "on".
        if status == "Active":
            active.append(contact)
    print(f"  {name}: {len(attached)} attached — " + " · ".join(lines))
    if unknown:
        print(f"  UNKNOWN status on {name!r}: an attached contact is missing from the contact list")

    if not active:
        print(f"NO ACTIVE ALERT CONTACT: every channel on {name!r} is paused, not activated or unknown")
        problems += 1
        continue

    interrupting = [c for c in active if c.get("type") not in non_interrupting]
    if not interrupting:
        print(
            f"NO INTERRUPTING CHANNEL: {name!r} can only reach a passive channel "
            f"({' '.join(sorted(non_interrupting))}). An outage will not wake anyone."
        )
        problems += 1
        continue

    kinds = ", ".join(sorted({str(c.get("type")) for c in interrupting}))
    print(f"  {name}: OK — interrupting and active: {kinds}")

if problems:
    print(f"{problems} problem(s) found")
    sys.exit(1)

print("LIVENESS OK — monitor active, an interrupting alert contact is Active")
PY
verdict=$?

if [ "$verdict" -ne 0 ]; then
    alert "CHECK FAILED: the uptime monitor's alerting chain is broken — see the run output"
    exit "$verdict"
fi

exit 0
