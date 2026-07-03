"""FEDERATION_ENABLED=False (the default) ⇒ federation surface is absent."""

import pytest

pytestmark = pytest.mark.django_db


class TestFlagOff:
    def test_wellknown_absent_on_default_urlconf(self, client, settings):
        assert settings.FEDERATION_ENABLED is False  # default must be OFF
        assert client.get("/.well-known/umi-federation").status_code == 404

    def test_handshake_absent_on_default_urlconf(self, client):
        assert client.post("/federation/v1/handshake", data="{}", content_type="application/json").status_code == 404

    @pytest.mark.urls("apps.federation.tests.urls_enabled")
    def test_view_guard_404s_even_if_routed(self, client, settings):
        settings.FEDERATION_ENABLED = False
        assert client.post("/federation/v1/handshake", data="{}", content_type="application/json").status_code == 404
