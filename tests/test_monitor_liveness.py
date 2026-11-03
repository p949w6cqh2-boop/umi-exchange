"""
The monitor that watches the site is itself unwatched, and that is the gap this
script closes.

Found in production and recorded in `docs/ethics-and-safety.md` box 1: the
UptimeRobot monitor existed and was detecting outages correctly for over two
weeks while its **E-mail notification channel was switched off**. In the 30 days
before anyone noticed: 84.416% uptime, 4 incidents, 4d 19h 56m down, and not one
of them reached a human. Detection working with alerting silently disabled is
worse than no monitoring, because it produces confidence without coverage.

So this script asserts the whole chain, not just that a monitor exists: the
monitor is not paused, at least one alert contact is attached AND enabled, and at
least one of those is an INTERRUPTING channel rather than e-mail alone.

Same pattern as test_backup_script.py: invoke the real script with a real shell.
The UptimeRobot API is served by a throwaway local HTTP server, so the real curl
path is exercised and no test ever reaches the network.
"""

import json
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "monitor_liveness.sh"

# UptimeRobot alert-contact types. 2 is E-mail — the one channel we know was off
# during the 30 days above. 5 is Web-Hook.
EMAIL = 2
WEBHOOK = 5
SMS = 1


def _monitor(status=2, contacts=()):
    """One monitor in UptimeRobot's v2 getMonitors shape.

    status 2 = Up, 0 = Paused. alert_contacts carries each contact's own
    status, where 0 means the channel is switched off.
    """
    return {
        "stat": "ok",
        "monitors": [
            {
                "id": 790000001,
                "friendly_name": "reciprocalaid.network health",
                "url": "https://reciprocalaid.network/health/",
                "status": status,
                "alert_contacts": [{"id": f"{i}", "type": t, "status": s} for i, (t, s) in enumerate(contacts, 1)],
            }
        ],
    }


@pytest.fixture
def api():
    """A throwaway UptimeRobot. `api.payload` is what the next call returns."""

    class State:
        payload = _monitor()

    state = State()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.dumps(state.payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    state.url = f"http://127.0.0.1:{server.server_port}/v2/getMonitors"
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


def test_no_api_key_fails_loudly():
    """An unconfigured liveness check must never look like a passing one — the
    whole defect class here is a control that is off while reporting nothing."""
    result = _run()

    assert result.returncode != 0
    assert "UPTIMEROBOT_API_KEY" in result.stdout + result.stderr


def test_healthy_monitor_with_an_interrupting_contact_passes(api):
    api.payload = _monitor(contacts=[(SMS, 1), (EMAIL, 1)])

    result = _run({"UPTIMEROBOT_API_KEY": "k", "UPTIMEROBOT_API_URL": api.url})

    assert result.returncode == 0, result.stdout + result.stderr
    assert "LIVENESS OK" in result.stdout


def test_paused_monitor_fails(api):
    """A paused monitor detects nothing. It is the quietest possible failure."""
    api.payload = _monitor(status=0, contacts=[(SMS, 1)])

    result = _run({"UPTIMEROBOT_API_KEY": "k", "UPTIMEROBOT_API_URL": api.url})

    assert result.returncode != 0
    assert "PAUSED" in result.stdout + result.stderr


def test_no_alert_contact_attached_fails(api):
    """Runbook step 4 asks for contacts attached to the monitor. Detection with
    nothing attached is the 84.416%-uptime, zero-humans-reached state."""
    api.payload = _monitor(contacts=[])

    result = _run({"UPTIMEROBOT_API_KEY": "k", "UPTIMEROBOT_API_URL": api.url})

    assert result.returncode != 0
    assert "NO ALERT CONTACT" in result.stdout + result.stderr


def test_all_contacts_switched_off_fails(api):
    """The exact production failure: contacts attached, channel toggled off."""
    api.payload = _monitor(contacts=[(SMS, 0), (EMAIL, 0)])

    result = _run({"UPTIMEROBOT_API_KEY": "k", "UPTIMEROBOT_API_URL": api.url})

    assert result.returncode != 0
    assert "NO ENABLED" in result.stdout + result.stderr


def test_email_only_fails_because_email_is_not_interrupting(api):
    """Box 1 was re-opened specifically because e-mail was the only path. An
    enabled e-mail contact is not evidence that an outage reaches a human."""
    api.payload = _monitor(contacts=[(EMAIL, 1)])

    result = _run({"UPTIMEROBOT_API_KEY": "k", "UPTIMEROBOT_API_URL": api.url})

    assert result.returncode != 0
    assert "NO INTERRUPTING" in result.stdout + result.stderr


def test_webhook_is_not_interrupting_either(api):
    """A web-hook into a channel nobody watches has the same shape as e-mail."""
    api.payload = _monitor(contacts=[(WEBHOOK, 1)])

    result = _run({"UPTIMEROBOT_API_KEY": "k", "UPTIMEROBOT_API_URL": api.url})

    assert result.returncode != 0
    assert "NO INTERRUPTING" in result.stdout + result.stderr


def test_api_failure_is_not_a_pass(api):
    """A bad key, a revoked key, or UptimeRobot being down must fail loudly
    rather than report a healthy chain it never read."""
    api.payload = {"stat": "fail", "error": {"message": "api_key not found."}}

    result = _run({"UPTIMEROBOT_API_KEY": "k", "UPTIMEROBOT_API_URL": api.url})

    assert result.returncode != 0
    assert "API" in result.stdout + result.stderr


def test_it_prints_the_contact_types_it_saw(api):
    """First-run calibration: UptimeRobot's numeric type for mobile push is not
    documented in this repo, so the script reports what it actually found."""
    api.payload = _monitor(contacts=[(SMS, 1)])

    result = _run({"UPTIMEROBOT_API_KEY": "k", "UPTIMEROBOT_API_URL": api.url})

    assert f"type={SMS}" in result.stdout


def test_the_api_key_never_appears_in_output(api):
    """The key is a credential; a cron log or an alert body is not a place for it."""
    api.payload = _monitor(contacts=[(EMAIL, 1)])

    result = _run({"UPTIMEROBOT_API_KEY": "u1234567-secret", "UPTIMEROBOT_API_URL": api.url})

    assert "u1234567-secret" not in result.stdout + result.stderr
