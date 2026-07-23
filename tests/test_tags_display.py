"""
Stage 3B — surfacing verified tag badges (read-only) on the feed, detail
pages, and the My Tags nav link.

Only *verified* tags badge on shared surfaces (the safety-critical decision:
self-reported authority claims must never read as endorsed). Visibility is
honoured — coordinators-only tags never leak to plain members.
"""

import pytest
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.tags.badges import verified_badges_for
from apps.tags.models import MemberTag, Tag

from .conftest import CategoryFactory, CommunityFactory, MemberFactory, NeedFactory, OfferFactory


@pytest.fixture
def community(db):
    return CommunityFactory()


@pytest.fixture
def poster(community):
    return MemberFactory(community=community, role="member", display_name="Pat Poster")


@pytest.fixture
def viewer(community):
    return MemberFactory(community=community, role="member", display_name="Val Viewer")


@pytest.fixture
def coordinator(community):
    return MemberFactory(community=community, role="coordinator", display_name="Cora Coord")


def verify_tag(member, slug, status="verified"):
    tag = Tag.objects.get(community=member.community, slug=slug)
    return MemberTag.objects.create(member=member, tag=tag, status=status)


def login(member):
    c = Client()
    c.force_login(member.user)
    return c


# ──────────────────────────────────────────────────────────────────────
# verified_badges_for() helper
# ──────────────────────────────────────────────────────────────────────
class TestVerifiedBadgesHelper:
    def test_returns_verified_tag(self, community, poster, viewer):
        verify_tag(poster, "svdp-member")  # coordinator_verified, public_when_verified
        result = verified_badges_for([poster.id], viewer)
        assert [mt.tag.slug for mt in result.get(poster.id, [])] == ["svdp-member"]

    def test_excludes_self_reported(self, community, poster, viewer):
        verify_tag(poster, "homeowner", status="self_claimed")
        result = verified_badges_for([poster.id], viewer)
        assert result.get(poster.id, []) == []

    def test_excludes_pending(self, community, poster, viewer):
        verify_tag(poster, "svdp-member", status="pending")
        result = verified_badges_for([poster.id], viewer)
        assert result.get(poster.id, []) == []

    def test_coordinators_only_tag_hidden_from_plain_member(self, community, poster, viewer):
        verify_tag(poster, "nurse")  # default_visibility coordinators_only, not public_when_verified
        result = verified_badges_for([poster.id], viewer)
        assert "nurse" not in [mt.tag.slug for mt in result.get(poster.id, [])]

    def test_coordinators_only_tag_visible_to_coordinator(self, community, poster, coordinator):
        verify_tag(poster, "nurse")
        result = verified_badges_for([poster.id], coordinator)
        assert "nurse" in [mt.tag.slug for mt in result.get(poster.id, [])]

    def test_batches_multiple_members_one_query(self, community, poster, viewer, django_assert_num_queries):
        other = MemberFactory(community=community, role="member", display_name="Otto")
        verify_tag(poster, "svdp-member")
        verify_tag(other, "priest")  # admin_verified, public_when_verified
        with django_assert_num_queries(1):
            result = verified_badges_for([poster.id, other.id], viewer)
        assert "svdp-member" in [mt.tag.slug for mt in result[poster.id]]
        assert "priest" in [mt.tag.slug for mt in result[other.id]]

    def test_empty_member_ids_returns_empty(self, community, viewer):
        assert verified_badges_for([], viewer) == {}


# ──────────────────────────────────────────────────────────────────────
# "My Tags" nav link
# ──────────────────────────────────────────────────────────────────────
class TestMyTagsNav:
    def test_link_shown_for_member_on_community_page(self, community, viewer):
        resp = login(viewer).get(reverse("community-feed", kwargs={"slug": community.slug}))
        assert resp.status_code == 200
        my_tags_url = reverse("tags:my-tags", kwargs={"slug": community.slug})
        assert my_tags_url.encode() in resp.content

    def test_link_absent_without_community_context(self, community, viewer):
        # The account-settings page has no community/member in context.
        resp = login(viewer).get(reverse("account-settings"))
        my_tags_url = reverse("tags:my-tags", kwargs={"slug": community.slug})
        assert my_tags_url.encode() not in resp.content


# ──────────────────────────────────────────────────────────────────────
# Feed card badges (verified only)
# ──────────────────────────────────────────────────────────────────────
class TestFeedBadges:
    def test_need_card_shows_verified_badge(self, community, poster, viewer):
        verify_tag(poster, "svdp-member")
        cat = CategoryFactory(community=community)
        NeedFactory(community=community, requester=poster, category=cat, title="Need a ride")
        resp = login(viewer).get(reverse("community-feed", kwargs={"slug": community.slug}))
        assert resp.status_code == 200
        assert b"SVdP Member" in resp.content

    def test_offer_card_shows_verified_badge(self, community, poster, viewer):
        verify_tag(poster, "svdp-member")
        cat = CategoryFactory(community=community)
        OfferFactory(community=community, offerer=poster, category=cat, title="Offering help")
        resp = login(viewer).get(reverse("community-feed", kwargs={"slug": community.slug}))
        assert resp.status_code == 200
        assert b"SVdP Member" in resp.content

    def test_feed_hides_self_reported(self, community, poster, viewer):
        verify_tag(poster, "homeowner", status="self_claimed")
        cat = CategoryFactory(community=community)
        NeedFactory(community=community, requester=poster, category=cat, title="Need a ride")
        resp = login(viewer).get(reverse("community-feed", kwargs={"slug": community.slug}))
        assert b"Homeowner" not in resp.content

    def test_feed_hides_coordinators_only_from_plain_member(self, community, poster, viewer):
        verify_tag(poster, "nurse")  # verified but coordinators-only
        cat = CategoryFactory(community=community)
        NeedFactory(community=community, requester=poster, category=cat, title="Need a ride")
        resp = login(viewer).get(reverse("community-feed", kwargs={"slug": community.slug}))
        assert b"Nurse" not in resp.content

    def test_feed_fetches_badges_in_one_query(self, community, viewer):
        cat = CategoryFactory(community=community)
        for i in range(3):
            m = MemberFactory(community=community, role="member", display_name=f"Poster{i}")
            verify_tag(m, "svdp-member")
            NeedFactory(community=community, requester=m, category=cat, title=f"Need {i}")
        c = login(viewer)
        with CaptureQueriesContext(connection) as cap:
            resp = c.get(reverse("community-feed", kwargs={"slug": community.slug}))
        assert resp.status_code == 200
        tag_queries = [q for q in cap.captured_queries if "tags_member_tag" in q["sql"]]
        assert len(tag_queries) == 1, f"expected 1 batched badge query, got {len(tag_queries)}"


# ──────────────────────────────────────────────────────────────────────
# Detail page badges (verified only)
# ──────────────────────────────────────────────────────────────────────
class TestDetailBadges:
    def test_need_detail_shows_verified_badge(self, community, poster, viewer):
        verify_tag(poster, "svdp-member")
        cat = CategoryFactory(community=community)
        need = NeedFactory(community=community, requester=poster, category=cat, title="Need a ride")
        resp = login(viewer).get(reverse("need-detail", kwargs={"slug": community.slug, "pk": need.id}))
        assert resp.status_code == 200
        assert b"SVdP Member" in resp.content

    def test_need_detail_hides_self_reported(self, community, poster, viewer):
        verify_tag(poster, "homeowner", status="self_claimed")
        cat = CategoryFactory(community=community)
        need = NeedFactory(community=community, requester=poster, category=cat, title="Need a ride")
        resp = login(viewer).get(reverse("need-detail", kwargs={"slug": community.slug, "pk": need.id}))
        assert b"Homeowner" not in resp.content

    def test_offer_detail_shows_verified_badge(self, community, poster, viewer):
        verify_tag(poster, "svdp-member")
        cat = CategoryFactory(community=community)
        offer = OfferFactory(community=community, offerer=poster, category=cat, title="Offering help")
        resp = login(viewer).get(reverse("offer-detail", kwargs={"slug": community.slug, "pk": offer.id}))
        assert resp.status_code == 200
        assert b"SVdP Member" in resp.content


class TestBadgeTerminalStates:
    """Revoked/removed tags must never wear another state's badge.

    The hub renders a member's own tags through tags/_badge.html; before the
    explicit branches below, a revoked tag fell into the {% else %} arm and
    was styled as an innocuous "Self-reported" pill.
    """

    def _render(self, status):
        from types import SimpleNamespace

        from django.template.loader import render_to_string

        return render_to_string("tags/_badge.html", {"mt": SimpleNamespace(status=status)})

    def test_revoked_badge_is_distinct(self):
        html = self._render("revoked")
        assert "Revoked" in html
        assert "Self-reported" not in html
        assert "emerald" not in html  # never styled like verified
        assert "Verified by" not in html

    def test_removed_badge_renders_nothing(self):
        assert self._render("removed").strip() == ""


class TestKeepAndExplainCopy:
    """Jasiah Williams's 2026-07-11 decision: tags and household stay — and the UI
    says plainly what each is for."""

    def test_my_tags_page_explains_tags(self, community, viewer):
        resp = login(viewer).get(reverse("tags:my-tags", kwargs={"slug": community.slug}))
        assert resp.status_code == 200
        assert b"coordinator confirmed" in resp.content
        assert b"only verified" in resp.content.lower()

    def test_household_pages_explain_households(self, community, viewer):
        client = login(viewer)
        create = client.get(reverse("household-create"))
        assert create.status_code == 200
        assert b"families, not individuals" in create.content
        join = client.get(reverse("household-join"))
        assert join.status_code == 200
        assert b"one household" in join.content
