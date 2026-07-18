"""Coordinator removal of a member must be durable, reversible, and complete.

Before this: "hide a member" set Member.is_active=False and nothing else — the
removed member's needs/offers stayed on the board, their in-flight matches
lingered, and they could walk back in by re-entering the still-valid join code.
These tests pin the hardened behavior: removal ripples to their content and
matches, refuses a silent rejoin, and a coordinator can reinstate.
"""

import pytest
from django.test import Client
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.moderation.models import Flag
from apps.moderation.services import reinstate_member, remove_member
from tests.conftest import (
    CategoryFactory,
    CommunityFactory,
    MatchFactory,
    MemberFactory,
    NeedFactory,
    OfferFactory,
)

pytestmark = pytest.mark.django_db


def _login(member):
    c = Client()
    c.force_login(member.user)
    return c


@pytest.fixture
def world():
    community = CommunityFactory()
    coordinator = MemberFactory(community=community, role="coordinator", display_name="Anne Coordinator")
    poster = MemberFactory(community=community, role="member", display_name="Paul Poster")
    return community, coordinator, poster


class TestRemoveMemberRipple:
    def test_removal_sets_state_and_records_who(self, world):
        community, coordinator, poster = world
        remove_member(poster, by=coordinator)
        poster.refresh_from_db()
        assert poster.is_active is False
        assert poster.removed_at is not None
        assert poster.removed_by == coordinator

    def test_removal_takes_their_open_content_off_the_board(self, world):
        community, coordinator, poster = world
        cat = CategoryFactory(community=community)
        need = NeedFactory(community=community, requester=poster, category=cat, status="open")
        offer = OfferFactory(community=community, offerer=poster, category=cat, status="active")
        remove_member(poster, by=coordinator)
        need.refresh_from_db()
        offer.refresh_from_db()
        assert need.moderation_hidden is True
        assert offer.moderation_hidden is True

    def test_removal_cancels_their_in_flight_matches(self, world):
        community, coordinator, poster = world
        cat = CategoryFactory(community=community)
        need = NeedFactory(community=community, requester=poster, category=cat, status="open")
        helper = MemberFactory(community=community, role="member")
        offer = OfferFactory(community=community, offerer=helper, category=cat, status="active")
        match = MatchFactory(need=need, offer=offer, proposed_by=helper, status="proposed")
        remove_member(poster, by=coordinator)
        match.refresh_from_db()
        assert match.status == "cancelled"

    def test_removal_is_audited_pii_free(self, world):
        community, coordinator, poster = world
        remove_member(poster, by=coordinator)
        row = AuditLog.objects.filter(action="member.removed", resource_id=poster.pk).first()
        assert row is not None
        assert "Paul" not in str(row.details or {})


class TestRemovalDurability:
    def test_removed_member_cannot_rejoin_on_the_same_code(self, world):
        community, coordinator, poster = world
        remove_member(poster, by=coordinator)
        # They re-enter the community's still-valid join code.
        resp = _login(poster).post(reverse("community-join"), {"join_code": community.join_code})
        poster.refresh_from_db()
        # Still out: the archived row is NOT silently reactivated.
        assert poster.is_active is False
        assert poster.removed_at is not None
        # And they don't land inside the community feed.
        assert resp.status_code in (200, 302)
        if resp.status_code == 302:
            assert f"/c/{community.slug}/" not in resp.headers.get("Location", "")

    def test_voluntary_leaver_can_still_rejoin(self, world):
        community, coordinator, poster = world
        leaver = MemberFactory(community=community, role="member")
        # Voluntary leave: is_active False, removed_at stays NULL.
        leaver.is_active = False
        leaver.save(update_fields=["is_active"])
        _login(leaver).post(reverse("community-join"), {"join_code": community.join_code})
        leaver.refresh_from_db()
        assert leaver.is_active is True


class TestQueueHideUsesHardenedRemoval:
    def test_hide_member_from_queue_is_durable_and_ripples(self, world):
        community, coordinator, poster = world
        cat = CategoryFactory(community=community)
        need = NeedFactory(community=community, requester=poster, category=cat, status="open")
        reporter = MemberFactory(community=community, role="member")
        _login(reporter).post(
            reverse("moderation:flag", kwargs={"slug": community.slug}),
            {"target_type": "member", "target_id": poster.pk, "reason": "unsafe", "detail": ""},
        )
        flag = Flag.objects.get(target_type="member")
        _login(coordinator).post(
            reverse("moderation:resolve", kwargs={"slug": community.slug, "pk": flag.pk}), {"action": "hide"}
        )
        poster.refresh_from_db()
        need.refresh_from_db()
        assert poster.is_active is False
        assert poster.removed_at is not None
        assert poster.removed_by == coordinator
        assert need.moderation_hidden is True


class TestReinstate:
    def test_reinstate_restores_access_and_content(self, world):
        community, coordinator, poster = world
        cat = CategoryFactory(community=community)
        need = NeedFactory(community=community, requester=poster, category=cat, status="open")
        remove_member(poster, by=coordinator)
        need.refresh_from_db()
        assert need.moderation_hidden is True  # hidden by removal

        reinstate_member(poster, by=coordinator)
        poster.refresh_from_db()
        need.refresh_from_db()
        assert poster.is_active is True
        assert poster.removed_at is None
        assert poster.removed_by is None
        assert need.moderation_hidden is False  # content back on the board
        assert AuditLog.objects.filter(action="member.reinstated", resource_id=poster.pk).exists()

    def test_reinstated_member_can_rejoin_again(self, world):
        community, coordinator, poster = world
        remove_member(poster, by=coordinator)
        reinstate_member(poster, by=coordinator)
        # Already active after reinstate; a rejoin POST is a harmless no-op.
        poster.refresh_from_db()
        assert poster.is_active is True and poster.removed_at is None


class TestReinstateView:
    def test_coordinator_can_reinstate_from_the_queue(self, world):
        community, coordinator, poster = world
        remove_member(poster, by=coordinator)
        resp = _login(coordinator).post(
            reverse("moderation:reinstate", kwargs={"slug": community.slug}), {"member_id": str(poster.pk)}
        )
        assert resp.status_code in (302, 200)
        poster.refresh_from_db()
        assert poster.is_active is True and poster.removed_at is None

    def test_plain_member_cannot_reinstate(self, world):
        community, coordinator, poster = world
        remove_member(poster, by=coordinator)
        other = MemberFactory(community=community, role="member")
        resp = _login(other).post(
            reverse("moderation:reinstate", kwargs={"slug": community.slug}), {"member_id": str(poster.pk)}
        )
        assert resp.status_code == 403
        poster.refresh_from_db()
        assert poster.is_active is False

    def test_removed_members_show_in_the_queue(self, world):
        community, coordinator, poster = world
        remove_member(poster, by=coordinator)
        resp = _login(coordinator).get(reverse("moderation:queue", kwargs={"slug": community.slug}))
        assert resp.status_code == 200
        assert b"Paul Poster" in resp.content  # coordinator can see who to reinstate
