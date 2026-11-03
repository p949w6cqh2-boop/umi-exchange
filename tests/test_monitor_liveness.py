"""
The monitor that watches the site is itself unwatched, and that is the gap this
script closes.

Found in production and recorded in `docs/ethics-and-safety.md` box 1: the
UptimeRobot monitor existed and was detecting outages correctly for over two
weeks while its **E-mail notification channel was switched off**. In the 30 days
before anyone noticed: 84.416% uptime, 4 incidents, 4d 19h 56m down, and not one
of them reached a human. Detection working with alerting silently disabled is
worse than no monitoring, because it produces confidence without coverage.

⚖️ REWRITTEN 2026-11-03, because the first version of this file was itself a
false green. Its fixtures were the API shape I EXPECTED, not the one UptimeRobot
returns, and the script passed against them while failing in production:
  * `getMonitors` lists a monitor's alert contacts WITHOUT their status — the
    first real run printed `status=None` for every contact, and the script
    counted "no answer" as "on";
  * the documented status values are `0` not activated, `1` PAUSED, `2` active,
    and the script treated anything but `0` as on — so a PAUSED contact, the
    09-05 failure itself, would have passed;
  * a monitor-specific key may call `getMonitors` only, so it can never see
    status at all; on/off lives in `getAlertContacts`, which needs the
    Read-Only key.
Every fixture below is shaped like a response measured on 2026-11-03.

Same pattern as test_backup_script.py: invoke the real script with a real shell.
The UptimeRobot API is served by a throwaway local HTTP server that answers each
endpoint separately, so the real curl path is exercised and nothing reaches the
network.
"""

import json
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "monitor_liveness.sh"

# UptimeRobot alert-contact types this repo can cite. 2 is E-mail — the channel
# that was off for the 30 days above. 5 is Web-Hook. 8 is what the account's
# SMS-style contact reports as (measured 2026-11-03).
EMAIL = 2
WEBHOOK = 5
SMS = 8

# Documented alert-contact status values (UptimeRobot API, getAlertContacts).
NOT_ACTIVATED, PAUSED, ACTIVE = 0, 1, 2


def _monitors(monitor_status=2, attached=()):
    """`getMonitors` with alert_contacts=1, as measured: the attached contacts
    carry an id and a type, and NO status field."""
    return {
        "stat": "ok",
        "monitors": [
            {
                "id": 790000001,
                "friendly_name": "Reciprocal Aid Network",
                "url": "https://reciprocalaid.network/health/",
                "status": monitor_status,
                "alert_contacts": [
                    {"id": str(cid), "type": ctype, "value": "redacted", "threshold": 0, "recurrence": 0}
                    for cid, ctype in attached
                ],
            }
        ],
    }


def _contacts(*rows):
    """`getAlertContacts`, as measured: id, type and the status that matters."""
    return {
        "stat": "ok",
        "total": len(rows),
        "alert_contacts": [
            {"id": str(cid), "friendly_name": "redacted", "type": ctype, "status": status, "value": "redacted"}
            for cid, ctype, status in rows
        ],
    }


@pytest.fixture
def api():
    """A throwaway UptimeRobot. Set `api.routes[endpoint]` to what it returns."""

    class State:
        routes = {"getMonitors": _monitors(), "getAlertContacts": _contacts()}

    state = State()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            endpoint = self.path.rstrip("/").rsplit("/", 1)[-1]
            payload = state.routes.get(endpoint, {"stat": "fail", "error": {"message": "unknown endpoint"}})
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    state.base = f"http://127.0.0.1:{server.server_port}/v2"
    yield state
    server.shutdown()


def _run(env=None, timeout=20):
    return subprocess.run(  # noqa: S603
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(REPO),
        env={"PATH": "/usr/bin:/bin:/usr/local/bin", **(env or {})},
    )


def _check(api, **extra_env):
    return _run({"UPTIMEROBOT_API_KEY": "k", "UPTIMEROBOT_API_BASE": api.base, **extra_env})


def test_no_api_key_fails_loudly():
    """An unconfigured liveness check must never look like a passing one — the
    whole defect class here is a control that is off while reporting nothing."""
    result = _run()

    assert result.returncode != 0
    assert "UPTIMEROBOT_API_KEY" in result.stdout + result.stderr


def test_an_active_interrupting_contact_passes(api):
    api.routes["getMonitors"] = _monitors(attached=[(11, SMS), (12, EMAIL)])
    api.routes["getAlertContacts"] = _contacts((11, SMS, ACTIVE), (12, EMAIL, ACTIVE))

    result = _check(api)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "LIVENESS OK" in result.stdout


def test_the_real_2026_11_03_state_fails(api):
    """⭐ The regression this rewrite exists for. Read off the live account with
    the Read-Only key on 2026-11-03: every attached contact was off — two
    'not activated', the e-mail one PAUSED. The first version of the script
    printed LIVENESS OK on this state."""
    api.routes["getMonitors"] = _monitors(attached=[(8633663, 8), (8633664, 14), (8662643, EMAIL)])
    api.routes["getAlertContacts"] = _contacts(
        (8633663, 8, NOT_ACTIVATED),
        (8633664, 14, NOT_ACTIVATED),
        (8662643, EMAIL, PAUSED),
        (8990105, 12, PAUSED),
    )

    result = _check(api)

    assert result.returncode != 0, "the false green is back: every attached contact is off"
    assert "LIVENESS OK" not in result.stdout
    assert "NO ACTIVE ALERT CONTACT" in result.stdout + result.stderr


def test_a_paused_contact_is_not_on(api):
    """The 09-05 failure: contact attached, channel paused, silence."""
    api.routes["getMonitors"] = _monitors(attached=[(11, SMS)])
    api.routes["getAlertContacts"] = _contacts((11, SMS, PAUSED))

    result = _check(api)

    assert result.returncode != 0
    assert "NO ACTIVE ALERT CONTACT" in result.stdout + result.stderr
    assert "paused" in (result.stdout + result.stderr).lower()


def test_a_not_activated_contact_is_not_on(api):
    """A contact whose address or number was never confirmed delivers nothing."""
    api.routes["getMonitors"] = _monitors(attached=[(11, SMS)])
    api.routes["getAlertContacts"] = _contacts((11, SMS, NOT_ACTIVATED))

    result = _check(api)

    assert result.returncode != 0
    assert "NO ACTIVE ALERT CONTACT" in result.stdout + result.stderr


def test_an_unknown_status_is_not_a_pass(api):
    """No answer is not 'on'. A contact attached to the monitor but missing from
    getAlertContacts has no readable status, and must not count."""
    api.routes["getMonitors"] = _monitors(attached=[(11, SMS)])
    api.routes["getAlertContacts"] = _contacts()

    result = _check(api)

    assert result.returncode != 0
    assert "UNKNOWN" in result.stdout + result.stderr


def test_a_monitor_specific_key_cannot_read_status_and_says_so(api):
    """A monitor-specific key may call getMonitors only. The check must not pass
    on what it could not see — and it must say which key to use instead."""
    api.routes["getMonitors"] = _monitors(attached=[(11, SMS)])
    api.routes["getAlertContacts"] = {"stat": "fail", "error": {"message": "api_key not authorized for this method"}}

    result = _check(api)

    assert result.returncode != 0
    assert "Read-Only" in result.stdout + result.stderr


def test_a_paused_monitor_fails(api):
    """A paused monitor detects nothing. It is the quietest possible failure."""
    api.routes["getMonitors"] = _monitors(monitor_status=0, attached=[(11, SMS)])
    api.routes["getAlertContacts"] = _contacts((11, SMS, ACTIVE))

    result = _check(api)

    assert result.returncode != 0
    assert "PAUSED" in result.stdout + result.stderr


def test_no_alert_contact_attached_fails(api):
    """Detection with nothing attached is the zero-humans-reached state."""
    api.routes["getMonitors"] = _monitors(attached=[])

    result = _check(api)

    assert result.returncode != 0
    assert "NO ALERT CONTACT" in result.stdout + result.stderr


def test_email_only_fails_because_email_is_not_interrupting(api):
    """Box 1 was re-opened specifically because e-mail was the only path."""
    api.routes["getMonitors"] = _monitors(attached=[(12, EMAIL)])
    api.routes["getAlertContacts"] = _contacts((12, EMAIL, ACTIVE))

    result = _check(api)

    assert result.returncode != 0
    assert "NO INTERRUPTING" in result.stdout + result.stderr


def test_email_counts_when_the_steward_says_it_interrupts(api):
    """His call, 2026-11-02: his phone notifies on alert e-mail, so e-mail is
    interrupting for him (UMI_NON_INTERRUPTING_TYPES=5, the reason in box 1)."""
    api.routes["getMonitors"] = _monitors(attached=[(12, EMAIL)])
    api.routes["getAlertContacts"] = _contacts((12, EMAIL, ACTIVE))

    result = _check(api, UMI_NON_INTERRUPTING_TYPES="5")

    assert result.returncode == 0, result.stdout + result.stderr


def test_a_webhook_is_not_interrupting_either(api):
    """A web-hook into a channel nobody watches has the same shape as e-mail."""
    api.routes["getMonitors"] = _monitors(attached=[(13, WEBHOOK)])
    api.routes["getAlertContacts"] = _contacts((13, WEBHOOK, ACTIVE))

    result = _check(api)

    assert result.returncode != 0
    assert "NO INTERRUPTING" in result.stdout + result.stderr


def test_an_api_failure_is_not_a_pass(api):
    """A bad, revoked or expired key, or UptimeRobot being down, must fail
    loudly rather than report a chain it never read."""
    api.routes["getMonitors"] = {"stat": "fail", "error": {"message": "api_key not found."}}

    result = _check(api)

    assert result.returncode != 0
    assert "API" in result.stdout + result.stderr


def test_it_prints_each_attached_contact_with_its_state(api):
    """The run is also the reading: which channels exist and which are on."""
    api.routes["getMonitors"] = _monitors(attached=[(11, SMS), (12, EMAIL)])
    api.routes["getAlertContacts"] = _contacts((11, SMS, ACTIVE), (12, EMAIL, PAUSED))

    result = _check(api)

    assert f"type={SMS} active" in result.stdout
    assert f"type={EMAIL} paused" in result.stdout


def test_the_api_key_never_appears_in_output(api):
    """The key is a credential; a log or an alert body is not a place for it."""
    api.routes["getMonitors"] = _monitors(attached=[(12, EMAIL)])
    api.routes["getAlertContacts"] = _contacts((12, EMAIL, PAUSED))

    result = _run({"UPTIMEROBOT_API_KEY": "ur1234567-secret", "UPTIMEROBOT_API_BASE": api.base})

    assert "ur1234567-secret" not in result.stdout + result.stderr
