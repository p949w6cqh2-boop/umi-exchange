"""P7 — real notification delivery over SMTP, consented per user.

The adapter was already wired for email; these pin the two things that make
it safe to turn on: it actually sends to a willing recipient, and it never
sends to one who opted out. Backend is Django's in-memory outbox here — the
same code path a real SMTP backend runs."""

import pytest
from django.core import mail
from django.test import Client, override_settings
from django.urls import reverse

from apps.notifications.adapter import NotificationAdapter
from tests.conftest import UserFactory

pytestmark = pytest.mark.django_db

MEMORY_BACKEND = "django.core.mail.backends.locmem.EmailBackend"


@override_settings(EMAIL_BACKEND=MEMORY_BACKEND)
def test_email_sent_to_a_willing_recipient():
    user = UserFactory(email="maria@example.org")
    user.email_notifications = True
    user.save()
    mail.outbox.clear()
    note = NotificationAdapter.send(user, "match_proposed", "A neighbour offered", "Come see.", link="/x/")
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["maria@example.org"]
    assert "A neighbour offered" in mail.outbox[0].subject
    assert "email" in note.channels_sent


@override_settings(EMAIL_BACKEND=MEMORY_BACKEND)
def test_no_email_when_opted_out_but_in_app_still_lands():
    user = UserFactory(email="sam@example.org")
    user.email_notifications = False
    user.save()
    mail.outbox.clear()
    note = NotificationAdapter.send(user, "match_proposed", "A neighbour offered", "Come see.")
    assert len(mail.outbox) == 0  # respected
    assert note.pk is not None  # in-app notification still created
    assert "email" not in note.channels_sent


@override_settings(EMAIL_BACKEND=MEMORY_BACKEND)
def test_no_email_without_an_address():
    user = UserFactory(email=None)
    mail.outbox.clear()
    NotificationAdapter.send(user, "match_proposed", "t", "b")
    assert len(mail.outbox) == 0


def test_member_can_opt_out_from_settings():
    user = UserFactory(email="pat@example.org")
    assert user.email_notifications is True
    client = Client()
    client.force_login(user)
    resp = client.post(
        reverse("account-settings"),
        {"email": "pat@example.org", "phone": "", "email_notifications": ""},  # unchecked
    )
    assert resp.status_code in (200, 302)
    user.refresh_from_db()
    assert user.email_notifications is False
