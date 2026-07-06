"""Per-community theming: presets, custom overrides, and the settings picker."""

import re
from pathlib import Path

import pytest
from django.urls import reverse

from apps.communities.themes import THEME_DEFAULT, THEMES, resolve_theme

from .conftest import CommunityFactory, MemberFactory

REPO_ROOT = Path(__file__).resolve().parent.parent

# Design system v2 — "The Commons" (full redesign, 2026-07-06).
# One committed evergreen accent; bronze is functional offer-coding only.
DIRECTION_D_PRIMARY = "#275D4C"
DIRECTION_D_PRIMARY_HOVER = "#1C4739"
GOLD_ACCENT = "#9C7A3C"


def _luminance(hex_color):
    """WCAG relative luminance of a #rrggbb color."""
    h = hex_color.lstrip("#")
    chans = [int(h[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in chans]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _contrast(a, b):
    la, lb = _luminance(a), _luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _base_html_default(var):
    """Extract the |default fallback hex for a --umi-* var injected in base.html."""
    txt = (REPO_ROOT / "templates" / "base.html").read_text()
    m = re.search(rf'--umi-{var}:\s*\{{\{{[^}}]*default:"(#[0-9A-Fa-f]{{6}})"', txt)
    return m.group(1).lower() if m else None


def _input_css_root(var):
    """Extract the :root fallback hex for a --umi-* var in input.css."""
    txt = (REPO_ROOT / "static" / "css" / "input.css").read_text()
    m = re.search(rf"--umi-{var}:\s*(#[0-9A-Fa-f]{{6}})", txt)
    return m.group(1).lower() if m else None


def _tailwind_parish(key):
    """Extract a parish.<key> static color hex from tailwind.config.js."""
    txt = (REPO_ROOT / "tailwind.config.js").read_text()
    m = re.search(rf'{key}:\s*"(#[0-9A-Fa-f]{{6}})"', txt)
    return m.group(1).lower() if m else None


def _tailwind_gray(step):
    """Extract gray.<step> from the overridden gray ramp in tailwind.config.js."""
    txt = (REPO_ROOT / "tailwind.config.js").read_text()
    block = re.search(r"gray:\s*\{(.*?)\}", txt, re.DOTALL)
    if not block:
        return None
    m = re.search(rf'\b{step}:\s*"(#[0-9A-Fa-f]{{6}})"', block.group(1))
    return m.group(1).lower() if m else None


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


class TestDirectionDPalette:
    """Design v2 canon: default theme is evergreen, bronze demoted to offer coding, AA-safe, sources in sync."""

    def test_default_theme_is_evergreen(self):
        t = resolve_theme(None)
        assert t["primary"].lower() == DIRECTION_D_PRIMARY.lower()
        assert t["primary_hover"].lower() == DIRECTION_D_PRIMARY_HOVER.lower()

    def test_default_theme_keeps_gold_accent(self):
        # bronze stays the functional offer accent (never decoration)
        assert resolve_theme(None)["accent"].lower() == GOLD_ACCENT.lower()

    @pytest.mark.django_db
    def test_per_community_override_still_wins(self):
        # theming-safe: a community's own primary still beats the evergreen default
        c = CommunityFactory()
        c.settings = {"theme_custom": {"primary": "#aa0000"}}
        c.save()
        assert resolve_theme(c)["primary"] == "#aa0000"

    def test_default_primary_passes_wcag_aa(self):
        t = resolve_theme(None)
        assert _contrast(t["primary"], t["bg"]) >= 4.5  # primary text/icon on bg
        assert _contrast("#FFFFFF", t["primary"]) >= 4.5  # white label on the button

    def test_css_fallbacks_match_canonical_theme(self):
        """Four-source-sync guard: base.html, input.css and tailwind.config must equal
        THEMES['parish']. Regression for the prep-feature finding — change only some
        sources and default community pages render the old color."""
        canon = THEMES[THEME_DEFAULT]
        primary, hover = canon["primary"].lower(), canon["primary_hover"].lower()

        assert _base_html_default("primary") == primary, "base.html --umi-primary default drifted"
        assert _base_html_default("primary-hover") == hover, "base.html --umi-primary-hover drifted"
        assert _base_html_default("need-accent") == primary, "base.html need-accent should follow primary"

        assert _input_css_root("primary") == primary, "input.css --umi-primary drifted"
        assert _input_css_root("primary-hover") == hover, "input.css --umi-primary-hover drifted"
        css_text = (REPO_ROOT / "static" / "css" / "input.css").read_text()
        assert _input_css_root("need-accent") == primary or "--umi-need-accent: var(--umi-primary)" in css_text, (
            "input.css need-accent should follow primary"
        )

        assert _tailwind_parish("green") == primary, "tailwind parish.green drifted"
        assert _tailwind_parish("greendark") == hover, "tailwind parish.greendark drifted"

    def test_no_static_parish_green_classes_remain(self):
        """Option b: templates use the var-backed `umi-primary` color, not the static
        `parish-green`/`parish-greendark` utilities — so these surfaces follow per-community
        theming (a `rose`/`ocean` community no longer shows the parish color here)."""
        offenders = []
        for p in (REPO_ROOT / "templates").rglob("*.html"):
            for i, line in enumerate(p.read_text().splitlines(), 1):
                if "parish-green" in line:
                    offenders.append(f"{p.relative_to(REPO_ROOT)}:{i}")
        assert not offenders, "static parish-green classes remain:\n  " + "\n  ".join(offenders)


class TestWarmNeutralRamp:
    """Stage A: Tailwind's cool gray scale is overridden with a warm parish ramp, so the
    ~500 gray-* usages across 53 templates warm app-wide with no per-template edits."""

    def test_gray_ramp_is_warmed(self):
        assert _tailwind_gray("900") == "#2c2a29", "gray.900 should be warm ink, not TW #111827"
        assert _tailwind_gray("600") == "#6b6358", "gray.600 should be warm muted, not TW #4B5563"
        assert _tailwind_gray("200") == "#e6ded5", "gray.200 should be warm border, not TW #E5E7EB"
        assert _tailwind_gray("50") == "#faf7f1", "gray.50 should be warm light, not TW #F9FAFB"

    def test_warm_ink_passes_aa_on_stone(self):
        assert _contrast("#1F1C18", "#F6F4EE") >= 4.5  # espresso ink on stone paper
        assert _contrast("#6F6759", "#F6F4EE") >= 4.5  # warm muted text still readable


@pytest.mark.django_db
class TestThemePickerView:
    def test_admin_can_set_theme_and_custom_color(self, client):
        admin = MemberFactory(role="admin")
        community = admin.community
        client.force_login(admin.user)
        url = reverse("community-settings", kwargs={"slug": community.slug})

        resp = client.post(
            url, {"action": "set_theme", "theme": "ocean", "custom_primary": "#aabbcc", "custom_accent": ""}
        )
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
