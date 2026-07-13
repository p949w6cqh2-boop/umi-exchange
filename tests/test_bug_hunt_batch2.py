"""Batch-2 regression (communities): theming CSS-injection render-boundary
validation, and set_theme open-redirect hardening."""

from types import SimpleNamespace

import pytest
from django.urls import reverse

from apps.communities.themes import resolve_theme

from .conftest import MemberFactory


def test_resolve_theme_rejects_css_injection_in_custom_value():
    hostile = SimpleNamespace(settings={"theme": "parish", "theme_custom": {"primary": "red;}html{display:none}"}})
    # The value is interpolated raw into a <style> block; a non-hex value must not
    # reach the CSS var. A strict #RRGGBB still applies.
    assert resolve_theme(hostile)["primary"] != "red;}html{display:none}"
    ok = SimpleNamespace(settings={"theme": "parish", "theme_custom": {"primary": "#123ABC"}})
    assert resolve_theme(ok)["primary"] == "#123ABC"


@pytest.mark.django_db
def test_set_theme_rejects_offsite_next_redirect(client):
    admin = MemberFactory(role="admin")
    community = admin.community
    client.force_login(admin.user)
    resp = client.post(
        reverse("community-settings", kwargs={"slug": community.slug}),
        {"action": "set_theme", "theme": "ocean", "next": "/\\evil.com"},  # backslash bypass
    )
    assert resp.status_code in (302, 303)
    assert "evil.com" not in resp["Location"]  # normalized //evil.com must be rejected
