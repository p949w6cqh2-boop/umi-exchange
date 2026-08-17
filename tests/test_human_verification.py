"""Human verification at sign-up — the keyed A+C build of docs/specs/human-verification.md.

His keys, 2026-08-12: option A (email verification, SOFT gate: sign in and look around,
but no community join / post / propose until verified) + option C (honeypot + timing on
the register form, same response either way — no oracle for the bot author) + the
two-exit amendment for the protocol's email-optional accounts: a coordinator can vouch
for a neighbour in person (audited), because a robot doesn't sit in a pew.

House gotchas honoured: register/login are IP-throttled — every POST here carries its
own REMOTE_ADDR.
"""

import time

import pytest
from django.contrib.auth import get_user_model
from django.core import mail, signing
from django.urls import reverse

from apps.accounts.verification import EMAIL_VERIFY_SALT, HONEYPOT_TS_SALT, make_email_token
from tests.conftest import CommunityFactory, MemberFactory, NeedFactory

User = get_user_model()
pytestmark = pytest.mark.django_db

STRONG = "Str0ng-p4ss!x9"


def _ip(n):
    return f"10.77.0.{n}"


@pytest.fixture()
def parish(db):
    community = CommunityFactory()
    member = MemberFactory(community=community)
    coordinator = MemberFactory(community=community, role="coordinator")
    return {"community": community, "member": member, "coordinator": coordinator}


def _register(client, n, username, email=""):
    """POST the register form like a human: honeypot empty, form age > minimum."""
    ts = signing.dumps(time.time() - 30, salt=HONEYPOT_TS_SALT)
    return client.post(
        reverse("register"),
        {
            "username": username,
            "email": email,
            "password": STRONG,
            "password_confirm": STRONG,
            "website": "",
            "hp_ts": ts,
        },
        REMOTE_ADDR=_ip(n),
    )


# ── A: email verification ────────────────────────────────────────────────


def test_register_with_email_sends_verification_link(client):
    resp = _register(client, 1, "nuala", "nuala@example.org")
    assert resp.status_code in (301, 302)
    assert len(mail.outbox) == 1
    assert "verify" in mail.outbox[0].body.lower()
    user = User.objects.get(username="nuala")
    assert user.verified_at is None


def test_clicking_link_verifies(client):
    _register(client, 2, "marta", "marta@example.org")
    user = User.objects.get(username="marta")
    token = make_email_token(user)
    resp = client.get(reverse("verify-email", args=[token]))
    assert resp.status_code in (301, 302)
    user.refresh_from_db()
    assert user.verified_at is not None
    assert user.verified_via == "email"


def test_tampered_token_rejected(client):
    _register(client, 3, "tom", "tom@example.org")
    user = User.objects.get(username="tom")
    token = make_email_token(user) + "x"
    client.get(reverse("verify-email", args=[token]))
    user.refresh_from_db()
    assert user.verified_at is None


def test_expired_token_rejected(client, settings):
    _register(client, 4, "old", "old@example.org")
    user = User.objects.get(username="old")
    # a token signed 49 hours ago (48h max age)
    token = signing.dumps({"uid": str(user.pk)}, salt=EMAIL_VERIFY_SALT)
    import unittest.mock as m

    with m.patch("django.core.signing.TimestampSigner.unsign", side_effect=signing.SignatureExpired("old")):
        client.get(reverse("verify-email", args=[token]))
    user.refresh_from_db()
    assert user.verified_at is None


def test_resend_sends_again_and_is_throttled_path(client):
    _register(client, 5, "resender", "resender@example.org")
    mail.outbox.clear()
    client.post(reverse("login"), {"username": "resender", "password": STRONG}, REMOTE_ADDR=_ip(50))
    resp = client.post(reverse("verify-send"), REMOTE_ADDR=_ip(51))
    assert resp.status_code in (301, 302)
    assert len(mail.outbox) == 1


# ── the soft gate ────────────────────────────────────────────────────────


def _unverified_member_client(client, parish):
    """A signed-in, UNVERIFIED user who is already a member (pre-gate account),
    for the post/propose doors."""
    user = parish["member"].user
    user.verified_at = None
    user.verified_via = ""
    user.save(update_fields=["verified_at", "verified_via"])
    client.force_login(user)
    return parish["member"]


def test_unverified_cannot_join_community(client, parish):
    _register(client, 6, "gated")
    user = User.objects.get(username="gated")
    client.force_login(user)
    resp = client.post(
        reverse("community-join"),
        {"join_code": parish["community"].join_code},
        REMOTE_ADDR=_ip(6),
    )
    assert resp.status_code in (301, 302)
    assert reverse("verify-pending") in resp.url
    assert not user.member_set.exists()


def test_unverified_cannot_post_need(client, parish):
    member = _unverified_member_client(client, parish)
    resp = client.get(reverse("need-create", kwargs={"slug": member.community.slug}))
    assert resp.status_code in (301, 302)
    assert reverse("verify-pending") in resp.url


def test_unverified_cannot_post_offer(client, parish):
    member = _unverified_member_client(client, parish)
    resp = client.get(reverse("offer-create", kwargs={"slug": member.community.slug}))
    assert resp.status_code in (301, 302)
    assert reverse("verify-pending") in resp.url


def test_unverified_cannot_propose_match(client, parish):
    member = _unverified_member_client(client, parish)
    need = NeedFactory(community=member.community)
    resp = client.post(
        reverse("match-propose", kwargs={"slug": member.community.slug}),
        {"need_id": str(need.id)},
        REMOTE_ADDR=_ip(7),
    )
    assert resp.status_code in (301, 302)
    assert reverse("verify-pending") in resp.url


def test_verified_member_passes_the_doors(client, parish):
    member = parish["member"]
    user = member.user
    assert user.verified_at is not None  # backfill migration promise
    client.force_login(user)
    resp = client.get(reverse("need-create", kwargs={"slug": member.community.slug}))
    assert resp.status_code == 200


def test_pending_page_names_both_exits(client):
    _register(client, 8, "reader", "reader@example.org")
    user = User.objects.get(username="reader")
    client.force_login(user)
    html = client.get(reverse("verify-pending")).content.decode().lower()
    assert "email" in html
    assert "coordinator" in html


def test_backfill_marked_existing_users_verified(parish):
    # The data migration promise: accounts that predate the gate are verified.
    assert parish["member"].user.verified_at is not None
    assert parish["member"].user.verified_via == "backfill"


# ── B-exit: the coordinator vouch ────────────────────────────────────────


def test_coordinator_vouch_verifies_email_less_user(client, parish):
    _register(client, 9, "pewneighbour")  # no email at all
    target = User.objects.get(username="pewneighbour")
    assert target.verified_at is None
    coordinator = parish["coordinator"]
    client.force_login(coordinator.user)
    resp = client.post(
        reverse("member-vouch", kwargs={"slug": coordinator.community.slug}),
        {"username": "pewneighbour"},
        REMOTE_ADDR=_ip(9),
    )
    assert resp.status_code in (301, 302)
    target.refresh_from_db()
    assert target.verified_at is not None
    assert target.verified_via == "coordinator"


def test_vouch_is_audited(client, parish):
    from apps.audit.models import AuditLog

    _register(client, 10, "audited")
    coordinator = parish["coordinator"]
    client.force_login(coordinator.user)
    client.post(
        reverse("member-vouch", kwargs={"slug": coordinator.community.slug}),
        {"username": "audited"},
        REMOTE_ADDR=_ip(10),
    )
    assert AuditLog.objects.filter(action="user.vouched").exists()


def test_ordinary_member_cannot_vouch(client, parish):
    _register(client, 11, "sneaky")
    member = parish["member"]
    client.force_login(member.user)
    resp = client.post(
        reverse("member-vouch", kwargs={"slug": member.community.slug}),
        {"username": "sneaky"},
        REMOTE_ADDR=_ip(11),
    )
    assert resp.status_code in (403, 404)
    assert User.objects.get(username="sneaky").verified_at is None


# ── C: honeypot + timing ─────────────────────────────────────────────────


def test_honeypot_filled_creates_no_account_same_shape_response(client):
    ts = signing.dumps(time.time() - 30, salt=HONEYPOT_TS_SALT)
    resp = client.post(
        reverse("register"),
        {
            "username": "bot1",
            "email": "",
            "password": STRONG,
            "password_confirm": STRONG,
            "website": "https://spam.example",
            "hp_ts": ts,
        },
        REMOTE_ADDR=_ip(21),
    )
    assert resp.status_code in (301, 302)  # same shape as success — no oracle
    assert not User.objects.filter(username="bot1").exists()


def test_too_fast_submit_creates_no_account(client):
    ts = signing.dumps(time.time(), salt=HONEYPOT_TS_SALT)  # 0 seconds old
    resp = client.post(
        reverse("register"),
        {
            "username": "bot2",
            "email": "",
            "password": STRONG,
            "password_confirm": STRONG,
            "website": "",
            "hp_ts": ts,
        },
        REMOTE_ADDR=_ip(22),
    )
    assert resp.status_code in (301, 302)
    assert not User.objects.filter(username="bot2").exists()


def test_missing_timestamp_creates_no_account(client):
    resp = client.post(
        reverse("register"),
        {
            "username": "bot3",
            "email": "",
            "password": STRONG,
            "password_confirm": STRONG,
            "website": "",
        },
        REMOTE_ADDR=_ip(23),
    )
    assert resp.status_code in (301, 302)
    assert not User.objects.filter(username="bot3").exists()


def test_human_registration_still_works_end_to_end(client):
    resp = _register(client, 24, "human", "human@example.org")
    assert resp.status_code in (301, 302)
    assert User.objects.filter(username="human").exists()
