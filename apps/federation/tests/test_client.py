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

    def test_debug_allows_loopback_literal(self, settings):
        # Literal IP, no DNS: the old `http://localhost:8000/x` form was
        # resolver-dependent — CI runners whose localhost resolves to ::1 or an
        # IPv4-mapped form flaked it. The DEBUG loopback relaxation itself is
        # what this pins; hostname classification is pinned below with
        # getaddrinfo mocked.
        settings.DEBUG = True
        _validate_public_url("http://127.0.0.1:8000/x")  # no raise

    def test_debug_still_blocks_link_local_metadata(self, settings):
        # DEBUG relaxes loopback for the local rehearsal but must NOT reopen the
        # cloud-metadata sink (169.254.169.254).
        settings.DEBUG = True
        with pytest.raises(FederationClientError):
            _validate_public_url("https://169.254.169.254/latest/meta-data/")


def _pin_resolver(monkeypatch, *ips):
    """Pin getaddrinfo's answer — classification tests must never touch DNS."""

    def fake_getaddrinfo(host, port, *args, **kwargs):
        return [
            (
                client_mod.socket.AF_INET6 if ":" in ip else client_mod.socket.AF_INET,
                client_mod.socket.SOCK_STREAM,
                client_mod.socket.IPPROTO_TCP,
                "",
                (ip, port, 0, 0) if ":" in ip else (ip, port),
            )
            for ip in ips
        ]

    monkeypatch.setattr(client_mod.socket, "getaddrinfo", fake_getaddrinfo)


class TestAddressClassification:
    """Every classification branch pinned with getaddrinfo mocked. Real resolvers
    disagree about localhost (::1, ::ffff:127.0.0.1, plain 127.0.0.1), and Python
    3.12/3.13 disagree about how those forms classify (on 3.12, ::1 is ALSO
    is_reserved; on 3.13, ::ffff:127.0.0.1 is is_loopback) — so the validator's
    behavior is pinned per address, per DEBUG state, DNS-free."""

    def test_ipv6_loopback_allowed_under_debug(self, settings, monkeypatch):
        settings.DEBUG = True
        _pin_resolver(monkeypatch, "::1")
        _validate_public_url("http://peer.test:8000/x")  # no raise

    def test_ipv6_loopback_blocked_outside_debug(self, settings, monkeypatch):
        settings.DEBUG = False
        _pin_resolver(monkeypatch, "::1")
        with pytest.raises(FederationClientError):
            _validate_public_url("https://peer.test/x")

    def test_ipv4_mapped_loopback_blocked_even_under_debug(self, settings, monkeypatch):
        # The rehearsal uses literal 127.0.0.1 (arrives as plain IPv4). A resolver
        # handing back ::ffff:127.0.0.1 for a peer NAME is a rebind smell — never
        # accepted, DEBUG or not.
        settings.DEBUG = True
        _pin_resolver(monkeypatch, "::ffff:127.0.0.1")
        with pytest.raises(FederationClientError):
            _validate_public_url("http://peer.test:8000/x")

    def test_ipv4_mapped_loopback_blocked_outside_debug(self, settings, monkeypatch):
        settings.DEBUG = False
        _pin_resolver(monkeypatch, "::ffff:127.0.0.1")
        with pytest.raises(FederationClientError):
            _validate_public_url("https://peer.test/x")

    def test_hostname_resolving_to_metadata_blocked_under_debug(self, settings, monkeypatch):
        settings.DEBUG = True
        _pin_resolver(monkeypatch, "169.254.169.254")
        with pytest.raises(FederationClientError):
            _validate_public_url("http://peer.test/x")

    def test_ipv4_mapped_metadata_blocked_under_debug(self, settings, monkeypatch):
        settings.DEBUG = True
        _pin_resolver(monkeypatch, "::ffff:169.254.169.254")
        with pytest.raises(FederationClientError):
            _validate_public_url("http://peer.test/x")

    def test_public_address_allowed(self, settings, monkeypatch):
        settings.DEBUG = False
        _pin_resolver(monkeypatch, "8.8.8.8")
        _validate_public_url("https://peer.test/x")  # no raise


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
