"""
The monitor that watches the site is itself unwatched, and that is the gap this
script closes.

Found in production and recorded in `docs/ethics-and-safety.md` box 1: the
UptimeRobot monitor existed and was detecting outages correctly for over two
weeks while its **E-mail notification channel was switched off**. In the 30 days
before anyone noticed: 84.416% uptime, 4 incidents, 4d 19h 56m down, and not one
of them reached a human. Detection working with alerting silently disabled is
worse than no monitoring, because it produces confidence without coverage.

⚖️ REWRITTEN TWICE on 2026-11-03, and the reasons are the point of this file:
  1. The first version was a FALSE GREEN. Its fixtures were the response shape I
     EXPECTED from the legacy v2 API: `getMonitors` returns attached contacts
     with no status, and the script counted "no answer" as on.
  2. The second version, coded to the legacy docs (`1` = paused), would have
     been a FALSE RED. Read against the live account, the legacy API reported `1`
     for the e-mail and push contacts the dashboard shows ON, and the v3 API
     (what the dashboard runs on) reported both as "Active".
So the check now uses v3, where status and type are words, and every fixture
below is a v3 response shape MEASURED on 2026-11-03.

Same pattern as test_backup_script.py: invoke the real script with a real shell.
UptimeRobot is a throwaway local HTTP server that answers each endpoint
separately and refuses a request without the right bearer token, exactly as the
real API does. Nothing reaches the network.
"""

import json
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "monitor_liveness.sh"
KEY = "ur0000000-test"


def _monitors(status="UP", attached=()):
    """GET /v3/monitors, as measured: {"data": [...]}; attached contacts are
    {alertContactId, threshold, recurrence} and carry no status."""
    return {
        "data": [
            {
                "id": 790000001,
                "friendlyName": "Reciprocal Aid Network",
                "status": status,
                "url": "https://reciprocalaid.network/health/",
                "apiKey": "never-printed",
                "assignedAlertContacts": [{"alertContactId": cid, "threshold": 0, "recurrence": 0} for cid in attached],
            }
        ]
    }


def _contacts(*rows):
    """GET /v3/user/alert-contacts, as measured: a list; type and status are words."""
    return [
        {"id": cid, "type": ctype, "status": status, "friendlyName": "redacted", "value": "redacted"}
        for cid, ctype, status in rows
    ]


@pytest.fixture
def api():
    """A throwaway UptimeRobot v3. Set `api.routes[path]` to (http_code, body)."""

    class State:
        routes = {"/v3/monitors": (200, _monitors()), "/v3/user/alert-contacts": (200, _contacts())}
        seen_auth = []

    state = State()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            state.seen_auth.append(self.headers.get("Authorization"))
            if self.headers.get("Authorization") != f"Bearer {KEY}":
                code, payload = 401, {"message": "Unauthorized"}
            else:
                code, payload = state.routes.get(self.path, (404, {"message": "Not Found"}))
            body = json.dumps(payload).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    state.base = f"http://127.0.0.1:{server.server_port}/v3"
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


def _check(api, key=KEY, **extra_env):
    return _run({"UPTIMEROBOT_API_KEY": key, "UPTIMEROBOT_API_BASE": api.base, **extra_env})


def _out(result):
    return result.stdout + result.stderr


def test_no_api_key_fails_loudly():
    """An unconfigured liveness check must never look like a passing one — the
    whole defect class here is a control that is off while reporting nothing."""
    result = _run()

    assert result.returncode != 0
    assert "UPTIMEROBOT_API_KEY" in _out(result)


def test_it_sends_the_key_as_a_bearer_token(api):
    """v3 authenticates with a bearer token. Wrong wiring is a 401, not a pass."""
    _check(api)

    assert f"Bearer {KEY}" in api.seen_auth


def test_an_active_push_contact_passes(api):
    api.routes["/v3/monitors"] = (200, _monitors(attached=[8990105]))
    api.routes["/v3/user/alert-contacts"] = (200, _contacts((8990105, "MobileAppOld", "Active")))

    result = _check(api)

    assert result.returncode == 0, _out(result)
    assert "LIVENESS OK" in result.stdout


def test_the_real_2026_11_03_state_is_email_only(api):
    """⭐ Read off the live account with the Read-Only key on 2026-11-03 (v3):
    attached ProSms + Voice not activated, e-mail ACTIVE; push active but NOT
    attached. By default e-mail is not interrupting, so this must fail — and
    say why — rather than pass on an inbox."""
    api.routes["/v3/monitors"] = (200, _monitors(attached=[8633663, 8633664, 8662643]))
    api.routes["/v3/user/alert-contacts"] = (
        200,
        _contacts(
            (8633664, "Voice", "NotActivated"),
            (8633663, "ProSms", "NotActivated"),
            (8662643, "Email", "Active"),
            (8990105, "MobileAppOld", "Active"),
        ),
    )

    result = _check(api)

    assert result.returncode != 0
    assert "NO INTERRUPTING" in _out(result)


def test_the_real_state_passes_on_the_stewards_recorded_reason(api):
    """His call, recorded in box 1: his phone notifies on alert e-mail, so e-mail
    counts as interrupting for him. The same live state then passes."""
    api.routes["/v3/monitors"] = (200, _monitors(attached=[8633663, 8633664, 8662643]))
    api.routes["/v3/user/alert-contacts"] = (
        200,
        _contacts(
            (8633664, "Voice", "NotActivated"),
            (8633663, "ProSms", "NotActivated"),
            (8662643, "Email", "Active"),
        ),
    )

    result = _check(api, UMI_NON_INTERRUPTING_TYPES="Webhook")

    assert result.returncode == 0, _out(result)


def test_a_paused_contact_is_not_on(api):
    """The 09-05 failure: contact attached, channel paused, silence."""
    api.routes["/v3/monitors"] = (200, _monitors(attached=[1]))
    api.routes["/v3/user/alert-contacts"] = (200, _contacts((1, "MobileAppOld", "Paused")))

    result = _check(api)

    assert result.returncode != 0
    assert "NO ACTIVE ALERT CONTACT" in _out(result)


def test_a_not_activated_contact_is_not_on(api):
    """A contact whose address or number was never confirmed delivers nothing."""
    api.routes["/v3/monitors"] = (200, _monitors(attached=[1]))
    api.routes["/v3/user/alert-contacts"] = (200, _contacts((1, "ProSms", "NotActivated")))

    result = _check(api)

    assert result.returncode != 0
    assert "NO ACTIVE ALERT CONTACT" in _out(result)


def test_only_the_word_active_counts(api):
    """The legacy API reported a NUMBER for status, and its documented meaning
    turned out not to match the live system. Nothing but "Active" counts."""
    api.routes["/v3/monitors"] = (200, _monitors(attached=[1, 2]))
    api.routes["/v3/user/alert-contacts"] = (200, _contacts((1, "MobileAppOld", 1), (2, "MobileAppOld", "active?")))

    result = _check(api)

    assert result.returncode != 0
    assert "NO ACTIVE ALERT CONTACT" in _out(result)


def test_an_unknown_contact_is_not_a_pass(api):
    """No answer is not 'on'. An attached contact missing from the contact list
    has no readable status, and must not count."""
    api.routes["/v3/monitors"] = (200, _monitors(attached=[1]))
    api.routes["/v3/user/alert-contacts"] = (200, _contacts())

    result = _check(api)

    assert result.returncode != 0
    assert "UNKNOWN" in _out(result)


def test_a_key_that_cannot_read_contacts_fails_and_says_which_key(api):
    """A key without access to the contact list must not pass on what it could
    not see — and must say which key to use instead."""
    api.routes["/v3/monitors"] = (200, _monitors(attached=[1]))
    api.routes["/v3/user/alert-contacts"] = (403, {"message": "Forbidden"})

    result = _check(api)

    assert result.returncode != 0
    assert "Read-Only" in _out(result)


def test_a_rejected_key_is_not_a_pass(api):
    """A bad, revoked or expired key must fail loudly with the HTTP code."""
    result = _check(api, key="ur-wrong")

    assert result.returncode != 0
    assert "401" in _out(result)


def test_a_paused_monitor_fails(api):
    """A paused monitor detects nothing. It is the quietest possible failure."""
    api.routes["/v3/monitors"] = (200, _monitors(status="PAUSED", attached=[1]))
    api.routes["/v3/user/alert-contacts"] = (200, _contacts((1, "MobileAppOld", "Active")))

    result = _check(api)

    assert result.returncode != 0
    assert "PAUSED" in _out(result)


def test_no_alert_contact_attached_fails(api):
    """Detection with nothing attached is the zero-humans-reached state."""
    api.routes["/v3/monitors"] = (200, _monitors(attached=[]))

    result = _check(api)

    assert result.returncode != 0
    assert "NO ALERT CONTACT" in _out(result)


def test_a_webhook_is_not_interrupting(api):
    """A web-hook into a channel nobody watches has the same shape as e-mail."""
    api.routes["/v3/monitors"] = (200, _monitors(attached=[1]))
    api.routes["/v3/user/alert-contacts"] = (200, _contacts((1, "Webhook", "Active")))

    result = _check(api)

    assert result.returncode != 0
    assert "NO INTERRUPTING" in _out(result)


def test_it_prints_each_attached_contact_with_its_state(api):
    """The run is also the reading: which channels exist and which are on."""
    api.routes["/v3/monitors"] = (200, _monitors(attached=[1, 2]))
    api.routes["/v3/user/alert-contacts"] = (200, _contacts((1, "MobileAppOld", "Active"), (2, "Email", "Paused")))

    result = _check(api)

    assert "MobileAppOld Active" in result.stdout
    assert "Email Paused" in result.stdout


def test_secrets_never_appear_in_output(api):
    """The key is a credential, and the monitor object carries one of its own."""
    api.routes["/v3/monitors"] = (200, _monitors(attached=[1]))
    api.routes["/v3/user/alert-contacts"] = (200, _contacts((1, "Email", "Paused")))

    result = _check(api)

    assert KEY not in _out(result)
    assert "never-printed" not in _out(result)
