"""A2: the coordinator-issued reset (docs/specs/account-recovery.md §C, as built).

A coordinator or admin issues a 15-minute code, reads it aloud, and the person sets their own
password at /auth/recover/code/. The coordinator never sees or sets the password. His ruling
(2026-09-30): coordinators and admins only; intake helpers stay vouch-only. Guard beyond the plan:
only a plain member of the issuer's own community, never a coordinator, an admin, or themselves,
so a reset can never be used to climb.
"""

from datetime import timedelta

import pytest
from django.core import mail
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.credentials import hash_code
from apps.accounts.models import RecoveryCredential
from apps.audit.models import AuditLog
from tests.factories import CommunityFactory, MemberFactory, UserFactory

pytestmark = pytest.mark.django_db
PURPOSE = RecoveryCredential.PURPOSE_COORDINATOR_RESET


@pytest.fixture(autouse=True)
def _mail_and_no_throttle(settings):
    from django.core.cache import cache

    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.RATELIMIT_ENABLED = False
    cache.clear()


@pytest.fixture
def parish():
    return CommunityFactory()


def _post(member, username):
    client = Client()
    client.force_login(member.user)
    return client.post(reverse("member-reset", kwargs={"slug": member.community.slug}), {"username": username})


def _target(parish, username="lost", **user_kwargs):
    return MemberFactory(community=parish, role="member", user=UserFactory(username=username, **user_kwargs))


# ── Who can issue ──────────────────────────────────────────────


def test_coordinator_issues_a_fifteen_minute_code(parish):
    coord = MemberFactory(community=parish, role="coordinator", display_name="Dan")
    target = _target(parish)
    before = target.user.password
    resp = _post(coord, "lost")
    assert resp.status_code == 200
    code = resp.context["code"]
    cred = RecoveryCredential.objects.get(user=target.user, purpose=PURPOSE)
    assert cred.token_hash == hash_code(code)
    assert cred.issued_by == coord and cred.issued_by_label == "Dan"
    assert timedelta(minutes=14) < cred.expires_at - timezone.now() <= timedelta(minutes=15, seconds=5)
    target.user.refresh_from_db()
    assert target.user.password == before  # the coordinator never sets it


def test_admin_can_issue(parish):
    admin = MemberFactory(community=parish, role="admin")
    _target(parish)
    assert _post(admin, "lost").status_code == 200


def test_plain_member_is_refused(parish):
    member = MemberFactory(community=parish, role="member")
    _target(parish)
    assert _post(member, "lost").status_code == 403
    assert not RecoveryCredential.objects.exists()


def test_member_can_reset_and_helper_cannot_by_capability(parish):
    assert MemberFactory(community=parish, role="coordinator").can_reset
    assert MemberFactory(community=parish, role="admin").can_reset
    assert not MemberFactory(community=parish, role="member").can_reset


# ── Whom ───────────────────────────────────────────────────────


def test_target_in_another_community_is_refused(parish):
    coord = MemberFactory(community=parish, role="coordinator")
    other = CommunityFactory()
    MemberFactory(community=other, role="member", user=UserFactory(username="elsewhere"))
    UserFactory(username="nomember")
    for name in ("elsewhere", "nomember"):
        resp = _post(coord, name)
        assert resp.status_code == 200 and resp.context["code"] is None
    assert not RecoveryCredential.objects.exists()


def test_cannot_reset_a_coordinator_an_admin_or_yourself(parish):
    coord = MemberFactory(community=parish, role="coordinator", user=UserFactory(username="me"))
    MemberFactory(community=parish, role="coordinator", user=UserFactory(username="peer"))
    MemberFactory(community=parish, role="admin", user=UserFactory(username="boss"))
    for name in ("peer", "boss", "me"):
        _post(coord, name)
    assert not RecoveryCredential.objects.exists()


def test_inactive_member_is_refused(parish):
    coord = MemberFactory(community=parish, role="coordinator")
    left = _target(parish)
    left.is_active = False
    left.save()
    _post(coord, "lost")
    assert not RecoveryCredential.objects.exists()


# ── Detection: audit and notice ────────────────────────────────


def test_audited_with_both_members_and_the_community(parish):
    coord = MemberFactory(community=parish, role="coordinator")
    target = _target(parish)
    _post(coord, "lost")
    row = AuditLog.objects.get(action="account.reset.coordinator")
    assert row.user == coord.user
    assert row.details == {"community": parish.slug, "issuer_member": str(coord.pk), "target_member": str(target.pk)}


def test_person_with_an_email_is_told(parish):
    coord = MemberFactory(community=parish, role="coordinator", display_name="Dan")
    _target(parish, email="lost@example.org")
    _post(coord, "lost")
    assert [m.to for m in mail.outbox] == [["lost@example.org"]]
    assert "Dan" in mail.outbox[0].body
    assert RecoveryCredential.objects.get().token_hash not in mail.outbox[0].body


def test_person_without_a_confirmed_email_gets_no_mail(parish):
    coord = MemberFactory(community=parish, role="coordinator")
    _target(parish, email="typo@example.org", email_confirmed_at=None)
    _post(coord, "lost")
    assert mail.outbox == []


@override_settings(RATELIMIT_ENABLE=True)
def test_rate_limited_per_coordinator(parish):
    coord = MemberFactory(community=parish, role="coordinator")
    for i in range(6):
        _target(parish, username=f"p{i}")
    codes = [_post(coord, f"p{i}").status_code for i in range(6)]
    assert codes[:5] == [200] * 5
    assert codes[5] in (403, 429)


# ── Redemption ─────────────────────────────────────────────────


def test_person_redeems_it_at_the_recovery_page_and_it_dies_after_fifteen_minutes(parish):
    coord = MemberFactory(community=parish, role="coordinator")
    _target(parish)
    code = _post(coord, "lost").context["code"]
    resp = Client().post(reverse("recovery-code-redeem"), {"username": "lost", "code": code})
    assert "/auth/password/reset/" in resp.content.decode()
    assert AuditLog.objects.filter(action="account.reset.redeemed").count() == 1

    code2 = _post(coord, "lost").context["code"]
    RecoveryCredential.objects.filter(used_at__isnull=True, purpose=PURPOSE).update(
        expires_at=timezone.now() - timedelta(seconds=1)
    )
    resp = Client().post(reverse("recovery-code-redeem"), {"username": "lost", "code": code2})
    assert "/auth/password/reset/" not in resp.content.decode()


def test_settings_page_offers_the_reset_form(parish):
    coord = MemberFactory(community=parish, role="coordinator")
    client = Client()
    client.force_login(coord.user)
    body = client.get(reverse("community-settings", kwargs={"slug": parish.slug})).content.decode()
    assert reverse("member-reset", kwargs={"slug": parish.slug}) in body


# ── Landlines: a call back to the number on file (the founder's yes, 2026-10-03) ──


def test_the_code_page_shows_the_number_to_call_back_and_only_that_one(parish):
    coord = MemberFactory(community=parish, role="coordinator")
    _target(parish, phone="(555) 234-5678")
    body = _post(coord, "lost").content.decode()
    assert "(555) 234-5678" in body
    assert "call them back on the number saved on their account" in body
    assert "never one they give you" in body


def test_without_a_number_on_file_it_is_in_person_only(parish):
    coord = MemberFactory(community=parish, role="coordinator")
    _target(parish)
    body = _post(coord, "lost").content.decode()
    assert "call them back" not in body
    assert "No phone number is saved on their account" in body


def test_settings_says_a_locked_out_member_can_be_on_the_phone(parish):
    coord = MemberFactory(community=parish, role="coordinator")
    client = Client()
    client.force_login(coord.user)
    body = client.get(reverse("community-settings", kwargs={"slug": parish.slug})).content.decode()
    assert "standing with you, or on a call you make" in body
