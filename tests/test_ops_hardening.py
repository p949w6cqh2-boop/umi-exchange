"""
Ops/deploy hardening (bug-hunt batch 8, #28 #29).

#28 production.py called sentry_sdk.init(send_default_pii=False) under the comment
    "Never send PII to Sentry". That comment is materially false: send_default_pii
    gates cookies and user identity only. The request body (max_request_body_size
    defaults to "medium") and frame locals (include_local_variables defaults True)
    are sent regardless, and the casework field names — body, summary, detail — are
    not on any scrubber denylist. Any operator who sets SENTRY_DSN, which the README
    encourages, would ship envelope-decrypted casework narratives and Person PII
    off-box on the first unhandled 500. Dormant here (SENTRY_DSN is empty and
    docs/monitoring-decision.md keeps it off for exactly this reason), but this is a
    reference implementation others adopt.

#29 The image HEALTHCHECK ran `curl -sf http://localhost:8000/health/` with no -L.
    Under production settings SECURE_SSL_REDIRECT=True means SecurityMiddleware 301s
    a plain-HTTP request before any app code runs, and `curl --fail` only trips on
    >=400 — so the probe exited 0 without ever reaching the database check. The
    container reported healthy while every real request 500'd. docker-compose.prod.yml
    already worked around it with an X-Forwarded-Proto probe; the image and
    docker-compose.yml inherited the broken one.
"""

import re
from pathlib import Path

import pytest
from django.test import Client, override_settings

REPO = Path(__file__).resolve().parent.parent
DOCKERFILES = (REPO / "Dockerfile", REPO / "docker" / "Dockerfile")


def _healthcheck_line(path):
    for line in path.read_text().splitlines():
        if line.startswith("HEALTHCHECK"):
            return line
    raise AssertionError(f"{path} has no HEALTHCHECK line")


# ------------------------------------------------------------------------ #28
def test_sentry_options_never_send_frame_locals():
    """Frame locals are where a decrypted case narrative sits at 500 time."""
    from config.sentry import sentry_options

    opts = sentry_options("https://key@example.test/1", environment="production", release="abc")

    assert opts["include_local_variables"] is False


def test_sentry_options_never_send_request_bodies():
    """A POSTed note body is the plaintext the envelope encryption exists to protect."""
    from config.sentry import sentry_options

    opts = sentry_options("https://key@example.test/1", environment="production", release="abc")

    assert opts["max_request_body_size"] == "never"


def test_sentry_options_keep_default_pii_off():
    from config.sentry import sentry_options

    opts = sentry_options("https://key@example.test/1", environment="production", release="abc")

    assert opts["send_default_pii"] is False


def test_sentry_options_set_the_privacy_keys_explicitly():
    """Both keys must be stated, never inherited: the SDK's own defaults are the
    leaky ones (include_local_variables=True, max_request_body_size='medium'), so
    relying on defaults is how this bug happened in the first place."""
    from config.sentry import sentry_options

    opts = sentry_options("https://key@example.test/1", environment="production", release="abc")

    assert "include_local_variables" in opts
    assert "max_request_body_size" in opts


# ------------------------------------------------------------------------ #29
@pytest.mark.django_db
@override_settings(SECURE_SSL_REDIRECT=True, SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"))
def test_health_probe_without_the_proxy_header_is_redirected_before_any_app_code():
    """This is why the old probe was permanently green — it never reached the app."""
    resp = Client().get("/health/")

    assert resp.status_code == 301


@pytest.mark.django_db
@override_settings(SECURE_SSL_REDIRECT=True, SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"))
def test_health_probe_with_the_proxy_header_reaches_the_database_check():
    resp = Client().get("/health/", headers={"x-forwarded-proto": "https"})

    assert resp.status_code == 200
    assert resp.json()["db"] == "ok"


def test_image_healthcheck_sends_the_proxy_header():
    """Both Dockerfiles — docker/Dockerfile is canonical, the root one is its alias
    (tests/test_dockerfile_parity.py keeps them identical)."""
    for path in DOCKERFILES:
        line = _healthcheck_line(path)
        assert re.search(r"X-Forwarded-Proto:\s*https", line), f"{path}: probe would be 301'd, never reaching /health/"


def test_image_healthcheck_survives_a_configured_health_token():
    """/health/ 403s without ?token= when HEALTH_CHECK_TOKEN is set. A probe that
    ignores the token would flip a healthy container to unhealthy the moment an
    operator sets one — the same false signal in the other direction."""
    for path in DOCKERFILES:
        line = _healthcheck_line(path)
        assert "HEALTH_CHECK_TOKEN" in line, f"{path}: probe ignores the health token"
