"""C11: the intake helper, a role that can vouch and nothing else (docs/specs/coordinator-roles.md).

The design is additive. Every existing coordinator check names "coordinator" and "admin"
explicitly, so a new role is excluded from all of them by construction. These tests pin that:
a helper vouches, and on every coordinator surface gets exactly the answer a plain member gets.
"""

import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.models import User
from apps.audit.models import AuditLog
from apps.communities.models import Member
from tests.factories import CommunityFactory, MemberFactory, UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def parish():
    return CommunityFactory()


def _client_for(member):
    client = Client()
    client.force_login(member.user)
    return client


def _unverified(username):
    return UserFactory(username=username, verified_at=None, verified_via="")


# ── The role itself ────────────────────────────────────────────


def test_intake_is_a_role_choice():
    assert "intake" in dict(Member.ROLE_CHOICES)


def test_intake_helper_is_not_a_coordinator(parish):
    helper = MemberFactory(community=parish, role="intake")
    assert helper.is_coordinator is False
    assert helper.is_admin is False
    assert helper.can_vouch is True


def test_who_can_vouch(parish):
    assert MemberFactory(community=parish, role="coordinator").can_vouch
    assert MemberFactory(community=parish, role="admin").can_vouch
    assert not MemberFactory(community=parish, role="member").can_vouch


# ── The one power it has ───────────────────────────────────────


def test_intake_helper_can_open_the_vouch_page(parish):
    helper = MemberFactory(community=parish, role="intake")
    resp = _client_for(helper).get(reverse("member-vouch-page", kwargs={"slug": parish.slug}))
    assert resp.status_code == 200
    assert reverse("member-vouch", kwargs={"slug": parish.slug}) in resp.content.decode()


def test_plain_member_cannot_open_the_vouch_page(parish):
    member = MemberFactory(community=parish, role="member")
    assert _client_for(member).get(reverse("member-vouch-page", kwargs={"slug": parish.slug})).status_code == 403


def test_intake_helper_can_vouch_and_returns_to_the_vouch_page(parish):
    helper = MemberFactory(community=parish, role="intake")
    target = _unverified("newneighbor")
    resp = _client_for(helper).post(
        reverse("member-vouch", kwargs={"slug": parish.slug}), {"username": "newneighbor", "return_to": "vouch"}
    )
    assert resp.status_code == 302
    assert resp["Location"] == reverse("member-vouch-page", kwargs={"slug": parish.slug})
    target.refresh_from_db()
    assert target.verified_via == "coordinator"
    assert AuditLog.objects.filter(action="user.vouched", user=helper.user).exists()


def test_coordinator_vouch_still_returns_to_settings(parish):
    coordinator = MemberFactory(community=parish, role="coordinator")
    _unverified("other")
    resp = _client_for(coordinator).post(reverse("member-vouch", kwargs={"slug": parish.slug}), {"username": "other"})
    assert resp["Location"] == reverse("community-settings", kwargs={"slug": parish.slug})


def test_plain_member_still_cannot_vouch(parish):
    member = MemberFactory(community=parish, role="member")
    _unverified("x1")
    resp = _client_for(member).post(reverse("member-vouch", kwargs={"slug": parish.slug}), {"username": "x1"})
    assert resp.status_code == 403
    assert User.objects.get(username="x1").verified_at is None


def test_helper_in_one_parish_cannot_vouch_in_another(parish):
    other = CommunityFactory()
    helper = MemberFactory(community=parish, role="intake")
    MemberFactory(community=other, role="member", user=helper.user)
    _unverified("y1")
    resp = _client_for(helper).post(reverse("member-vouch", kwargs={"slug": other.slug}), {"username": "y1"})
    assert resp.status_code == 403


# ── Everything else: exactly what a plain member gets ─────────

COORDINATOR_GETS = [
    ("community-settings", {}),
    ("community-dashboard", {}),
    ("moderation:queue", {}),
    ("tags:queue", {}),
]


@pytest.mark.parametrize("name,extra", COORDINATOR_GETS)
def test_helper_gets_the_member_answer_on_coordinator_pages(parish, name, extra):
    member = MemberFactory(community=parish, role="member")
    helper = MemberFactory(community=parish, role="intake")
    url = reverse(name, kwargs={"slug": parish.slug, **extra})
    as_member = _client_for(member).get(url)
    as_helper = _client_for(helper).get(url)
    assert as_helper.status_code == as_member.status_code
    assert as_helper.status_code != 200 or as_member.status_code == 200


def test_helper_cannot_curate_resources(parish):
    helper = MemberFactory(community=parish, role="intake")
    resp = _client_for(helper).post(
        reverse("community-resources", kwargs={"slug": parish.slug}),
        {"action": "add", "title": "x", "url": "https://example.org", "category": "other"},
    )
    assert resp.status_code == 403


def test_helper_cannot_change_roles(parish):
    MemberFactory(community=parish, role="admin")
    helper = MemberFactory(community=parish, role="intake")
    target = MemberFactory(community=parish, role="member")
    _client_for(helper).post(
        reverse("community-settings", kwargs={"slug": parish.slug}),
        {"action": "change_role", "member_id": str(target.id), "role": "coordinator"},
    )
    target.refresh_from_db()
    helper.refresh_from_db()
    assert target.role == "member"
    assert helper.role == "intake"


def test_admin_can_make_someone_an_intake_helper_and_it_is_audited(parish):
    admin = MemberFactory(community=parish, role="admin")
    target = MemberFactory(community=parish, role="member")
    _client_for(admin).post(
        reverse("community-settings", kwargs={"slug": parish.slug}),
        {"action": "change_role", "member_id": str(target.id), "role": "intake"},
    )
    target.refresh_from_db()
    assert target.role == "intake"
    row = AuditLog.objects.get(action="member.role_changed")
    assert row.details == {"from": "member", "to": "intake"}


def test_header_shows_helper_the_vouch_link_not_settings(parish):
    helper = MemberFactory(community=parish, role="intake")
    body = _client_for(helper).get(reverse("community-feed", kwargs={"slug": parish.slug})).content.decode()
    assert reverse("member-vouch-page", kwargs={"slug": parish.slug}) in body
    assert reverse("community-settings", kwargs={"slug": parish.slug}) not in body
