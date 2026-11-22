"""A match that connects two neighbours with only a name must reach a coordinator.

Protocol §8.2 reveals contact after accept: a display name plus only the channels a member
opted into (Member.contact_dict). When the counterpart has no proven email, no phone, or chose
"in_app", the match page shows a bare name and says "A coordinator can pass a message along"
(templates/components/_contact_info_box.html). Until this fix nothing told any coordinator,
because the accept notification goes to the counterpart participant only, never the actor and
never a coordinator (apps/matches/views.py, the accept branch). The neighbour waited on a
coordinator who did not know they were needed, after a notice that said "Contact info has been
shared" when none had been.

Factory users carry a proven-email timestamp but an EMPTY address and no phone
(tests/conftest.py UserFactory), so the default world below IS the bare-name case.
"""

import pytest
from django.test import Client
from django.urls import reverse

from apps.notifications.models import Notification

from .conftest import (
    CategoryFactory,
    CommunityFactory,
    MatchFactory,
    MemberFactory,
    NeedFactory,
    OfferFactory,
)

pytestmark = pytest.mark.django_db


def _world(requester_email="", offerer_email="", offer_pref="in_app"):
    community = CommunityFactory()
    category = CategoryFactory(community=community)
    requester = MemberFactory(community=community, is_active=True, user__email=requester_email)
    offerer = MemberFactory(community=community, is_active=True, user__email=offerer_email)
    coordinator = MemberFactory(community=community, is_active=True, role="coordinator")
    need = NeedFactory(community=community, requester=requester, category=category, status="open")
    offer = OfferFactory(community=community, offerer=offerer, category=category, contact_pref=offer_pref)
    match = MatchFactory(need=need, offer=offer, proposed_by=offerer, status="proposed")
    return community, requester, offerer, coordinator, match


def _accept(community, actor, match):
    client = Client()
    client.force_login(actor.user)
    resp = client.post(
        reverse("match-update", kwargs={"slug": community.slug, "pk": match.id}),
        {"status": "accepted"},
    )
    assert resp.status_code == 302
    match.refresh_from_db()
    assert match.status == "accepted"


def test_accept_that_reveals_only_a_name_tells_the_coordinator():
    community, requester, _offerer, coordinator, match = _world()

    _accept(community, requester, match)

    told = Notification.objects.filter(recipient=coordinator.user)
    assert told.count() == 1
    assert str(match.id) in told.get().link


def test_accept_that_shares_real_contact_leaves_the_coordinator_alone():
    community, requester, _offerer, coordinator, match = _world(
        requester_email="asker@example.com", offerer_email="helper@example.com", offer_pref="any"
    )

    _accept(community, requester, match)

    assert not Notification.objects.filter(recipient=coordinator.user).exists()


def test_a_neighbour_given_only_a_name_is_not_told_contact_was_shared():
    # The requester has no email or phone, so the helper who is notified sees only a name.
    community, requester, offerer, _coordinator, match = _world(offerer_email="helper@example.com", offer_pref="any")

    _accept(community, requester, match)

    notice = Notification.objects.get(recipient=offerer.user)
    assert "Contact info has been shared" not in notice.body
    assert "coordinator" in notice.body.lower()


def test_a_neighbour_given_real_contact_still_hears_it_was_shared():
    community, requester, offerer, _coordinator, match = _world(
        requester_email="asker@example.com", offerer_email="helper@example.com", offer_pref="any"
    )

    _accept(community, requester, match)

    assert "Contact info has been shared" in Notification.objects.get(recipient=offerer.user).body


def test_a_coordinator_of_another_community_is_never_told():
    community, requester, _offerer, _coordinator, match = _world()
    elsewhere = MemberFactory(community=CommunityFactory(), is_active=True, role="coordinator")

    _accept(community, requester, match)

    assert not Notification.objects.filter(recipient=elsewhere.user).exists()


def test_a_coordinator_who_accepts_their_own_match_is_not_told_twice():
    # Small parishes: the coordinator is often the one asking. Never notify the actor.
    community = CommunityFactory()
    category = CategoryFactory(community=community)
    asking_coordinator = MemberFactory(community=community, is_active=True, role="coordinator")
    offerer = MemberFactory(community=community, is_active=True)
    need = NeedFactory(community=community, requester=asking_coordinator, category=category, status="open")
    offer = OfferFactory(community=community, offerer=offerer, category=category)
    match = MatchFactory(need=need, offer=offer, proposed_by=offerer, status="proposed")

    _accept(community, asking_coordinator, match)

    assert not Notification.objects.filter(recipient=asking_coordinator.user).exists()


def test_a_coordinator_who_has_left_is_not_told():
    community, requester, _offerer, coordinator, match = _world()
    coordinator.is_active = False
    coordinator.save(update_fields=["is_active"])

    _accept(community, requester, match)

    assert not Notification.objects.filter(recipient=coordinator.user).exists()
