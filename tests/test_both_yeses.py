"""Contact opens only after both people have said yes (the founder's call, 2026-10-06).

Until now one yes was enough: the asker, the helper, or a coordinator alone could accept a match
and open both people's contact details, while the front page promised "only after both sides say
yes". Now:

- a helper who proposes their own offer, or volunteers directly, has said yes by proposing;
- when a coordinator brokers a match, each person still says yes, in either order;
- a coordinator can never say yes for them (spec §4.1: coordinators must not consent on a member's
  behalf);
- until both have said yes the match stays proposed and nothing is revealed (§8.2).
"""

import pytest
from django.test import Client
from django.urls import reverse

from apps.matches.models import Match
from apps.notifications.models import Notification
from tests.conftest import CategoryFactory, CommunityFactory, MatchFactory, MemberFactory, NeedFactory, OfferFactory

pytestmark = pytest.mark.django_db


def _client(member):
    c = Client()
    c.force_login(member.user)
    return c


def _say_yes(member, match):
    url = reverse("match-update", args=[match.need.community.slug, match.id])
    return _client(member).post(url, {"status": "accepted"})


def _parish():
    community = CommunityFactory()
    category = CategoryFactory(community=community)
    asker = MemberFactory(community=community)
    helper = MemberFactory(community=community)
    need = NeedFactory(community=community, requester=asker, category=category)
    return community, category, asker, helper, need


def _brokered():
    community, category, asker, helper, need = _parish()
    coordinator = MemberFactory(community=community, role="coordinator")
    offer = OfferFactory(community=community, offerer=helper, category=category)
    match = MatchFactory(need=need, offer=offer, proposed_by=coordinator, status="proposed")
    return match, asker, helper, coordinator


def test_a_brokered_match_waits_for_the_second_yes():
    match, asker, helper, _ = _brokered()

    _say_yes(asker, match)
    match.refresh_from_db()
    assert match.status == "proposed"
    assert match.asker_yes_at is not None
    assert match.get_contact_info_for(asker) is None, "one yes must not open contact"

    _say_yes(helper, match)
    match.refresh_from_db()
    assert match.status == "accepted"
    assert match.get_contact_info_for(asker) is not None


def test_the_helper_can_say_yes_first():
    match, asker, helper, _ = _brokered()

    _say_yes(helper, match)
    match.refresh_from_db()
    assert match.status == "proposed"
    assert match.helper_yes_at is not None

    _say_yes(asker, match)
    match.refresh_from_db()
    assert match.status == "accepted"


def test_a_coordinator_cannot_say_yes_for_them():
    match, _, _, coordinator = _brokered()

    resp = _say_yes(coordinator, match)
    assert resp.status_code == 403
    match.refresh_from_db()
    assert match.status == "proposed"
    assert match.asker_yes_at is None and match.helper_yes_at is None


def test_a_helpers_own_proposal_is_their_yes():
    community, category, asker, helper, need = _parish()
    offer = OfferFactory(community=community, offerer=helper, category=category)
    match = MatchFactory(need=need, offer=offer, proposed_by=helper, status="proposed")

    _say_yes(asker, match)
    match.refresh_from_db()
    assert match.status == "accepted"


def test_a_direct_volunteer_has_said_yes_by_volunteering():
    community, _, asker, volunteer, need = _parish()
    match = MatchFactory(need=need, offer=None, proposed_by=volunteer, status="proposed")

    _say_yes(asker, match)
    match.refresh_from_db()
    assert match.status == "accepted"


def test_saying_yes_twice_changes_nothing():
    match, asker, _, _ = _brokered()

    _say_yes(asker, match)
    first = Match.objects.get(pk=match.pk).asker_yes_at
    _say_yes(asker, match)
    match.refresh_from_db()
    assert match.status == "proposed"
    assert match.asker_yes_at == first


def test_the_other_person_hears_about_the_first_yes():
    match, asker, helper, _ = _brokered()

    _say_yes(asker, match)
    note = Notification.objects.filter(recipient=helper.user, link__contains=str(match.id)).order_by("-created_at")
    assert note.exists()
    assert "said yes" in note.first().title


def test_the_match_page_says_who_it_is_waiting_for():
    match, asker, helper, _ = _brokered()

    _say_yes(asker, match)
    body = _client(asker).get(reverse("match-detail", args=[match.need.community.slug, match.id])).content.decode()
    assert "You said yes" in body
    assert helper.display_name in body
    assert "Accept match" not in body, "a person who has said yes is not asked again"
