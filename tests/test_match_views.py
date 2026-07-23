"""
Authorization, race-condition, and self-match tests for the matches views.
These cover the protocol's consent/safety guarantees (Sections 8.2, 8.6, 8.7).
"""

import pytest
from django.test import Client
from django.urls import reverse

from apps.audit.models import AuditLog
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
        need=need,
        offer=offer,
        proposed_by=(offerer if with_offer else MemberFactory(community=community)),
        status="proposed",
    )
    return community, need, offer, match, requester, offerer


def _client_for(member):
    client = Client()
    client.force_login(member.user)
    return client


@pytest.mark.django_db
def test_accept_does_not_double_commit_one_offer():
    """§8.7 for the OFFER: an active offer accepted against one need must not be
    acceptable against a second need — the accept guard checks the offer's
    availability, not only the need's."""
    community = CommunityFactory()
    category = CategoryFactory(community=community)
    requester_a = MemberFactory(community=community)
    requester_b = MemberFactory(community=community)
    offerer = MemberFactory(community=community)
    need_a = NeedFactory(community=community, requester=requester_a, category=category, status="open")
    need_b = NeedFactory(community=community, requester=requester_b, category=category, status="open")
    offer = OfferFactory(community=community, offerer=offerer, category=category)  # status "active"
    match_a = MatchFactory(need=need_a, offer=offer, proposed_by=offerer, status="proposed")
    match_b = MatchFactory(need=need_b, offer=offer, proposed_by=offerer, status="proposed")

    r1 = _client_for(requester_a).post(_update_url(community, match_a), {"status": "accepted"})
    assert r1.status_code in (200, 302)
    offer.refresh_from_db()
    assert offer.status == "matched"

    # The same offer must not be committable to a second need.
    r2 = _client_for(requester_b).post(_update_url(community, match_b), {"status": "accepted"})
    assert r2.status_code == 409
    match_b.refresh_from_db()
    assert match_b.status == "proposed"


def _update_url(community, match):
    return reverse("match-update", kwargs={"slug": community.slug, "pk": match.id})


def _propose_url(community):
    return reverse("match-propose", kwargs={"slug": community.slug})


def _detail_url(community, match):
    return reverse("match-detail", kwargs={"slug": community.slug, "pk": match.id})


def _contact_reads(match):
    return AuditLog.objects.filter(action="read", resource_type="match_contact", resource_id=match.id)


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

    def test_plain_member_cannot_propose_offer_they_do_not_own(self):
        """H-2: a NON-coordinator third party may not bind someone else's offer
        to a match. A plain member who is neither the requester nor the offer's
        owner is rejected, and no Match row created. (Coordinators are the
        exception — see test_coordinator_can_broker_offer_they_do_not_own.)"""
        community = CommunityFactory()
        category = CategoryFactory(community=community)
        requester = MemberFactory(community=community)
        offerer = MemberFactory(community=community)
        proposer = MemberFactory(community=community)  # plain member, neither party
        need = NeedFactory(community=community, requester=requester, category=category, status="open")
        offer = OfferFactory(community=community, offerer=offerer, category=category)

        client = _client_for(proposer)
        response = client.post(_propose_url(community), {"need_id": str(need.id), "offer_id": str(offer.id)})

        assert response.status_code == 400
        assert Match.objects.filter(need=need).count() == 0

    def test_offerer_can_propose_their_own_offer(self):
        """Regression: the legitimate offer-bearing propose — the offerer
        offering their own offer against another member's need — still works."""
        community = CommunityFactory()
        category = CategoryFactory(community=community)
        requester = MemberFactory(community=community)
        offerer = MemberFactory(community=community)
        need = NeedFactory(community=community, requester=requester, category=category, status="open")
        offer = OfferFactory(community=community, offerer=offerer, category=category)

        client = _client_for(offerer)
        response = client.post(_propose_url(community), {"need_id": str(need.id), "offer_id": str(offer.id)})

        assert response.status_code == 302
        assert Match.objects.filter(need=need, offer=offer, proposed_by=offerer).count() == 1

    def test_coordinator_can_broker_offer_they_do_not_own(self):
        """Subsidiarity (Jasiah Williams's call): a coordinator MAY broker a match with a
        member's offer they don't own — and the offerer is signaled so they keep
        the right to accept or decline (the consent that makes brokering
        *assist*, not *substitution*)."""
        from apps.notifications.models import Notification

        community = CommunityFactory()
        category = CategoryFactory(community=community)
        requester = MemberFactory(community=community)
        offerer = MemberFactory(community=community)
        coordinator = MemberFactory(community=community, role="coordinator")
        need = NeedFactory(community=community, requester=requester, category=category, status="open")
        offer = OfferFactory(community=community, offerer=offerer, category=category)

        client = _client_for(coordinator)
        response = client.post(_propose_url(community), {"need_id": str(need.id), "offer_id": str(offer.id)})

        assert response.status_code == 302
        assert Match.objects.filter(need=need, offer=offer, proposed_by=coordinator).count() == 1
        # The offerer is signaled — the subsidiarity safeguard: they can decline.
        assert Notification.objects.filter(recipient=offerer.user, type="match_proposed").exists()


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


@pytest.mark.django_db
class TestContactReadAuditing:
    def test_revealing_contact_writes_audit_entry(self):
        """Viewing a match where contact is disclosed records a read in the audit log."""
        community, need, offer, match, requester, offerer = _scenario()
        _client_for(requester).post(_update_url(community, match), {"status": "accepted"})
        assert _contact_reads(match).count() == 0  # nothing read yet

        response = _client_for(offerer).get(_detail_url(community, match))
        assert response.status_code == 200
        entries = _contact_reads(match)
        assert entries.count() == 1
        assert entries.first().user == offerer.user

    def test_no_audit_when_contact_hidden(self):
        """Before acceptance contact is hidden, so viewing logs no read entry."""
        community, need, offer, match, requester, offerer = _scenario()  # still 'proposed'

        response = _client_for(offerer).get(_detail_url(community, match))
        assert response.status_code == 200
        assert _contact_reads(match).count() == 0


@pytest.mark.django_db
class TestMatchNotes:
    def test_note_is_persisted_on_status_change(self):
        community, need, offer, match, requester, offerer = _scenario()
        client = _client_for(requester)
        response = client.post(
            _update_url(community, match),
            {"status": "accepted", "notes": "Will drop by Saturday morning"},
        )
        assert response.status_code == 302
        match.refresh_from_db()
        assert match.status == "accepted"
        assert match.notes == "Will drop by Saturday morning"

    def test_blank_note_does_not_overwrite(self):
        community, need, offer, match, requester, offerer = _scenario()
        match.notes = "existing note"
        match.save(update_fields=["notes"])

        _client_for(requester).post(_update_url(community, match), {"status": "accepted"})
        match.refresh_from_db()
        assert match.notes == "existing note"
