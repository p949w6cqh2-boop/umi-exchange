"""
Report/flag + coordinator moderation queue (P1 slice).

Covers: flag submission (validation, self-flag guard, duplicate guard, rate
limit, cross-community isolation), the coordinator-only queue, resolve/hide
(safe-fail: need → closed, offer → withdrawn, never delete), dismiss, the
flag state machine, audit emission, and coordinator notifications.
"""

import pytest
from django.core.cache import cache
from django.test import Client
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.moderation.models import Flag
from apps.notifications.models import Notification

from .conftest import CommunityFactory, MemberFactory, NeedFactory, OfferFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear_ratelimit_cache():
    """Flag submission uses the cache-backed fixed-window limiter; clear it
    around every test so counters never bleed across tests."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def community(db):
    return CommunityFactory()


@pytest.fixture
def reporter(community):
    return MemberFactory(community=community, role="member", display_name="Alice")


@pytest.fixture
def poster(community):
    return MemberFactory(community=community, role="member", display_name="Bob")


@pytest.fixture
def coordinator(community):
    return MemberFactory(community=community, role="coordinator", display_name="Dave")


@pytest.fixture
def need(community, poster):
    return NeedFactory(community=community, requester=poster, category__community=community)


@pytest.fixture
def offer(community, poster):
    return OfferFactory(community=community, offerer=poster, category__community=community)


def _login(member):
    client = Client()
    client.force_login(member.user)
    return client


def _flag_url(community):
    return reverse("moderation:flag", kwargs={"slug": community.slug})


def _queue_url(community):
    return reverse("moderation:queue", kwargs={"slug": community.slug})


def _post_flag(client, community, target_type, target_id, reason="fake_or_scam", detail=""):
    return client.post(
        _flag_url(community),
        {"target_type": target_type, "target_id": str(target_id), "reason": reason, "detail": detail},
    )


# ── Submitting a report ────────────────────────────────────────────────


class TestFlagCreate:
    def test_member_can_flag_a_need(self, community, reporter, coordinator, need):
        client = _login(reporter)
        resp = _post_flag(client, community, "need", need.id, detail="Asked me to wire money.")
        assert resp.status_code == 302
        assert "reported=1" in resp["Location"]

        flag = Flag.objects.get()
        assert flag.status == "open"
        assert flag.need == need
        assert flag.reporter == reporter
        assert flag.reason == "fake_or_scam"
        assert flag.detail == "Asked me to wire money."

    def test_flag_emits_audit_without_free_text(self, community, reporter, need):
        client = _login(reporter)
        _post_flag(client, community, "need", need.id, detail="secret context")
        row = AuditLog.objects.get(action="flag.submitted")
        assert row.details == {"target_type": "need", "reason": "fake_or_scam"}
        assert "secret" not in str(row.details)

    def test_flag_notifies_coordinators_not_reporter(self, community, reporter, coordinator, need):
        client = _login(reporter)
        _post_flag(client, community, "need", need.id)
        notes = Notification.objects.filter(type="flag_submitted")
        assert notes.count() == 1
        note = notes.get()
        assert note.recipient == coordinator.user
        assert note.link == _queue_url(community)
        # Body carries no titles/names — reason category only.
        assert need.title not in note.body

    def test_reporting_coordinator_is_not_self_notified(self, community, coordinator, need):
        client = _login(coordinator)
        _post_flag(client, community, "need", need.id)
        assert not Notification.objects.filter(type="flag_submitted", recipient=coordinator.user).exists()

    def test_cannot_flag_own_need(self, community, poster, need):
        client = _login(poster)
        resp = _post_flag(client, community, "need", need.id)
        assert resp.status_code == 400
        assert Flag.objects.count() == 0

    def test_cannot_flag_self(self, community, reporter):
        client = _login(reporter)
        resp = _post_flag(client, community, "member", reporter.id)
        assert resp.status_code == 400
        assert Flag.objects.count() == 0

    def test_can_flag_a_member(self, community, reporter, poster):
        client = _login(reporter)
        resp = _post_flag(client, community, "member", poster.id, reason="safety")
        assert resp.status_code == 302
        flag = Flag.objects.get()
        assert flag.member == poster
        assert flag.target_type == "member"

    def test_duplicate_open_flag_rejected(self, community, reporter, need):
        client = _login(reporter)
        _post_flag(client, community, "need", need.id)
        resp = _post_flag(client, community, "need", need.id, reason="spam")
        assert resp.status_code == 400
        assert Flag.objects.count() == 1

    def test_re_report_allowed_after_dismissal(self, community, reporter, coordinator, need):
        client = _login(reporter)
        _post_flag(client, community, "need", need.id)
        flag = Flag.objects.get()
        flag.transition_to("dismissed")
        resp = _post_flag(client, community, "need", need.id)
        assert resp.status_code == 302
        assert Flag.objects.count() == 2

    def test_cross_community_target_404(self, community, reporter):
        foreign_need = NeedFactory()
        client = _login(reporter)
        resp = _post_flag(client, community, "need", foreign_need.id)
        assert resp.status_code == 404
        assert Flag.objects.count() == 0

    def test_rate_limited_after_five(self, community, reporter, poster):
        needs = [NeedFactory(community=community, requester=poster, category__community=community) for _ in range(6)]
        client = _login(reporter)
        for n in needs[:5]:
            assert _post_flag(client, community, "need", n.id).status_code == 302
        resp = _post_flag(client, community, "need", needs[5].id)
        assert resp.status_code == 429
        assert Flag.objects.count() == 5

    def test_invalid_target_type_400(self, community, reporter, need):
        client = _login(reporter)
        resp = _post_flag(client, community, "match", need.id)
        assert resp.status_code == 400

    def test_anonymous_redirected(self, community, need):
        resp = Client().post(_flag_url(community), {})
        assert resp.status_code == 302
        assert "login" in resp["Location"]


# ── The queue ──────────────────────────────────────────────────────────


class TestModerationQueue:
    def test_plain_member_403(self, community, reporter):
        client = _login(reporter)
        assert client.get(_queue_url(community)).status_code == 403

    def test_foreign_coordinator_404(self, community):
        foreign_coord = MemberFactory(role="coordinator")
        client = _login(foreign_coord)
        assert client.get(_queue_url(community)).status_code == 404

    def test_coordinator_sees_open_flags_only(self, community, reporter, coordinator, need, offer):
        client_r = _login(reporter)
        _post_flag(client_r, community, "need", need.id)
        _post_flag(client_r, community, "offer", offer.id)
        Flag.objects.filter(offer=offer).get().transition_to("dismissed")

        client = _login(coordinator)
        resp = client.get(_queue_url(community))
        assert resp.status_code == 200
        assert list(resp.context["flags"]) == list(Flag.objects.filter(status="open"))
        assert len(resp.context["flags"]) == 1


# ── Resolving ──────────────────────────────────────────────────────────


def _resolve_url(community, flag):
    return reverse("moderation:resolve", kwargs={"slug": community.slug, "pk": flag.pk})


def _dismiss_url(community, flag):
    return reverse("moderation:dismiss", kwargs={"slug": community.slug, "pk": flag.pk})


def _make_flag(community, reporter, **target):
    flag = Flag(community=community, reporter=reporter, reason="fake_or_scam", **target)
    flag.full_clean()
    flag.save()
    return flag


class TestFlagResolve:
    def test_hide_need_closes_it(self, community, reporter, coordinator, need):
        flag = _make_flag(community, reporter, need=need)
        client = _login(coordinator)
        resp = client.post(_resolve_url(community, flag), {"action": "hide"})
        assert resp.status_code == 302

        need.refresh_from_db()
        flag.refresh_from_db()
        assert need.status == "closed"  # archived, not deleted
        assert flag.status == "resolved"
        assert flag.resolution == "content_hidden"
        assert flag.resolved_by == coordinator
        assert flag.resolved_at is not None
        assert AuditLog.objects.filter(action="flag.resolved").exists()
        assert AuditLog.objects.filter(action="need.hidden").exists()

    def test_hidden_need_leaves_the_feed(self, community, reporter, coordinator, need):
        flag = _make_flag(community, reporter, need=need)
        client = _login(coordinator)
        client.post(_resolve_url(community, flag), {"action": "hide"})
        feed = client.get(reverse("community-feed", kwargs={"slug": community.slug}))
        assert need.title not in feed.content.decode()

    def test_hide_offer_withdraws_it(self, community, reporter, coordinator, offer):
        flag = _make_flag(community, reporter, offer=offer)
        client = _login(coordinator)
        resp = client.post(_resolve_url(community, flag), {"action": "hide"})
        assert resp.status_code == 302
        offer.refresh_from_db()
        assert offer.status == "withdrawn"
        assert AuditLog.objects.filter(action="offer.hidden").exists()

    def test_hide_matched_need_409_and_flag_stays_open(self, community, reporter, coordinator, need):
        need.status = "matched"
        need.save(update_fields=["status"])
        flag = _make_flag(community, reporter, need=need)
        client = _login(coordinator)
        resp = client.post(_resolve_url(community, flag), {"action": "hide"})
        assert resp.status_code == 409
        flag.refresh_from_db()
        need.refresh_from_db()
        assert flag.status == "open"  # transaction rolled back
        assert need.status == "matched"

    def test_hide_member_flag_400(self, community, reporter, poster, coordinator):
        flag = _make_flag(community, reporter, member=poster)
        client = _login(coordinator)
        resp = client.post(_resolve_url(community, flag), {"action": "hide"})
        assert resp.status_code == 400
        flag.refresh_from_db()
        assert flag.status == "open"

    def test_resolve_no_action(self, community, reporter, coordinator, need):
        flag = _make_flag(community, reporter, need=need)
        client = _login(coordinator)
        resp = client.post(_resolve_url(community, flag), {"action": "no_action", "note": "Spoke to Bob; legit."})
        assert resp.status_code == 302
        flag.refresh_from_db()
        need.refresh_from_db()
        assert flag.status == "resolved"
        assert flag.resolution == "no_action"
        assert flag.resolution_note == "Spoke to Bob; legit."
        assert need.status == "open"  # untouched

    def test_double_resolve_409(self, community, reporter, coordinator, need):
        flag = _make_flag(community, reporter, need=need)
        client = _login(coordinator)
        client.post(_resolve_url(community, flag), {"action": "no_action"})
        resp = client.post(_resolve_url(community, flag), {"action": "no_action"})
        assert resp.status_code == 409

    def test_plain_member_cannot_resolve(self, community, reporter, poster, need):
        flag = _make_flag(community, reporter, need=need)
        client = _login(poster)
        resp = client.post(_resolve_url(community, flag), {"action": "no_action"})
        assert resp.status_code == 403

    def test_dismiss(self, community, reporter, coordinator, need):
        flag = _make_flag(community, reporter, need=need)
        client = _login(coordinator)
        resp = client.post(_dismiss_url(community, flag), {"note": "Not a violation."})
        assert resp.status_code == 302
        flag.refresh_from_db()
        assert flag.status == "dismissed"
        assert flag.resolution_note == "Not a violation."
        assert flag.resolved_by == coordinator
        assert AuditLog.objects.filter(action="flag.dismissed").exists()


# ── Model guards ───────────────────────────────────────────────────────


class TestFlagModel:
    def test_exactly_one_target_required(self, community, reporter, need, offer):
        from django.core.exceptions import ValidationError

        flag = Flag(community=community, reporter=reporter, reason="spam", need=need, offer=offer)
        with pytest.raises(ValidationError):
            flag.full_clean()
        flag = Flag(community=community, reporter=reporter, reason="spam")
        with pytest.raises(ValidationError):
            flag.full_clean()

    def test_target_must_match_community(self, reporter, community):
        from django.core.exceptions import ValidationError

        foreign_need = NeedFactory()
        flag = Flag(community=community, reporter=reporter, reason="spam", need=foreign_need)
        with pytest.raises(ValidationError):
            flag.full_clean()
