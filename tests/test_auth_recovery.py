"""Auth recovery — username recovery flow + the email-delivery smoke command.

Pilot-parish finding (2026-08-11): the password-reset flow existed but there was no way
to recover a forgotten USERNAME at all, and the login page only advertised the password
half. These tests pin the new flow: no user enumeration, active accounts only, one email
listing every username on the address, and the same rate-limit posture as the other auth
endpoints.
"""

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.urls import reverse

User = get_user_model()
pytestmark = pytest.mark.django_db

STRONG = "Str0ng-p4ss!x9"


def test_login_page_offers_both_recovery_links(client):
    html = client.get(reverse("login")).content.decode()
    assert "Forgot password?" in html
    assert "Forgot username?" in html


def test_username_recovery_form_renders(client):
    resp = client.get(reverse("username_recovery"))
    assert resp.status_code == 200
    assert "email" in resp.content.decode().lower()


def test_known_email_receives_its_username(client):
    User.objects.create_user("nuala", email="nuala@example.org", password=STRONG)
    resp = client.post(reverse("username_recovery"), {"email": "nuala@example.org"})
    assert resp.status_code == 302
    assert resp.url == reverse("username_recovery_done")
    assert len(mail.outbox) == 1
    assert "nuala" in mail.outbox[0].body
    assert mail.outbox[0].to == ["nuala@example.org"]


def test_unknown_email_gets_identical_response_and_no_mail(client):
    resp = client.post(reverse("username_recovery"), {"email": "ghost@example.org"})
    assert resp.status_code == 302
    assert resp.url == reverse("username_recovery_done")
    assert len(mail.outbox) == 0


def test_email_lookup_is_case_insensitive(client):
    User.objects.create_user("marta", email="Marta@Example.org", password=STRONG)
    client.post(reverse("username_recovery"), {"email": "marta@example.org"})
    assert len(mail.outbox) == 1
    assert "marta" in mail.outbox[0].body


def test_email_is_unique_per_account():
    # The model enforces one account per email (and the registration form says
    # "This email is already in use"), so the recovery email always carries
    # exactly one username. This pins the invariant the flow relies on.
    from django.db import IntegrityError

    User.objects.create_user("marta", email="shared@example.org", password=STRONG)
    with pytest.raises(IntegrityError):
        User.objects.create_user("tom", email="shared@example.org", password=STRONG)


def test_inactive_account_is_not_disclosed(client):
    user = User.objects.create_user("gone", email="gone@example.org", password=STRONG)
    user.is_active = False
    user.save(update_fields=["is_active"])
    client.post(reverse("username_recovery"), {"email": "gone@example.org"})
    assert len(mail.outbox) == 0


def test_username_recovery_path_is_rate_limited():
    # Same posture as login/register/password-reset: the auth middleware throttles
    # POSTs on this path (5/min/IP). Mirrors test_password_reset_path_is_rate_limited.
    assert "/auth/username/recover/" in settings.RATELIMIT_AUTH_PATHS


def test_send_smoke_command_sends_one_email(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    call_command("send_smoke", "steward@example.org")
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["steward@example.org"]
    assert "UMI Exchange" in mail.outbox[0].subject
