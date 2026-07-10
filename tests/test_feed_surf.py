"""Surfable Lake 1: infinite scroll (the paginator finally rendered), type
tabs, and the week pulse-strip — the feed you can actually stay on."""

import pytest
from django.urls import reverse

from tests.conftest import CommunityFactory, MemberFactory, NeedFactory, OfferFactory, UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def surf_world():
    community = CommunityFactory()
    user = UserFactory()
    member = MemberFactory(user=user, community=community)
    other = MemberFactory(community=community)
    for i in range(25):  # > paginate_by=20, so page 2 exists
        NeedFactory(community=community, requester=other, title=f"surf ask {i}")
    OfferFactory(community=community, offerer=other, title="surf offer one")
    return type("W", (), {"community": community, "user": user, "member": member, "other": other})


def _feed(surf_world):
    return reverse("community-feed", kwargs={"slug": surf_world.community.slug})


def test_feed_renders_infinite_scroll_sentinel(client, surf_world):
    client.force_login(surf_world.user)
    body = client.get(_feed(surf_world)).content.decode()
    assert 'hx-trigger="revealed"' in body  # the surf sentinel
    assert "page=2" in body


def test_feed_page_two_loads_more_cards(client, surf_world):
    client.force_login(surf_world.user)
    page2 = client.get(_feed(surf_world), {"page": 2}, HTTP_HX_REQUEST="true").content.decode()
    assert "surf ask" in page2 or "surf offer" in page2
    # last page carries no further sentinel
    assert 'hx-trigger="revealed"' not in page2 or "page=3" not in page2


def test_feed_type_tabs_filter(client, surf_world):
    client.force_login(surf_world.user)
    asks = client.get(_feed(surf_world), {"type": "need"}, HTTP_HX_REQUEST="true").content.decode()
    assert "surf ask" in asks and "surf offer one" not in asks
    offers = client.get(_feed(surf_world), {"type": "offer"}, HTTP_HX_REQUEST="true").content.decode()
    assert "surf offer one" in offers and "surf ask" not in offers


def test_feed_shows_week_pulse_strip(client, surf_world):
    from apps.matches.models import Match

    need = NeedFactory(community=surf_world.community, requester=surf_world.other, title="strip ask")
    match = Match.objects.create(need=need, proposed_by=surf_world.member)
    match.transition_to("accepted")
    client.force_login(surf_world.user)
    body = client.get(_feed(surf_world)).content.decode()
    assert "this week" in body.lower()
    assert "answered" in body.lower()


def test_mission_pages_carry_chapter_nav(client):
    body = client.get(reverse("about")).content.decode()
    assert 'aria-current="page"' in body  # active chapter marked
    for name in ("beliefs", "why-umi", "technology"):
        assert reverse(name) in body
    # book flow: about points onward to beliefs
    assert "Next" in body
