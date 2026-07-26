"""
Dashboard triage correctness (bug-hunt batch 9, #23).

The coordinator's "Waiting asks (7 days or more, no match yet)" list annotated
Count('matches') with no status predicate, so cancelled/expired/unfulfilled Match
rows counted like live ones. transition_to reopens the need to 'open' but never
deletes the dead Match row — so the ask most likely to be abandoned (a helper
tried and withdrew) was permanently invisible to the one list built to catch it.
"""

from datetime import timedelta

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.needs.models import Need
from tests.conftest import (
    CategoryFactory,
    CommunityFactory,
    MatchFactory,
    MemberFactory,
    NeedFactory,
    OfferFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def triage_world():
    community = CommunityFactory()
    category = CategoryFactory(community=community)
    coordinator = MemberFactory(community=community, role="coordinator")
    requester = MemberFactory(community=community)
    helper = MemberFactory(community=community)
    return community, category, coordinator, requester, helper


def _aged_open_need(community, category, requester, days=8, **over):
    need = NeedFactory(community=community, category=category, requester=requester, status="open", **over)
    Need.objects.filter(pk=need.pk).update(created_at=timezone.now() - timedelta(days=days))
    return need


def _stale_pks(coordinator, community):
    client = Client()
    client.force_login(coordinator.user)
    resp = client.get(reverse("community-dashboard", args=[community.slug]))
    assert resp.status_code == 200
    return [n.pk for n in resp.context["stale_needs"]]


def test_stale_needs_includes_an_ask_whose_only_match_was_cancelled(triage_world):
    community, category, coordinator, requester, helper = triage_world
    need = _aged_open_need(community, category, requester)
    offer = OfferFactory(community=community, category=category, offerer=helper)
    MatchFactory(need=need, offer=offer, proposed_by=helper, status="cancelled")

    assert need.pk in _stale_pks(coordinator, community), (
        "a helper tried and withdrew — this is the ask the triage list exists for"
    )


def test_stale_needs_still_includes_an_ask_with_no_matches_at_all(triage_world):
    community, category, coordinator, requester, helper = triage_world
    need = _aged_open_need(community, category, requester)

    assert need.pk in _stale_pks(coordinator, community)


def test_stale_needs_excludes_an_ask_with_a_live_proposal(triage_world):
    community, category, coordinator, requester, helper = triage_world
    need = _aged_open_need(community, category, requester)
    offer = OfferFactory(community=community, category=category, offerer=helper)
    MatchFactory(need=need, offer=offer, proposed_by=helper, status="proposed")

    assert need.pk not in _stale_pks(coordinator, community), "someone is already on it — not waiting"


def test_stale_needs_excludes_a_fresh_ask(triage_world):
    community, category, coordinator, requester, helper = triage_world
    need = _aged_open_need(community, category, requester, days=2)

    assert need.pk not in _stale_pks(coordinator, community)
