"""Batch-5 regression (2026-10 bug hunt, account email).

1. An add-email link stayed valid after a newer address was confirmed, and replaced it: a link
   to a mistyped inbox, opened later, took the account's recovery address back to that inbox.
   A link is now bound to the account's email state when it was sent.
2. Asking to change your email sent mail to any address with no limit, and a mail failure gave
   a 500 on only the branches that send, so an SMTP outage told anyone whether an address was
   registered (settings, username recovery, registration).
"""

import smtplib

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.verification import make_add_email_token

User = get_user_model()
pytestmark = pytest.mark.django_db
STRONG = "Str0ng-p4ss!x9"


@pytest.fixture(autouse=True)
def _clean(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.RATELIMIT_ENABLED = False
    cache.clear()


@pytest.fixture
def no_email_user():
    return User.objects.create_user(username="nomail", password=STRONG, email=None)


def _confirm(token):
    return Client().get(reverse("account-confirm-email", args=[token]))


# ── 1. An old link cannot replace a newer confirmed address ──


def test_an_older_link_cannot_replace_the_address_confirmed_after_it(no_email_user):
    typo = make_add_email_token(no_email_user, "maria@gmial.com")
    right = make_add_email_token(no_email_user, "maria@gmail.com")

    _confirm(right)
    _confirm(typo)

    no_email_user.refresh_from_db()
    assert no_email_user.email == "maria@gmail.com"


def test_a_used_link_cannot_revert_a_later_change(no_email_user):
    first = make_add_email_token(no_email_user, "old@example.org")
    _confirm(first)
    no_email_user.refresh_from_db()
    second = make_add_email_token(no_email_user, "new@example.org")
    _confirm(second)

    _confirm(first)

    no_email_user.refresh_from_db()
    assert no_email_user.email == "new@example.org"


def test_a_single_fresh_link_still_confirms(no_email_user):
    _confirm(make_add_email_token(no_email_user, "fresh@example.org"))
    no_email_user.refresh_from_db()
    assert no_email_user.email == "fresh@example.org"
    assert no_email_user.email_confirmed_at is not None


# ── 2. Email changes are limited, and a mail failure never shows ──


def _settings_post(client, email, phone=""):
    # A change of address takes the current password (2026-10 bug hunt, L48).
    return client.post(reverse("account-settings"), {"email": email, "phone": phone, "current_password": STRONG})


def test_email_change_requests_are_limited_per_account(settings, no_email_user):
    settings.RATELIMIT_ENABLED = True
    client = Client()
    client.force_login(no_email_user)

    codes = [_settings_post(client, f"addr{i}@example.org").status_code for i in range(12)]

    assert all(c == 302 for c in codes)
    assert len(mail.outbox) == 10
    # Saving a phone number is not an email change and is never held back by it.
    assert _settings_post(client, "", phone="555-0100").status_code == 302


@pytest.fixture
def failing_mail(monkeypatch):
    def boom(self, messages):
        raise smtplib.SMTPException("relay refused")

    monkeypatch.setattr("django.core.mail.backends.locmem.EmailBackend.send_messages", boom)


def test_settings_answer_the_same_for_a_free_and_a_taken_address_when_mail_fails(failing_mail, no_email_user):
    User.objects.create_user(username="owner", password=STRONG, email="taken@example.org")
    client = Client()
    client.force_login(no_email_user)
    assert _settings_post(client, "taken@example.org").status_code == 302
    assert _settings_post(client, "free@example.org").status_code == 302


def test_username_recovery_answers_the_same_when_mail_fails(failing_mail):
    User.objects.create_user(
        username="known", password=STRONG, email="known@example.org", email_confirmed_at=timezone.now()
    )
    url = reverse("username_recovery")
    known = Client().post(url, {"email": "known@example.org"}, REMOTE_ADDR="10.9.0.1")
    unknown = Client().post(url, {"email": "nobody@example.org"}, REMOTE_ADDR="10.9.0.2")
    assert known.status_code == unknown.status_code == 302
