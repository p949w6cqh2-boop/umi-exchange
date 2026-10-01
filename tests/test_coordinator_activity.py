"""C13: the coordinator activity page, "which coordinator did what" (docs/specs/coordinator-activity.md).

AuditLog has no community column and is append-only, so the page scopes each coordinator action to
a community through the resource it names (a member, a resource, a flag, a tag, a page, the
community itself) or, for a vouch, through the community slug the event already records. These
tests pin the three things that matter: a coordinator sees their own community's actions, never
another community's, and never a member's private acts or anything the audit layer kept out.
"""

from datetime import timedelta

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.audit.services import emit
from apps.communities.models import Resource
from apps.moderation.models import Flag
from tests.conftest import NeedFactory, PageFactory
from tests.factories import CommunityFactory, MemberFactory, UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def parish():
    return CommunityFactory()


def _page(member, **params):
    client = Client()
    client.force_login(member.user)
    return client.get(reverse("community-activity", kwargs={"slug": member.community.slug}), params)


def _coord(community, name="Dan"):
    return MemberFactory(community=community, role="coordinator", display_name=name)


# ── Access ─────────────────────────────────────────────────────


def test_plain_member_is_refused(parish):
    assert _page(MemberFactory(community=parish, role="member")).status_code == 403


def test_anonymous_is_sent_to_login(parish):
    resp = Client().get(reverse("community-activity", kwargs={"slug": parish.slug}))
    assert resp.status_code == 302 and "/auth/login/" in resp["Location"]


def test_coordinator_and_admin_can_open_it(parish):
    assert _page(_coord(parish)).status_code == 200
    assert _page(MemberFactory(community=parish, role="admin")).status_code == 200


def test_settings_page_links_to_it(parish):
    coord = _coord(parish)
    client = Client()
    client.force_login(coord.user)
    body = client.get(reverse("community-settings", kwargs={"slug": parish.slug})).content.decode()
    assert reverse("community-activity", kwargs={"slug": parish.slug}) in body


# ── What it shows ──────────────────────────────────────────────


def test_shows_each_kind_of_coordinator_action_with_who_did_it(parish):
    coord = _coord(parish, "Dan")
    target = MemberFactory(community=parish, display_name="Rose")
    resource = Resource.objects.create(community=parish, title="Food bank", url="https://ex.org", added_by=coord)
    need = NeedFactory(community=parish)
    flag = Flag.objects.create(community=parish, reporter=target, target_type="need", target_id=need.id, reason="spam")
    page = PageFactory(community=parish)
    vouched = UserFactory(username="newbie")

    emit("member.role_changed", target, user=coord.user, details={"from": "member", "to": "coordinator"})
    emit("member.removed", target, user=coord.user, details={})
    emit("resource.added", resource, user=coord.user, details={"category": "food"})
    emit("content.hidden", need, user=coord.user, details={"target_type": "need"})
    emit("flag.resolved", flag, user=coord.user, details={"action": "hide"})
    emit("page.published", page, user=coord.user, details={"slug": page.slug})
    emit("community.updated", parish, user=coord.user, details={"visibility": "private"})
    emit("user.vouched", vouched, user=coord.user, details={"vouched_username": "newbie", "community": parish.slug})

    body = _page(coord).content.decode()
    assert body.count("Dan") >= 8
    for words in ["Rose", "coordinator", "removed", "resource", "hid", "flag", "page", "settings", "newbie"]:
        assert words.lower() in body.lower(), words


def test_newest_first(parish):
    coord = _coord(parish)
    a, b = MemberFactory(community=parish, display_name="Alpha"), MemberFactory(community=parish, display_name="Beta")
    emit("member.reinstated", a, user=coord.user, details={})
    emit("member.reinstated", b, user=coord.user, details={})
    body = _page(coord).content.decode()
    assert body.index("Beta") < body.index("Alpha")


# ── What it never shows ────────────────────────────────────────


def test_another_communitys_actions_never_appear(parish):
    other = CommunityFactory()
    coord, other_coord = _coord(parish), _coord(other, "Zed")
    other_member = MemberFactory(community=other, display_name="Stranger")
    emit("member.removed", other_member, user=other_coord.user, details={})
    emit("community.updated", other, user=other_coord.user, details={"visibility": "public"})
    emit(
        "user.vouched",
        UserFactory(username="elsewhere"),
        user=other_coord.user,
        details={"vouched_username": "elsewhere", "community": other.slug},
    )
    body = _page(coord).content.decode()
    for leaked in ["Stranger", "Zed", "elsewhere"]:
        assert leaked not in body


def test_members_private_acts_and_reports_never_appear(parish):
    coord = _coord(parish)
    blocker = MemberFactory(community=parish, display_name="Quiet")
    blocked = MemberFactory(community=parish, display_name="Loud")
    need = NeedFactory(community=parish)
    flag = Flag.objects.create(community=parish, reporter=blocker, target_type="need", target_id=need.id, reason="spam")
    emit("member.blocked", blocked, user=blocker.user, details={})
    emit("member.unblocked", blocked, user=blocker.user, details={})
    emit("flag.created", flag, user=blocker.user, details={"target_type": "need"})
    body = _page(coord).content.decode()
    assert "Quiet" not in body and "Loud" not in body


def test_emails_and_ip_hashes_are_never_rendered(parish):
    coord = _coord(parish)
    coord.user.email = "dan@example.org"
    coord.user.save()
    target = MemberFactory(community=parish)
    emit("member.removed", target, user=coord.user, details={})
    row = AuditLog.objects.create(
        action="member.reinstated", resource_type="member", resource_id=target.pk, user=coord.user, ip_hash="f" * 64
    )
    body = _page(coord).content.decode()
    assert "dan@example.org" not in body
    assert row.ip_hash not in body


def test_raw_details_are_not_dumped(parish):
    coord = _coord(parish)
    target = MemberFactory(community=parish)
    emit("member.removed", target, user=coord.user, details={"matches_cancelled": 2, "secret_field": "SHOULD-NOT-SHOW"})
    assert "SHOULD-NOT-SHOW" not in _page(coord).content.decode()


# ── Paging and dates ───────────────────────────────────────────


def test_paginates_fifty_at_a_time(parish):
    coord = _coord(parish)
    target = MemberFactory(community=parish)
    for _ in range(60):
        emit("member.reinstated", target, user=coord.user, details={})
    first = _page(coord)
    second = _page(coord, page=2)
    assert len(first.context["events"]) == 50
    assert len(second.context["events"]) == 10


def test_date_filter(parish):
    coord = _coord(parish)
    target = MemberFactory(community=parish, display_name="Old")
    emit("member.reinstated", target, user=coord.user, details={})
    since = (timezone.now() + timedelta(days=1)).date().isoformat()
    assert len(_page(coord, since=since).context["events"]) == 0
    assert len(_page(coord).context["events"]) == 1


def test_coordinator_reset_codes_show_with_whom_and_stay_in_their_community(parish):
    """A2's reset is the most sensitive coordinator power, so this page must show it (#186)."""
    coord = _coord(parish, "Dan")
    target = MemberFactory(community=parish, display_name="Agnes")
    other = CommunityFactory()
    other_coord, other_target = _coord(other, "Zed"), MemberFactory(community=other, display_name="Far")
    emit(
        "account.reset.coordinator",
        target.user,
        user=coord.user,
        details={"community": parish.slug, "issuer_member": str(coord.pk), "target_member": str(target.pk)},
    )
    emit(
        "account.reset.coordinator",
        other_target.user,
        user=other_coord.user,
        details={"community": other.slug, "issuer_member": str(other_coord.pk), "target_member": str(other_target.pk)},
    )
    body = _page(coord).content.decode()
    assert "made a password reset code" in body and "Agnes" in body and "Dan" in body
    assert "Far" not in body and "Zed" not in body


def test_a_real_vouch_shows_up(parish):
    coord = _coord(parish, "Dan")
    UserFactory(username="walkin", verified_at=None, verified_via="")
    client = Client()
    client.force_login(coord.user)
    client.post(reverse("member-vouch", kwargs={"slug": parish.slug}), {"username": "walkin"})
    body = _page(coord).content.decode()
    assert "walkin" in body and "Dan" in body
