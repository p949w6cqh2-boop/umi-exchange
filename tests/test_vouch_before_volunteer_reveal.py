"""A helper this community has not vouched for does not receive the asker's contact, offer or not.

docs/ethics-and-safety.md, "The stranger at the door": a volunteer who proposes on a need without a
standing offer received the asker's contact on accept, "a person the board has not vouched for".
Closed by docs/specs/vouch-before-volunteer-reveal.md, and widened to every helper by the founder's
"17a" (2026-11-22), because posting an offer first was one step around an offer-less-only rule.
"Vouched" means a vouch made in the asker's own community (a Vouch row), or a role there trusted to
vouch for others (Member.can_vouch).

Not User.verified_via == "coordinator": any coordinator can vouch for any account on the site, and
anyone signed in can create a community and be its admin, so that mark can be minted in a community
nobody else is in. A held reveal is a bare name, so the coordinators are told on accept and one of
them makes the introduction.
"""

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.communities.models import Vouch
from apps.notifications.models import Notification

from .conftest import (
    CategoryFactory,
    CommunityFactory,
    MatchFactory,
    MemberFactory,
    NeedFactory,
    OfferFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db

PHONE = "555-0199"


def _world(volunteer_via="email", volunteer_role="member", status="accepted", contact_pref="any"):
    community = CommunityFactory()
    category = CategoryFactory(community=community, name="Home Repair")
    asker = MemberFactory(community=community, is_active=True, user__phone=PHONE)
    volunteer = MemberFactory(
        community=community, is_active=True, role=volunteer_role, user__verified_via=volunteer_via
    )
    coordinator = MemberFactory(community=community, is_active=True, role="coordinator")
    need = NeedFactory(
        community=community, requester=asker, category=category, status="open", contact_pref=contact_pref
    )
    match = MatchFactory(need=need, offer=None, proposed_by=volunteer, status=status, helper_yes_at=timezone.now())
    return community, asker, volunteer, coordinator, match


def _vouch(voucher, community, username):
    client = Client()
    client.force_login(voucher.user)
    return client.post(reverse("member-vouch", kwargs={"slug": community.slug}), {"username": username})


# --- who receives the asker's contact ---------------------------------------------------------


def test_an_email_verified_volunteer_does_not_get_the_askers_contact():
    _c, _asker, volunteer, _coord, match = _world(volunteer_via="email")

    info = match.get_contact_info_for(volunteer)

    assert "phone" not in info and "email" not in info
    assert info.get("vouch_pending") is True


def test_a_backfill_volunteer_does_not_get_the_askers_contact():
    _c, _asker, volunteer, _coord, match = _world(volunteer_via="backfill")

    info = match.get_contact_info_for(volunteer)

    assert "phone" not in info
    assert info.get("vouch_pending") is True


def test_a_site_wide_coordinator_mark_alone_does_not_release_the_contact():
    """verified_via == "coordinator" can be minted in a community nobody else is in."""
    _c, _asker, volunteer, _coord, match = _world(volunteer_via="coordinator")

    info = match.get_contact_info_for(volunteer)

    assert "phone" not in info
    assert info.get("vouch_pending") is True


def test_a_vouch_made_in_another_community_does_not_release_the_contact():
    _c, _asker, volunteer, _coord, match = _world()
    Vouch.objects.create(community=CommunityFactory(), user=volunteer.user)

    info = match.get_contact_info_for(volunteer)

    assert "phone" not in info
    assert info.get("vouch_pending") is True


def test_a_volunteer_vouched_for_here_gets_the_askers_contact():
    community, _asker, volunteer, coordinator, match = _world()
    Vouch.objects.create(community=community, user=volunteer.user, vouched_by=coordinator.user)

    info = match.get_contact_info_for(volunteer)

    assert info.get("phone") == PHONE
    assert "vouch_pending" not in info


def test_a_volunteer_trusted_to_vouch_here_gets_the_askers_contact():
    _c, _asker, volunteer, _coord, match = _world(volunteer_role="intake")

    info = match.get_contact_info_for(volunteer)

    assert info.get("phone") == PHONE


def test_nothing_is_marked_held_when_the_asker_shares_no_channel():
    """An asker who chose in-app shares nothing with anyone, so the box keeps its usual line."""
    _c, _asker, volunteer, _coord, match = _world(contact_pref="in_app")

    info = match.get_contact_info_for(volunteer)

    assert "vouch_pending" not in info


def test_an_asker_who_left_shows_as_left_not_held():
    _c, asker, volunteer, _coord, match = _world()
    asker.is_active = False
    asker.save(update_fields=["is_active"])

    info = match.get_contact_info_for(volunteer)

    assert info.get("left") is True
    assert "vouch_pending" not in info


def _offer_match():
    """A match made with an offer: the route the automated security review found around an
    offer-less-only rule (post an offer, propose it). Closed by the founder's 17a, 2026-11-22."""
    community = CommunityFactory()
    category = CategoryFactory(community=community, name="Home Repair")
    asker = MemberFactory(community=community, is_active=True, user__phone=PHONE)
    offerer = MemberFactory(community=community, is_active=True, user__verified_via="email")
    need = NeedFactory(community=community, requester=asker, category=category, status="open", contact_pref="any")
    offer = OfferFactory(community=community, offerer=offerer, category=category)
    match = MatchFactory(need=need, offer=offer, proposed_by=offerer, status="accepted")
    return community, offerer, match


def test_an_unvouched_offerer_does_not_get_the_askers_contact():
    """17a: every helper needs this community's vouch, offer or not."""
    _c, offerer, match = _offer_match()

    info = match.get_contact_info_for(offerer)

    assert "phone" not in info and "email" not in info
    assert info.get("vouch_pending") is True


def test_an_offerer_vouched_for_here_gets_the_askers_contact():
    community, offerer, match = _offer_match()
    Vouch.objects.create(community=community, user=offerer.user)

    info = match.get_contact_info_for(offerer)

    assert info.get("phone") == PHONE
    assert "vouch_pending" not in info


def test_the_askers_own_view_is_unchanged():
    _c, asker, _volunteer, _coord, match = _world(volunteer_via="email")

    info = match.get_contact_info_for(asker)

    assert "vouch_pending" not in info


# --- what people are told ---------------------------------------------------------------------


def test_coordinators_are_told_when_a_held_match_is_accepted():
    community, asker, _volunteer, coordinator, match = _world(volunteer_via="email", status="proposed")
    client = Client()
    client.force_login(asker.user)

    resp = client.post(reverse("match-update", kwargs={"slug": community.slug, "pk": match.id}), {"status": "accepted"})

    assert resp.status_code == 302
    match.refresh_from_db()
    assert match.status == "accepted"
    assert Notification.objects.filter(recipient=coordinator.user).exists()


def test_the_page_tells_the_volunteer_a_coordinator_can_put_them_in_touch():
    community, _asker, volunteer, _coord, match = _world(volunteer_via="email")
    client = Client()
    client.force_login(volunteer.user)

    body = client.get(reverse("match-detail", kwargs={"slug": community.slug, "pk": match.id})).content.decode()

    assert "A coordinator can put you in touch" in body
    assert "They prefer to arrange things through the community" not in body
    assert PHONE not in body


# --- the vouch that releases it ---------------------------------------------------------------


def test_vouching_for_an_email_verified_neighbour_is_recorded_here():
    """The vouch used to stop at "already verified", which would have held their reveals for good."""
    community, _asker, volunteer, coordinator, match = _world(volunteer_via="email")

    resp = _vouch(coordinator, community, volunteer.user.username)

    assert resp.status_code == 302
    assert Vouch.objects.filter(community=community, user=volunteer.user, vouched_by=coordinator.user).exists()
    volunteer.user.refresh_from_db()
    assert volunteer.user.verified_via == "email"  # how they were first verified is kept
    assert AuditLog.objects.filter(action="user.vouched", details__previously="email").exists()
    assert match.get_contact_info_for(volunteer).get("phone") == PHONE


def test_a_second_vouch_here_changes_nothing():
    community, _asker, volunteer, coordinator, _match = _world()

    _vouch(coordinator, community, volunteer.user.username)
    _vouch(coordinator, community, volunteer.user.username)

    assert Vouch.objects.filter(community=community, user=volunteer.user).count() == 1
    assert AuditLog.objects.filter(action="user.vouched").count() == 1


def test_vouching_for_an_unverified_neighbour_still_verifies_them():
    community = CommunityFactory()
    coordinator = MemberFactory(community=community, is_active=True, role="coordinator")
    newcomer = UserFactory(verified_at=None, verified_via="")

    _vouch(coordinator, community, newcomer.username)

    newcomer.refresh_from_db()
    assert newcomer.verified_via == "coordinator"
    assert Vouch.objects.filter(community=community, user=newcomer).exists()
