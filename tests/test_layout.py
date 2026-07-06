"""Community Hub layout pass — structural / accessibility guards (scan-first editorial).

Aesthetics are verified visually; these lock the structural invariants so the redesign
doesn't regress: single H1, a <main> landmark, the one obvious primary action, and the
landing inheriting the themed chrome (no hardcoded-gray header override)."""

from pathlib import Path

import pytest
from django.urls import reverse

from .conftest import MemberFactory

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.django_db
class TestLandingStructure:
    def test_landing_ok_single_h1_main_and_primary_cta(self, client):
        resp = client.get(reverse("landing"))
        assert resp.status_code == 200
        html = resp.content.decode()
        assert html.count("<h1") == 1, "landing should have exactly one H1 (the masthead)"
        assert "<main" in html, "landing needs a <main> landmark"
        assert "umi-masthead" in html, "landing H1 should use the editorial masthead"
        assert reverse("community-join") in html, "the one obvious primary action (Join) must be present"

    def test_landing_inherits_themed_chrome(self):
        txt = (REPO_ROOT / "templates" / "pages" / "landing.html").read_text()
        assert "{% block header %}" not in txt, "landing must inherit the themed base header, not override it"
        import re as _re

        # Solid white chrome is banned; translucent white tints (bg-white/15)
        # inside themed components follow the theme and are fine.
        assert not _re.search(r"bg-white(?!/)", txt), "no hardcoded solid-white chrome on the landing"


@pytest.mark.django_db
class TestFeedStructure:
    def test_feed_has_masthead_and_primary_cta(self, client):
        admin = MemberFactory(role="admin")
        community = admin.community
        client.force_login(admin.user)
        resp = client.get(reverse("community-feed", kwargs={"slug": community.slug}))
        assert resp.status_code == 200
        html = resp.content.decode()
        assert html.count("<h1") == 1, "feed should have exactly one H1 ('The board')"
        assert "umi-display" in html, "feed masthead should use the editorial display heading"
        post_ask = reverse("need-create", kwargs={"slug": community.slug})
        assert post_ask in html, "primary 'Post an ask' CTA must be present"
