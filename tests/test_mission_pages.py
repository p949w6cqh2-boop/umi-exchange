"""The public mission pages — story / beliefs / comparison — must render for
logged-out visitors, carry the real content, and NEVER expose the gated board."""

import pytest
from django.urls import reverse

from tests.conftest import CommunityFactory, MemberFactory, NeedFactory

pytestmark = pytest.mark.django_db

MISSION_PAGES = ["about", "beliefs", "why-umi"]


@pytest.mark.parametrize("name", MISSION_PAGES)
def test_mission_page_public_for_anonymous(client, name):
    resp = client.get(reverse(name))
    assert resp.status_code == 200  # no login redirect


def test_about_carries_founder_and_mission(client):
    body = client.get(reverse("about")).content.decode()
    assert "Jasiah" in body
    assert "Founder" in body
    assert "iron sharpens iron" in body.lower()  # reciprocity, in his words
    assert "Acts" in body  # Acts 4:32 — the blueprint
    assert "being established as a 501(c)(3)" in body


@pytest.mark.parametrize("name", MISSION_PAGES)
def test_no_granted_501c3_claim_while_filing_pending(client, name):
    """The 501(c)(3) filing is not complete (Jasiah, 2026-07-10) — no page may
    claim the status as granted, only 'being established as'. Covers the shared
    footer too, since it renders on every page."""
    body = client.get(reverse(name)).content.decode()
    assert "501(c)(3) non-profit" not in body  # granted-status phrasing
    assert "as a 501(c)(3):" not in body  # beliefs' old framing


def test_beliefs_grounds_in_cst(client):
    body = client.get(reverse("beliefs")).content.decode()
    assert "Integral human development" in body or "whole person" in body
    assert "Subsidiarity" in body or "subsidiarity" in body
    assert "structures of sin" in body
    # advocacy framed as non-partisan formation
    assert "no candidates" in body.lower() or "faithful citizenship" in body.lower()


def test_beliefs_tags_vision_as_not_yet_built(client):
    body = client.get(reverse("beliefs")).content.decode()
    assert "not yet built" in body.lower() or "where we're going" in body.lower()


def test_why_umi_is_factual_and_fair(client):
    body = client.get(reverse("why-umi")).content.decode()
    assert "CarePortal" in body
    assert "Global Orphan Project" in body  # the true attribution, stated plainly
    assert "Reciprocal aid network" in body or "reciprocal aid" in body.lower()
    # answers the two questions the founder asked
    assert "Why choose us" in body
    assert "help more" in body.lower()


def test_pages_reachable_from_footer_nav(client):
    body = client.get(reverse("landing")).content.decode()
    for name in MISSION_PAGES:
        assert reverse(name) in body  # header/footer links render on every page


# ── the gate is untouched: the real board stays private ──


def test_board_still_gated_for_anonymous(client):
    community = CommunityFactory()
    NeedFactory(community=community, requester=MemberFactory(community=community), title="Private ask")
    resp = client.get(f"/c/{community.slug}/")
    assert resp.status_code == 302
    assert "/auth/login/" in resp.url


def test_mission_pages_do_not_leak_real_needs(client):
    community = CommunityFactory()
    NeedFactory(community=community, requester=MemberFactory(community=community), title="Confidential need XYZ")
    for name in MISSION_PAGES:
        assert "Confidential need XYZ" not in client.get(reverse(name)).content.decode()
