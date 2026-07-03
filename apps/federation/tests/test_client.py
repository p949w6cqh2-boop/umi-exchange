"""Outbound client SSRF hardening (§9.3 decision + review): https-only,
redirects refused, non-public destinations rejected outside DEBUG."""

import pytest

from apps.federation import client as client_mod
from apps.federation.client import FederationClientError, _NoRedirectHandler, _validate_public_url


class TestUrlValidation:
    def test_https_required_outside_debug(self, settings):
        settings.DEBUG = False
        with pytest.raises(FederationClientError):
            _validate_public_url("http://peer.example/x")

    def test_loopback_rejected_outside_debug(self, settings):
        settings.DEBUG = False
        with pytest.raises(FederationClientError):
            _validate_public_url("https://127.0.0.1/x")

    def test_link_local_metadata_rejected_outside_debug(self, settings):
        settings.DEBUG = False
        with pytest.raises(FederationClientError):
            _validate_public_url("https://169.254.169.254/latest/meta-data/")

    def test_unsupported_scheme_rejected(self, settings):
        settings.DEBUG = True
        with pytest.raises(FederationClientError):
            _validate_public_url("ftp://peer.example/x")

    def test_debug_allows_localhost(self, settings):
        settings.DEBUG = True
        _validate_public_url("http://localhost:8000/x")  # no raise


class TestRedirectRefusal:
    def test_handler_returns_none(self):
        # redirect_request returning None ⇒ urllib does not follow the redirect.
        handler = _NoRedirectHandler()
        assert handler.redirect_request(None, None, 302, "Found", {}, "http://evil/") is None

    def test_request_validates_before_opening(self, settings, monkeypatch):
        settings.DEBUG = False
        opened = {"called": False}
        monkeypatch.setattr(client_mod._opener, "open", lambda *a, **k: opened.update(called=True))
        with pytest.raises(FederationClientError):
            client_mod._request("GET", "https://127.0.0.1/x")
        assert opened["called"] is False
