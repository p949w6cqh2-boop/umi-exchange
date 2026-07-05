"""M-16: the Content-Security-Policy was configured (flat CSP_* in production.py)
but never emitted — django-csp 4.x reads a CONTENT_SECURITY_POLICY dict and the
`csp` app/middleware were never wired in, so no CSP header was sent and
`check --deploy` reported clean the whole time. These tests assert the header is
actually present, so a silent no-op can't recur."""

import pytest


@pytest.mark.django_db
def test_csp_header_present_with_core_directives(client):
    resp = client.get("/")
    csp = resp.headers.get("Content-Security-Policy", "")

    assert csp, "Content-Security-Policy header must be present on responses"
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp


@pytest.mark.django_db
def test_csp_permits_what_the_app_loads(client):
    """The enforced policy must permit what the app actually uses in the browser,
    or it breaks the app. Verified against real console behavior: inline scripts
    (the toast system) need script-src 'unsafe-inline'; Alpine's expression eval
    needs 'unsafe-eval'; the CDN fallbacks need unpkg; Tailwind needs style-src
    'unsafe-inline'; QR codes need img-src data:. Tightening script-src back to
    'self'+unpkg is the hardening follow-up (nonces + Alpine CSP build)."""
    csp = client.get("/").headers.get("Content-Security-Policy", "")

    # script-src carries the app's current reality (see the settings comment)
    assert "script-src 'self' https://unpkg.com 'unsafe-inline' 'unsafe-eval'" in csp
    assert "style-src 'self' 'unsafe-inline'" in csp  # Tailwind inline
    assert "img-src 'self' data:" in csp  # inline QR codes
