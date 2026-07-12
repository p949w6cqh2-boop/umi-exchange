"""P1 — report/flag + coordinator moderation queue.

A member can say "this isn't right"; a coordinator the community already
trusts reviews it; hiding is reversible; everything is audited; the reporter
is never named to the crowd and never told more than "reviewed"."""

import pytest
from django.test import Client
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.hub import selectors
from apps.moderation.models import Flag
from apps.notifications.models import Notification
from tests.conftest import CategoryFactory, CommunityFactory, MemberFactory, NeedFactory, OfferFactory

pytestmark = pytest.mark.django_db


def _login(member):
    c = Client()
    c.force_login(member.user)
    return c


@pytest.fixture
def world():
    community = CommunityFactory()
    coordinator = MemberFactory(community=community, role="coordinator", display_name="Anne Coordinator")
    reporter = MemberFactory(community=community, role="member", display_name="Rita Reporter")
    poster = MemberFactory(community=community, role="member", display_name="Paul Poster")
    need = NeedFactory(
        community=community, requester=poster, category=CategoryFactory(community=community), title="Help with rent"
    )
    return community, coordinator, reporter, poster, need


def _flag(client, community, target_type, target_id, reason="fake", detail=""):
    return client.post(
        reverse("moderation:flag", kwargs={"slug": community.slug}),
        {"target_type": target_type, "target_id": target_id, "reason": reason, "detail": detail},
    )


class TestFlagCreate:
    def test_member_can_flag_a_need(self, world):
        community, coordinator, reporter, poster, need = world
        resp = _flag(_login(reporter), community, "need", need.pk, detail="Never seen this person")
        assert resp.status_code == 302
        flag = Flag.objects.get()
        assert flag.reporter == reporter and flag.status == "open"
        assert AuditLog.objects.filter(action="flag.created", resource_id=flag.pk).exists()

    def test_coordinators_notified_reporter_never_named(self, world):
        community, coordinator, reporter, poster, need = world
        _flag(_login(reporter), community, "need", need.pk)
        note = Notification.objects.get(recipient=coordinator.user, type="flag_received")
        assert "Rita" not in note.title and "Rita" not in note.body

    def test_second_report_of_same_target_stays_single(self, world):
        community, coordinator, reporter, poster, need = world
        client = _login(reporter)
        _flag(client, community, "need", need.pk)
        resp = _flag(client, community, "need", need.pk)
        assert resp.status_code == 302
        assert Flag.objects.count() == 1

    def test_foreign_member_cannot_flag_here(self, world):
        community, coordinator, reporter, poster, need = world
        outsider = MemberFactory(community=CommunityFactory(), role="member")
        assert _flag(_login(outsider), community, "need", need.pk).status_code == 404

    def test_cross_community_target_is_unreachable(self, world):
        community, coordinator, reporter, poster, need = world
        elsewhere = CommunityFactory()
        foreign_need = NeedFactory(
            community=elsewhere,
            requester=MemberFactory(community=elsewhere),
            category=CategoryFactory(community=elsewhere),
        )
        # target in ANOTHER community, posted to ours → 404, no flag row
        resp = _flag(_login(reporter), community, "need", foreign_need.pk)
        assert resp.status_code == 404
        assert Flag.objects.count() == 0


class TestQueueAccess:
    def test_coordinator_sees_open_flags(self, world):
        community, coordinator, reporter, poster, need = world
        _flag(_login(reporter), community, "need", need.pk)
        resp = _login(coordinator).get(reverse("moderation:queue", kwargs={"slug": community.slug}))
        assert resp.status_code == 200
        assert b"Help with rent" in resp.content

    def test_plain_member_is_refused(self, world):
        community, coordinator, reporter, poster, need = world
        resp = _login(reporter).get(reverse("moderation:queue", kwargs={"slug": community.slug}))
        assert resp.status_code == 403

    def test_foreign_coordinator_is_refused(self, world):
        community, coordinator, reporter, poster, need = world
        foreign = MemberFactory(community=CommunityFactory(), role="coordinator")
        resp = _login(foreign).get(reverse("moderation:queue", kwargs={"slug": community.slug}))
        assert resp.status_code == 404


class TestResolve:
    def _open_flag(self, world):
        community, coordinator, reporter, poster, need = world
        _flag(_login(reporter), community, "need", need.pk)
        return Flag.objects.get()

    def _resolve(self, coordinator, community, flag, action):
        return _login(coordinator).post(
            reverse("moderation:resolve", kwargs={"slug": community.slug, "pk": flag.pk}), {"action": action}
        )

    def test_hide_removes_from_every_member_surface(self, world):
        community, coordinator, reporter, poster, need = world
        flag = self._open_flag(world)
        assert self._resolve(coordinator, community, flag, "hide").status_code == 302
        need.refresh_from_db()
        assert need.moderation_hidden is True
        # feed
        feed = _login(reporter).get(reverse("community-feed", kwargs={"slug": community.slug}))
        assert b"Help with rent" not in feed.content
        # hub pulse + spotlight
        kinds = [e["title"] for e in selectors.pulse_events(community)]
        assert "Help with rent" not in kinds
        assert selectors.spotlight_need(reporter) is None or selectors.spotlight_need(reporter).pk != need.pk
        # detail gated
        assert (
            _login(reporter).get(reverse("need-detail", kwargs={"slug": community.slug, "pk": need.pk})).status_code
            == 404
        )
        assert (
            _login(coordinator).get(reverse("need-detail", kwargs={"slug": community.slug, "pk": need.pk})).status_code
            == 200
        )
        # audits + closure + reporter notified
        assert AuditLog.objects.filter(action="content.hidden", resource_id=need.pk).exists()
        flag.refresh_from_db()
        assert flag.status == "resolved" and flag.resolution == "hide"
        assert Notification.objects.filter(recipient=reporter.user, type="flag_reviewed").exists()

    def test_keep_resolves_without_touching_content(self, world):
        community, coordinator, reporter, poster, need = world
        flag = self._open_flag(world)
        self._resolve(coordinator, community, flag, "keep")
        need.refresh_from_db()
        flag.refresh_from_db()
        assert need.moderation_hidden is False
        assert flag.status == "resolved" and flag.resolution == "keep"

    def test_dismiss_closes_quietly(self, world):
        community, coordinator, reporter, poster, need = world
        flag = self._open_flag(world)
        self._resolve(coordinator, community, flag, "dismiss")
        flag.refresh_from_db()
        assert flag.status == "dismissed"

    def test_hiding_a_plain_member_deactivates_them(self, world):
        community, coordinator, reporter, poster, need = world
        _flag(_login(reporter), community, "member", poster.pk)
        flag = Flag.objects.get(target_type="member")
        self._resolve(coordinator, community, flag, "hide")
        poster.refresh_from_db()
        assert poster.is_active is False

    def test_a_coordinator_cannot_be_hidden_from_the_queue(self, world):
        community, coordinator, reporter, poster, need = world
        second_coord = MemberFactory(community=community, role="coordinator")
        _flag(_login(reporter), community, "member", second_coord.pk)
        flag = Flag.objects.get(target_type="member")
        resp = self._resolve(coordinator, community, flag, "hide")
        assert resp.status_code == 403
        second_coord.refresh_from_db()
        assert second_coord.is_active is True

    def test_plain_member_cannot_resolve(self, world):
        community, coordinator, reporter, poster, need = world
        flag = self._open_flag(world)
        resp = self._resolve(reporter, community, flag, "hide")
        assert resp.status_code == 403


class TestHiddenOffer:
    def test_offer_hide_works_the_same(self, world):
        community, coordinator, reporter, poster, need = world
        offer = OfferFactory(
            community=community, offerer=poster, category=CategoryFactory(community=community), title="Free tutoring"
        )
        _flag(_login(reporter), community, "offer", offer.pk)
        flag = Flag.objects.get()
        _login(coordinator).post(
            reverse("moderation:resolve", kwargs={"slug": community.slug, "pk": flag.pk}), {"action": "hide"}
        )
        offer.refresh_from_db()
        assert offer.moderation_hidden is True
        feed = _login(reporter).get(reverse("community-feed", kwargs={"slug": community.slug}))
        assert b"Free tutoring" not in feed.content
