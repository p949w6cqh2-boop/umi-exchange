"""The suggested-offers panel on an ask must not tell a neighbour that nobody is offering.

On your own ask the panel lists other neighbours' offers in the category. On someone else's ask it
lists only YOUR offers there, each with Propose Match (apps/needs/views.py). Both cases carried one
heading, "Neighbours already offering", and one empty line, "No offers in this category yet." So a
neighbour with no offer of their own, looking at someone else's ask, read that nobody was offering
while another neighbour's offer sat on the board (found filming B-roll, 2026-11-22: Bea on June's
"Groceries this week", Omar's "Grocery runs on Fridays" in plain view).
"""

import pytest
from django.test import Client
from django.urls import reverse

from .conftest import CategoryFactory, CommunityFactory, MemberFactory, NeedFactory, OfferFactory

pytestmark = pytest.mark.django_db


def _world():
    community = CommunityFactory()
    category = CategoryFactory(community=community, name="Groceries")
    asker = MemberFactory(community=community, is_active=True)
    helper = MemberFactory(community=community, is_active=True)
    bystander = MemberFactory(community=community, is_active=True)
    need = NeedFactory(
        community=community, requester=asker, category=category, status="open", title="Groceries this week"
    )
    OfferFactory(community=community, offerer=helper, category=category, title="Grocery runs on Fridays")
    return community, category, asker, helper, bystander, need


def _page(member, community, need):
    client = Client()
    client.force_login(member.user)
    resp = client.get(reverse("need-detail", kwargs={"slug": community.slug, "pk": need.pk}))
    assert resp.status_code == 200
    return resp.content.decode()


def test_the_asker_still_sees_neighbours_already_offering():
    community, _category, asker, _helper, _bystander, need = _world()

    body = _page(asker, community, need)

    assert "Neighbours already offering" in body
    assert "Grocery runs on Fridays" in body


def test_someone_else_sees_their_own_offers_headed_as_theirs():
    community, category, _asker, _helper, bystander, need = _world()
    OfferFactory(community=community, offerer=bystander, category=category, title="Extra bags from my store run")

    body = _page(bystander, community, need)

    assert "Your offers that could help" in body
    assert "Extra bags from my store run" in body
    assert "Neighbours already offering" not in body


def test_someone_with_no_offer_is_never_told_nobody_is_offering():
    community, _category, _asker, _helper, bystander, need = _world()

    body = _page(bystander, community, need)

    assert "No offers in this category yet." not in body
    assert "You have no offers in this category." in body
    assert "Neighbours already offering" not in body
