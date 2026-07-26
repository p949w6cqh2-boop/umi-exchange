"""
Block/hidden leaks on the secondary read surfaces (bug-hunt batch 7, #16 #17).

A block promises two things: no future match, and "you won't see each other on
the board". The feed, the hub list and the detail get_object all honour it. Four
read surfaces did not:

#16 OfferDetailView.matching_needs and NeedDetailView.suggested_offers filtered
    on status alone — no moderation_hidden=False, no blocked_member_ids exclusion.
    A coordinator-hidden post, or a post by a neighbour the viewer blocked, was
    re-listed with its title and the poster's display_name, and the offer-side
    panel rendered a working Propose Match button on hidden content.

#17 pulse_events() took no viewer at all and emitted requester/offerer display
    names (and member_joined names); spotlight_need() excluded only the member's
    own needs. LOGIN_REDIRECT_URL is /hub/, so after Ada blocks Ben the very first
    screen she saw said "Ben put an ask on the board", with his ask, name and
    urgency in the Spotlight under an "I can help" button that then 404s.

Display-only leaks — click-through is gated elsewhere — but the promise the block
made is about seeing, not only about matching.
"""

import pytest
from django.urls import reverse

from apps.hub import selectors
from apps.moderation.models import Block
from tests.conftest import (
    CategoryFactory,
    CommunityFactory,
    MemberFactory,
    NeedFactory,
    OfferFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def neighbours():
    community = CommunityFactory()
    category = CategoryFactory(community=community)
    ada = MemberFactory(community=community, display_name="Ada")
    ben = MemberFactory(community=community, display_name="Ben")
    return community, category, ada, ben


def _block(community, blocker, blocked):
    return Block.objects.create(community=community, blocker=blocker, blocked=blocked, reason="")


def _client(member):
    from django.test import Client

    c = Client()
    c.force_login(member.user)
    return c


# ------------------------------------------------------------------------ #17
def test_pulse_hides_a_blocked_neighbours_ask(neighbours):
    community, category, ada, ben = neighbours
    NeedFactory(community=community, category=category, requester=ben, title="Ben needs a lift")
    _block(community, ada, ben)

    events = selectors.pulse_events(community, viewer=ada)

    assert "Ben needs a lift" not in [e["title"] for e in events]
    assert "Ben" not in [e["actor"] for e in events]


def test_pulse_hides_a_blocked_neighbours_offer(neighbours):
    community, category, ada, ben = neighbours
    OfferFactory(community=community, category=category, offerer=ben, title="Ben can drive")
    _block(community, ada, ben)

    events = selectors.pulse_events(community, viewer=ada)

    assert "Ben can drive" not in [e["title"] for e in events]


def test_pulse_hides_a_blocked_neighbour_joining(neighbours):
    """member_joined carries the display_name and nothing else — it is the name
    itself that must not appear."""
    community, category, ada, ben = neighbours
    _block(community, ada, ben)

    events = selectors.pulse_events(community, viewer=ada)

    joined = [e["title"] for e in events if e["kind"] == "member_joined"]
    assert "Ben" not in joined
    assert "Ada" in joined, "her own community's life is still visible"


def test_pulse_is_symmetric_for_the_blocked_neighbour(neighbours):
    """A block hides both ways — Ben must not see Ada either."""
    community, category, ada, ben = neighbours
    NeedFactory(community=community, category=category, requester=ada, title="Ada needs a hand")
    _block(community, ada, ben)

    events = selectors.pulse_events(community, viewer=ben)

    assert "Ada needs a hand" not in [e["title"] for e in events]


def test_pulse_still_shows_an_unblocked_neighbour(neighbours):
    """The guard must not empty the Pulse."""
    community, category, ada, ben = neighbours
    NeedFactory(community=community, category=category, requester=ben, title="Ben needs a lift")

    events = selectors.pulse_events(community, viewer=ada)

    assert "Ben needs a lift" in [e["title"] for e in events]


def test_spotlight_skips_a_blocked_neighbours_ask(neighbours):
    community, category, ada, ben = neighbours
    NeedFactory(community=community, category=category, requester=ben, title="Ben needs a lift")
    _block(community, ada, ben)

    assert selectors.spotlight_need(ada) is None


def test_spotlight_still_offers_an_unblocked_neighbours_ask(neighbours):
    community, category, ada, ben = neighbours
    need = NeedFactory(community=community, category=category, requester=ben, title="Ben needs a lift")

    assert selectors.spotlight_need(ada).pk == need.pk


# ------------------------------------------------------------------------ #16
def test_offer_detail_panel_hides_blocked_and_hidden_needs(neighbours):
    community, category, ada, ben = neighbours
    cara = MemberFactory(community=community, display_name="Cara")
    offer = OfferFactory(community=community, category=category, offerer=ada, title="Ada can drive")
    NeedFactory(community=community, category=category, requester=ben, title="Ben needs a lift")
    NeedFactory(
        community=community,
        category=category,
        requester=cara,
        title="Cara needs a hidden lift",
        moderation_hidden=True,
    )
    _block(community, ada, ben)

    body = _client(ada).get(reverse("offer-detail", args=[community.slug, offer.pk])).content.decode()

    assert "Ben needs a lift" not in body, "a blocked neighbour's ask must not be re-listed here"
    assert "Cara needs a hidden lift" not in body, "a coordinator-hidden ask must not be re-listed here"


def test_offer_detail_panel_still_lists_an_ordinary_need(neighbours):
    community, category, ada, ben = neighbours
    offer = OfferFactory(community=community, category=category, offerer=ada, title="Ada can drive")
    NeedFactory(community=community, category=category, requester=ben, title="Ben needs a lift")

    body = _client(ada).get(reverse("offer-detail", args=[community.slug, offer.pk])).content.decode()

    assert "Ben needs a lift" in body


def test_need_detail_panel_hides_blocked_and_hidden_offers(neighbours):
    community, category, ada, ben = neighbours
    cara = MemberFactory(community=community, display_name="Cara")
    need = NeedFactory(community=community, category=category, requester=ada, title="Ada needs a lift")
    OfferFactory(community=community, category=category, offerer=ben, title="Ben can drive")
    OfferFactory(
        community=community,
        category=category,
        offerer=cara,
        title="Cara can drive quietly",
        moderation_hidden=True,
    )
    _block(community, ada, ben)

    body = _client(ada).get(reverse("need-detail", args=[community.slug, need.pk])).content.decode()

    assert "Ben can drive" not in body, "a blocked neighbour's offer must not be suggested"
    assert "Cara can drive quietly" not in body, "a coordinator-hidden offer must not be suggested"


def test_need_detail_panel_hides_your_own_hidden_offer(neighbours):
    """Viewing someone else's ask, the panel lists YOUR offers to propose. One a
    coordinator has hidden must not be among them: propose already 404s on hidden
    content (apps/matches/views.py), so listing it is a dead button — and every
    other surface, including the offer's own detail page, hides it from you too."""
    community, category, ada, ben = neighbours
    need = NeedFactory(community=community, category=category, requester=ben, title="Ben needs a lift")
    OfferFactory(community=community, category=category, offerer=ada, title="Ada can drive", moderation_hidden=True)

    body = _client(ada).get(reverse("need-detail", args=[community.slug, need.pk])).content.decode()

    assert "Ada can drive" not in body


def test_need_detail_panel_still_suggests_your_own_visible_offer(neighbours):
    """The companion that matters most: offerer=member plus a new filter is
    exactly the shape that silently empties a panel with nothing to notice."""
    community, category, ada, ben = neighbours
    need = NeedFactory(community=community, category=category, requester=ben, title="Ben needs a lift")
    OfferFactory(community=community, category=category, offerer=ada, title="Ada can drive")

    body = _client(ada).get(reverse("need-detail", args=[community.slug, need.pk])).content.decode()

    assert "Ada can drive" in body


def test_need_detail_panel_still_suggests_an_ordinary_offer(neighbours):
    community, category, ada, ben = neighbours
    need = NeedFactory(community=community, category=category, requester=ada, title="Ada needs a lift")
    OfferFactory(community=community, category=category, offerer=ben, title="Ben can drive")

    body = _client(ada).get(reverse("need-detail", args=[community.slug, need.pk])).content.decode()

    assert "Ben can drive" in body
