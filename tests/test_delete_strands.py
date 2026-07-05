"""DELETE-STRANDS: deleting a Need/Offer that has an active (proposed/accepted)
Match must be blocked with 409. Without the guard the cascade destroys the Match
(Match.need is CASCADE) or nulls it (Match.offer is SET_NULL), stranding the
counterpart in 'matched' forever with no reset path and no notification."""

import pytest
from django.test import Client
from django.urls import reverse

from apps.needs.models import Need
from apps.offers.models import Offer

from .conftest import (
    CategoryFactory,
    CommunityFactory,
    MatchFactory,
    MemberFactory,
    NeedFactory,
    OfferFactory,
)


def _client(member):
    c = Client()
    c.force_login(member.user)
    return c


@pytest.mark.django_db
def test_deleting_need_with_accepted_match_is_blocked():
    community = CommunityFactory()
    cat = CategoryFactory(community=community)
    requester = MemberFactory(community=community)
    offerer = MemberFactory(community=community)
    need = NeedFactory(community=community, requester=requester, category=cat, status="matched")
    offer = OfferFactory(community=community, offerer=offerer, category=cat, status="matched")
    match = MatchFactory(need=need, offer=offer, proposed_by=offerer, status="accepted")

    resp = _client(requester).post(reverse("need-delete", kwargs={"slug": community.slug, "pk": need.id}))

    assert resp.status_code == 409
    assert Need.objects.filter(pk=need.id).exists()  # not deleted
    offer.refresh_from_db()
    assert offer.status == "matched"  # counterpart not stranded — match still intact
    match.refresh_from_db()
    assert match.status == "accepted"


@pytest.mark.django_db
def test_deleting_offer_with_accepted_match_is_blocked():
    community = CommunityFactory()
    cat = CategoryFactory(community=community)
    requester = MemberFactory(community=community)
    offerer = MemberFactory(community=community)
    need = NeedFactory(community=community, requester=requester, category=cat, status="matched")
    offer = OfferFactory(community=community, offerer=offerer, category=cat, status="matched")
    match = MatchFactory(need=need, offer=offer, proposed_by=offerer, status="accepted")

    resp = _client(offerer).post(reverse("offer-delete", kwargs={"slug": community.slug, "pk": offer.id}))

    assert resp.status_code == 409
    assert Offer.objects.filter(pk=offer.id).exists()
    need.refresh_from_db()
    assert need.status == "matched"  # counterpart not stranded
    match.refresh_from_db()
    assert match.status == "accepted"


@pytest.mark.django_db
def test_deleting_need_with_proposed_match_is_blocked():
    community = CommunityFactory()
    cat = CategoryFactory(community=community)
    requester = MemberFactory(community=community)
    offerer = MemberFactory(community=community)
    need = NeedFactory(community=community, requester=requester, category=cat, status="open")
    offer = OfferFactory(community=community, offerer=offerer, category=cat, status="active")
    MatchFactory(need=need, offer=offer, proposed_by=offerer, status="proposed")

    resp = _client(requester).post(reverse("need-delete", kwargs={"slug": community.slug, "pk": need.id}))

    assert resp.status_code == 409
    assert Need.objects.filter(pk=need.id).exists()


@pytest.mark.django_db
def test_deleting_need_without_active_match_still_works():
    community = CommunityFactory()
    cat = CategoryFactory(community=community)
    requester = MemberFactory(community=community)
    need = NeedFactory(community=community, requester=requester, category=cat, status="open")

    resp = _client(requester).post(reverse("need-delete", kwargs={"slug": community.slug, "pk": need.id}))

    assert resp.status_code in (204, 302)
    assert not Need.objects.filter(pk=need.id).exists()  # deleted


@pytest.mark.django_db
def test_deleting_need_with_only_terminal_match_still_works():
    """A cancelled/expired match must not block deletion — only active ones do."""
    community = CommunityFactory()
    cat = CategoryFactory(community=community)
    requester = MemberFactory(community=community)
    offerer = MemberFactory(community=community)
    need = NeedFactory(community=community, requester=requester, category=cat, status="open")
    offer = OfferFactory(community=community, offerer=offerer, category=cat, status="active")
    MatchFactory(need=need, offer=offer, proposed_by=offerer, status="cancelled")

    resp = _client(requester).post(reverse("need-delete", kwargs={"slug": community.slug, "pk": need.id}))

    assert resp.status_code in (204, 302)
    assert not Need.objects.filter(pk=need.id).exists()
