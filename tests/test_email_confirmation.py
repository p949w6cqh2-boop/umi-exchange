"""Confirm an email before anything trusts it — docs/specs/email-confirmation.md, issue #172.

Password reset, username recovery, notification email, casework reminders and the contact
reveal on a match all used `User.email` as if the account holder owned it. Nothing recorded
whether they did. In production on 2026-09-26, every real account with an email had an
address nobody had ever proven — and a typo at sign-up made a stranger's inbox the account's
password-reset path.

`verified_via` could not carry this: it answers "is this a human?", and a coordinator vouch
is the strongest answer to that while proving nothing about any inbox. Two questions, one
column. This file pins the second column and the one accessor every sender must use.
"""

import re
from pathlib import Path

import pytest
from django import forms
from django.contrib.auth import get_user_model
from django.core import mail, signing
from django.urls import reverse
from django.utils import timezone

from apps.accounts.verification import EMAIL_VERIFY_SALT, make_add_email_token, make_email_token

User = get_user_model()
pytestmark = pytest.mark.django_db

STRONG = "Str0ng-p4ss!x9"
REPO = Path(__file__).resolve().parent.parent


def _user(name, email, confirmed, **extra):
    u = User.objects.create_user(name, email=email, password=STRONG, **extra)
    if confirmed:
        u.email_confirmed_at = timezone.now()
        u.save(update_fields=["email_confirmed_at"])
    return u


# ── the field and the accessor ───────────────────────────────────────────────


def test_a_new_address_is_unconfirmed():
    u = User.objects.create_user("new", email="new@example.org", password=STRONG)

    assert u.email_confirmed_at is None
    assert u.deliverable_email is None


def test_deliverable_email_is_the_address_once_confirmed():
    u = _user("ok", "ok@example.org", confirmed=True)

    assert u.deliverable_email == "ok@example.org"


def test_no_address_means_nothing_deliverable_even_if_the_stamp_is_set():
    u = User.objects.create_user("none", email=None, password=STRONG)
    u.email_confirmed_at = timezone.now()
    u.save(update_fields=["email_confirmed_at"])

    assert u.deliverable_email is None


# ── changing the address clears the proof, in the MODEL ─────────────────────


def test_changing_the_address_clears_confirmation_through_a_plain_save():
    u = _user("mover", "old@example.org", confirmed=True)

    u.email = "new@example.org"
    u.save()

    u.refresh_from_db()
    assert u.email_confirmed_at is None


def test_changing_the_address_through_a_modelform_clears_it_too():
    """The next caller will not come through our views. A plain ModelForm is how
    an admin page or a future settings form would reach the column."""

    class AnyForm(forms.ModelForm):
        class Meta:
            model = User
            fields = ["email"]

    u = _user("formed", "old@example.org", confirmed=True)
    form = AnyForm({"email": "other@example.org"}, instance=u)
    assert form.is_valid(), form.errors
    form.save()

    u.refresh_from_db()
    assert u.email_confirmed_at is None


def test_changing_the_address_with_update_fields_still_clears_it():
    u = _user("narrow", "old@example.org", confirmed=True)

    u.email = "narrow-new@example.org"
    u.save(update_fields=["email"])

    u.refresh_from_db()
    assert u.email_confirmed_at is None


def test_saving_other_fields_keeps_the_confirmation():
    u = _user("steady", "steady@example.org", confirmed=True)

    u.phone = "555-0100"
    u.save()

    u.refresh_from_db()
    assert u.email_confirmed_at is not None


def test_a_fresh_confirmation_written_with_the_new_address_is_kept():
    """ConfirmAddEmailView writes the new address and its proof in one save. The
    model must not clear the proof it was just handed."""
    u = _user("swap", "old@example.org", confirmed=True)

    u.email = "proven@example.org"
    u.email_confirmed_at = timezone.now()
    u.save()

    u.refresh_from_db()
    assert u.email == "proven@example.org"
    assert u.email_confirmed_at is not None


# ── the links that write the proof ───────────────────────────────────────────


def test_the_registration_link_confirms_the_address(client):
    u = _user("reg", "reg@example.org", confirmed=False)

    client.get(reverse("verify-email", args=[make_email_token(u)]))

    u.refresh_from_db()
    assert u.email_confirmed_at is not None
    assert u.verified_via == "email"


def test_the_link_confirms_an_already_verified_account_and_leaves_its_verification_alone(client):
    """The four backfill accounts held back on 2026-09-26. Before this fix the link
    recorded nothing for them and still said 'Email confirmed'. Now it records the
    one thing it proves — and a vouch or backfill stays exactly what it was."""
    u = _user("old", "old@example.org", confirmed=False)
    u.verified_at = timezone.now()
    u.verified_via = "backfill"
    u.save(update_fields=["verified_at", "verified_via"])

    client.get(reverse("verify-email", args=[make_email_token(u)]))

    u.refresh_from_db()
    assert u.email_confirmed_at is not None
    assert u.verified_via == "backfill"


def test_a_link_sent_to_an_old_address_does_not_confirm_the_new_one(client):
    """The token proves control of the address it was SENT to. If the address has
    changed since, confirming the current one would bless an inbox nobody proved."""
    u = _user("changer", "first@example.org", confirmed=False)
    token = make_email_token(u)
    u.email = "second@example.org"
    u.save()

    client.get(reverse("verify-email", args=[token]))

    u.refresh_from_db()
    assert u.email == "second@example.org"
    assert u.email_confirmed_at is None


def test_a_legacy_uid_only_link_still_confirms_the_current_address(client):
    """Four links went out on 2026-09-26 carrying only a user id. They must keep
    working for their 48 hours; after that every live token carries its address."""
    u = _user("legacy", "legacy@example.org", confirmed=False)
    legacy = signing.dumps({"uid": str(u.pk)}, salt=EMAIL_VERIFY_SALT)

    client.get(reverse("verify-email", args=[legacy]))

    u.refresh_from_db()
    assert u.email_confirmed_at is not None


def test_the_add_email_link_confirms_the_new_address(client):
    u = User.objects.create_user("adder", email=None, password=STRONG)

    client.get(reverse("account-confirm-email", args=[make_add_email_token(u, "added@example.org")]))

    u.refresh_from_db()
    assert u.email == "added@example.org"
    assert u.email_confirmed_at is not None


# ── resend works for the people who need it ─────────────────────────────────


def test_a_verified_account_with_an_unconfirmed_address_can_ask_for_the_link(client):
    """The resend view used to bounce every verified account to the hub — which is
    every backfill account, i.e. exactly the people this fix locks out of reset
    until they confirm."""
    u = _user("stuck", "stuck@example.org", confirmed=False)
    u.verified_at = timezone.now()
    u.verified_via = "backfill"
    u.save(update_fields=["verified_at", "verified_via"])
    client.force_login(u)

    client.post(reverse("verify-send"), REMOTE_ADDR="10.9.0.1")

    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["stuck@example.org"]


def test_a_fully_confirmed_account_gets_no_resend(client):
    u = _user("done", "done@example.org", confirmed=True)
    u.verified_at = timezone.now()
    u.verified_via = "email"
    u.save(update_fields=["verified_at", "verified_via"])
    client.force_login(u)

    resp = client.post(reverse("verify-send"), REMOTE_ADDR="10.9.0.2")

    assert resp.status_code == 302
    assert len(mail.outbox) == 0


# ── the senders ──────────────────────────────────────────────────────────────


def test_password_reset_sends_nothing_to_an_unconfirmed_address(client):
    _user("typo", "typo@example.org", confirmed=False)

    client.post(reverse("password_reset"), {"email": "typo@example.org"}, REMOTE_ADDR="10.9.1.1")

    assert len(mail.outbox) == 0


def test_password_reset_still_reaches_a_confirmed_address(client):
    _user("real", "real@example.org", confirmed=True)

    client.post(reverse("password_reset"), {"email": "real@example.org"}, REMOTE_ADDR="10.9.1.2")

    assert len(mail.outbox) == 1


def test_password_reset_answers_identically_either_way(client):
    """Any observable difference would rebuild the enumeration oracle #171 is about."""
    _user("a", "unconfirmed@example.org", confirmed=False)
    _user("b", "confirmed@example.org", confirmed=True)

    r1 = client.post(reverse("password_reset"), {"email": "unconfirmed@example.org"}, REMOTE_ADDR="10.9.1.3")
    r2 = client.post(reverse("password_reset"), {"email": "confirmed@example.org"}, REMOTE_ADDR="10.9.1.4")

    assert r1.status_code == r2.status_code
    assert r1.url == r2.url


def test_username_recovery_sends_nothing_to_an_unconfirmed_address(client):
    _user("hidden", "hidden@example.org", confirmed=False)

    client.post(reverse("username_recovery"), {"email": "hidden@example.org"}, REMOTE_ADDR="10.9.2.1")

    assert len(mail.outbox) == 0


def test_notification_email_skips_an_unconfirmed_address_but_the_notice_still_lands():
    from apps.notifications.adapter import NotificationAdapter

    u = _user("notif", "notif@example.org", confirmed=False)

    note = NotificationAdapter.send(u, "match_proposed", "Someone offered to help", "body text")

    assert len(mail.outbox) == 0
    assert note is not None, "the in-app notification must still be created"
    assert "email" not in (note.channels_sent or [])


def test_the_contact_reveal_withholds_an_unconfirmed_address():
    from tests.factories import CommunityFactory, MemberFactory

    u = _user("contact", "contact@example.org", confirmed=False)
    m = MemberFactory(user=u, community=CommunityFactory())

    info = m.contact_dict("email")

    assert "email" not in info


def test_the_contact_reveal_shares_a_confirmed_address():
    from tests.factories import CommunityFactory, MemberFactory

    u = _user("shared", "shared@example.org", confirmed=True)
    m = MemberFactory(user=u, community=CommunityFactory())

    assert m.contact_dict("email").get("email") == "shared@example.org"


# ── the guard: the sixth sender cannot forget ────────────────────────────────

# Recipients built straight from `.email`. The ONE intentional exception is the
# verification send itself: a confirmation link MUST go to the unproven address,
# because proving it is the entire point.
RAW_RECIPIENT = re.compile(r"(recipient_list|to)\s*=\s*\[[^\]]*\.email\b|\[\s*[\w.]+\.email\s*\]")
ALLOWED = {("apps/accounts/verification.py", "send_verification_email")}


def test_no_sender_builds_a_recipient_from_the_raw_address():
    """Deliberately crude. The failure it exists for is someone not knowing
    `deliverable_email` exists — not a clever bypass."""
    offenders = []
    for path in (REPO / "apps").rglob("*.py"):
        rel = path.relative_to(REPO).as_posix()
        if "/tests/" in rel or "/migrations/" in rel:
            continue
        current_def = ""
        for n, line in enumerate(path.read_text().splitlines(), 1):
            m = re.match(r"\s*def (\w+)", line)
            if m:
                current_def = m.group(1)
            if RAW_RECIPIENT.search(line) and (rel, current_def) not in ALLOWED:
                offenders.append(f"{rel}:{n} ({current_def}): {line.strip()}")

    assert offenders == [], "send to `deliverable_email`, never `.email`:\n" + "\n".join(offenders)


# ── telling people, in the place they look ──────────────────────────────────


def test_settings_says_plainly_when_the_address_is_unconfirmed(client):
    u = _user("unsure", "unsure@example.org", confirmed=False)
    client.force_login(u)

    body = client.get(reverse("account-settings")).content.decode()

    assert "Not confirmed yet" in body
    assert 'id="confirm-resend"' in body
    assert reverse("verify-send") in body


def test_settings_is_quiet_once_the_address_is_proven(client):
    u = _user("sure", "sure@example.org", confirmed=True)
    client.force_login(u)

    body = client.get(reverse("account-settings")).content.decode()

    assert "Not confirmed yet" not in body
    assert 'id="confirm-resend"' not in body
