"""Phase 2 "Member's Day" — the logged-in journey must look, not read:
threshold scene at join/create, hub crown, tokened notices, exchange ceremony.

Scenes are asserted via their unique grain-filter ids (g-*) because the
Parish Linocut header comments are {% comment %} blocks and never render."""

import pytest
from django.urls import reverse

from tests.conftest import (
    CommunityFactory,
    MemberFactory,
    NeedFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def homeless_client(client):
    """Logged-in user who belongs to no community yet — the threshold audience."""
    user = UserFactory()
    client.force_login(user)
    return client


@pytest.fixture
def member(db):
    return MemberFactory(user=UserFactory(), community=CommunityFactory())


@pytest.fixture
def member_client(client, member):
    client.force_login(member.user)
    return client


class TestHubCrown:
    def test_hub_masthead_carries_well_wash(self, member_client, member):
        body = member_client.get(reverse("hub:community", kwargs={"slug": member.community.slug})).content.decode()
        assert 'id="g-well"' in body

    def test_hub_empty_pulse_shows_vignette_not_bare_text(self, member_client, member):
        # A fresh member IS a pulse event (member_joined) — backdate the join
        # past the pulse window so the empty branch actually renders.
        from datetime import timedelta

        from django.utils import timezone

        type(member).objects.filter(pk=member.pk).update(joined_at=timezone.now() - timedelta(days=90))
        body = member_client.get(reverse("hub:pulse", kwargs={"slug": member.community.slug})).content.decode()
        assert "umi-vignette" in body  # quiet community → empty-state branch

    def test_hub_empty_spotlight_shows_vignette(self, member_client, member):
        body = member_client.get(reverse("hub:community", kwargs={"slug": member.community.slug})).content.decode()
        assert 'id="g-carry"' in body  # no open needs → spotlight empty state


class TestNotices:
    """Need/offer detail must sit on the Commons palette (no legacy grays)
    and read as a notice pinned to the board (medallion, like feed cards)."""

    @pytest.fixture
    def need_body(self, member_client, member):
        need = NeedFactory(community=member.community, requester=member)
        return member_client.get(reverse("need-detail", args=[member.community.slug, need.id])).content.decode()

    @pytest.fixture
    def offer_body(self, member_client, member):
        from tests.conftest import OfferFactory

        offer = OfferFactory(community=member.community, offerer=member)
        return member_client.get(reverse("offer-detail", args=[member.community.slug, offer.id])).content.decode()

    def test_need_detail_off_legacy_palette(self, need_body):
        assert "text-gray-" not in need_body
        assert "bg-gray-" not in need_body

    def test_need_detail_reads_as_board_notice(self, need_body):
        assert "umi-medallion" in need_body

    def test_offer_detail_off_legacy_palette(self, offer_body):
        assert "text-gray-" not in offer_body
        assert "bg-gray-" not in offer_body

    def test_offer_detail_reads_as_board_notice(self, offer_body):
        assert "umi-medallion" in offer_body


class TestExchangeCeremony:
    """The §8.2 contact reveal is the product's peak moment — it gets the
    exchange scene and ceremony copy, under the exact same gating."""

    def _world(self):
        from tests.conftest import CategoryFactory, MatchFactory, OfferFactory

        community = CommunityFactory()
        category = CategoryFactory(community=community)
        requester = MemberFactory(community=community)
        offerer = MemberFactory(community=community)
        need = NeedFactory(community=community, requester=requester, category=category, status="open")
        offer = OfferFactory(community=community, offerer=offerer, category=category)
        match = MatchFactory(need=need, offer=offer, proposed_by=offerer, status="proposed")
        return community, match, requester

    def _get(self, client, community, match, member):
        client.force_login(member.user)
        return client.get(reverse("match-detail", kwargs={"slug": community.slug, "pk": match.id})).content.decode()

    def test_accepted_match_shows_ceremony(self, client):
        community, match, requester = self._world()
        match.transition_to("accepted")
        body = self._get(client, community, match, requester)
        assert 'id="g-exch"' in body
        assert "connected" in body.lower()

    def test_proposed_match_shows_no_ceremony(self, client):
        community, match, requester = self._world()
        body = self._get(client, community, match, requester)
        assert 'id="g-exch"' not in body

    def test_match_page_off_legacy_palette(self, client):
        community, match, requester = self._world()
        match.transition_to("accepted")
        body = self._get(client, community, match, requester)
        assert "text-gray-" not in body
        assert "bg-gray-" not in body


class TestThreshold:
    def test_join_page_carries_threshold_scene(self, homeless_client):
        body = homeless_client.get(reverse("community-join")).content.decode()
        assert 'id="g-thresh"' in body

    def test_create_page_carries_threshold_scene(self, homeless_client):
        body = homeless_client.get(reverse("community-create")).content.decode()
        assert 'id="g-thresh"' in body
