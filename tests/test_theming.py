"""Per-community theming: presets, custom overrides, and the settings picker."""
import pytest
from django.urls import reverse

from apps.communities.themes import THEME_DEFAULT, THEMES, resolve_theme

from .conftest import CommunityFactory, MemberFactory


def test_none_community_is_default():
    assert resolve_theme(None)["primary"] == THEMES[THEME_DEFAULT]["primary"]


def test_unknown_key_falls_back_to_default():
    class C:
        settings = {"theme": "does-not-exist"}

    assert resolve_theme(C())["primary"] == THEMES[THEME_DEFAULT]["primary"]


@pytest.mark.django_db
class TestThemeResolution:
    def test_preset_applies(self):
        c = CommunityFactory()
        c.settings = {"theme": "kinfolk"}
        c.save()
        assert resolve_theme(c)["primary"] == THEMES["kinfolk"]["primary"]

    def test_custom_overrides_preset(self):
        c = CommunityFactory()
        c.settings = {"theme": "kinfolk", "theme_custom": {"primary": "#123456"}}
        c.save()
        t = resolve_theme(c)
        assert t["primary"] == "#123456"  # custom wins
        assert t["accent"] == THEMES["kinfolk"]["accent"]  # rest still from the preset


@pytest.mark.django_db
class TestThemePickerView:
    def test_admin_can_set_theme_and_custom_color(self, client):
        admin = MemberFactory(role="admin")
        community = admin.community
        client.force_login(admin.user)
        url = reverse("community-settings", kwargs={"slug": community.slug})

        resp = client.post(url, {"action": "set_theme", "theme": "ocean",
                                 "custom_primary": "#aabbcc", "custom_accent": ""})
        assert resp.status_code == 302
        community.refresh_from_db()
        assert community.settings["theme"] == "ocean"
        assert community.settings["theme_custom"]["primary"] == "#aabbcc"

    def test_invalid_hex_is_ignored(self, client):
        admin = MemberFactory(role="admin")
        community = admin.community
        client.force_login(admin.user)
        url = reverse("community-settings", kwargs={"slug": community.slug})

        client.post(url, {"action": "set_theme", "theme": "sankofa", "custom_primary": "not-a-hex"})
        community.refresh_from_db()
        assert community.settings["theme"] == "sankofa"
        assert "theme_custom" not in community.settings  # garbage rejected
