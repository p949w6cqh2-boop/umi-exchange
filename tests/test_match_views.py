"""
Authorization, race-condition, and self-match tests for the matches views.
These cover the protocol's consent/safety guarantees (Sections 8.2, 8.6, 8.7).
"""
import pytest
from django.test import Client
from django.urls import reverse

from apps.matches.models import Match

from .conftest import (
    CategoryFactory,
    CommunityFactory,
    MatchFactory,
    MemberFactory,
    NeedFactory,
    OfferFactory,
)


def _scenario(need_status="open", with_offer=True):
    """Build a coherent community with a need, an offer, and a proposed match."""
    community = CommunityFactory()
    category = CategoryFactory(community=community)
    requester = MemberFactory(community=community)
    offerer = MemberFactory(community=community)
    need = NeedFactory(community=community, requester=requester, category=category, status=need_status)
    offer = OfferFactory(community=community, offerer=offerer, category=category) if with_offer else None
    match = MatchFactory(
        need=need, offer=offer,
        proposed_by=(offerer if with_offer else MemberFactory(community=community)),
        status="proposed",
    )
    return community, need, offer, match, requester, offerer


def _client_for(member):
    client = Client()
    client.force_login(member.user)
    return client


def _update_url(community, match):
    return reverse("match-update", kwargs={"slug": community.slug, "pk": match.id})


def _propose_url(community):
    return reverse("match-propose", kwargs={"slug": community.slug})


@pytest.mark.django_db
class TestMatchUpdateAuthorization:
    def test_non_participant_cannot_update_match(self):
        """A random community member who is not a participant gets HTTP 403."""
        community, need, offer, match, requester, offerer = _scenario()
        outsider = MemberFactory(community=community)  # neither requester nor offerer

        client = _client_for(outsider)
        response = client.post(_update_url(community, match), {"status": "accepted"})

        assert response.status_code == 403
        match.refresh_from_db()
        assert match.status == "proposed"  # unchanged

    def test_requester_can_accept(self):
        community, need, offer, match, requester, offerer = _scenario()
        client = _client_for(requester)
        response = client.post(_update_url(community, match), {"status": "accepted"})

        assert response.status_code == 302  # success redirect
        match.refresh_from_db()
        assert match.status == "accepted"

    def test_offerer_can_accept(self):
        community, need, offer, match, requester, offerer = _scenario()
        client = _client_for(offerer)
        response = client.post(_update_url(community, match), {"status": "accepted"})

        assert response.status_code == 302
        match.refresh_from_db()
        assert match.status == "accepted"

    def test_coordinator_can_update(self):
        community, need, offer, match, requester, offerer = _scenario()
        coordinator = MemberFactory(community=community, role="coordinator")
        client = _client_for(coordinator)
        response = client.post(_update_url(community, match), {"status": "accepted"})

        assert response.status_code == 302
        match.refresh_from_db()
        assert match.status == "accepted"


@pytest.mark.django_db
class TestMatchAcceptRace:
    def test_second_accept_on_same_need_gets_409(self):
        """Two matches on one need: once one is accepted the need is locked,
        so a second accept must fail with 409 Conflict (Section 8.7)."""
        community, need, offer, match1, requester, offerer = _scenario()
        # A competing proposal on the same need.
        offerer2 = MemberFactory(community=community)
        offer2 = OfferFactory(community=community, offerer=offerer2, category=offer.category)
        match2 = MatchFactory(need=need, offer=offer2, proposed_by=offerer2, status="proposed")

        client = _client_for(requester)
        first = client.post(_update_url(community, match1), {"status": "accepted"})
        assert first.status_code == 302
        match1.refresh_from_db()
        assert match1.status == "accepted"

        second = client.post(_update_url(community, match2), {"status": "accepted"})
        assert second.status_code == 409
        match2.refresh_from_db()
        assert match2.status == "proposed"  # rejected


@pytest.mark.django_db
class TestSelfMatchPrevention:
    def test_cannot_propose_on_own_need(self):
        """The requester proposing on their own need is rejected (Section 8.6)."""
        community = CommunityFactory()
        category = CategoryFactory(community=community)
        requester = MemberFactory(community=community)
        need = NeedFactory(community=community, requester=requester, category=category, status="open")
        offer = OfferFactory(community=community, offerer=requester, category=category)

        client = _client_for(requester)
        response = client.post(_propose_url(community), {"need_id": str(need.id), "offer_id": str(offer.id)})

        assert response.status_code == 400
        assert Match.objects.filter(need=need).count() == 0

    def test_cannot_match_offer_owned_by_requester(self):
        """An offer owned by the need's requester cannot be matched to it."""
        community = CommunityFactory()
        category = CategoryFactory(community=community)
        requester = MemberFactory(community=community)
        proposer = MemberFactory(community=community)
        need = NeedFactory(community=community, requester=requester, category=category, status="open")
        # Offer belongs to the requester, but a different member proposes it.
        offer = OfferFactory(community=community, offerer=requester, category=category)

        client = _client_for(proposer)
        response = client.post(_propose_url(community), {"need_id": str(need.id), "offer_id": str(offer.id)})

        assert response.status_code == 400
        assert Match.objects.filter(need=need).count() == 0


@pytest.mark.django_db
class TestOfferLessMatch:
    def test_propose_offer_less_match_succeeds(self):
        """A direct-volunteer proposal with no offer creates a match (no 500).

        The server-rendered flow uses POST-redirect-GET, so success is a 302
        redirect to the match detail rather than a 201.
        """
        community = CommunityFactory()
        category = CategoryFactory(community=community)
        requester = MemberFactory(community=community)
        volunteer = MemberFactory(community=community)
        need = NeedFactory(community=community, requester=requester, category=category, status="open")

        client = _client_for(volunteer)
        response = client.post(_propose_url(community), {"need_id": str(need.id)})

        assert response.status_code == 302
        match = Match.objects.get(need=need)
        assert match.offer is None
        assert match.proposed_by == volunteer

    def test_accept_offer_less_match_does_not_500(self):
        """A direct-volunteer match (no Offer) can be accepted without error."""
        community, need, _offer, match, requester, _offerer = _scenario(with_offer=False)
        assert match.offer is None

        client = _client_for(requester)
        response = client.post(_update_url(community, match), {"status": "accepted"})

        assert response.status_code == 302
        match.refresh_from_db()
        assert match.status == "accepted"
