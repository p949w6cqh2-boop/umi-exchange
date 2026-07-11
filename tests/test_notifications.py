"""
Email and notification tests.
"""

import pytest
from django.core import mail
from django.test import override_settings

from apps.notifications.adapter import NotificationAdapter
from apps.notifications.models import Notification
from tests.factories import UserFactory


@pytest.mark.django_db
class TestNotificationAdapter:
    """Test the NotificationAdapter send method."""

    def test_creates_in_app_notification(self):
        user = UserFactory()
        notification = NotificationAdapter.send(user, "test_type", "Test Title", "Test body text")
        assert notification is not None
        assert notification.title == "Test Title"
        assert notification.body == "Test body text"
        assert notification.type == "test_type"
        assert notification.recipient == user
        assert "in_app" in notification.channels_sent
        assert Notification.objects.filter(recipient=user).count() == 1

    def test_creates_notification_with_link(self):
        user = UserFactory()
        notification = NotificationAdapter.send(user, "test_type", "Title", "Body", link="/community/test/")
        assert notification.link == "/community/test/"

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_sends_email_when_user_has_email(self):
        user = UserFactory(email="test@example.com")
        notification = NotificationAdapter.send(user, "match_accepted", "Match Accepted", "Your match was accepted!")
        # Check email was sent
        assert len(mail.outbox) == 1
        sent_email = mail.outbox[0]
        assert sent_email.to == ["test@example.com"]
        assert "[UMI] Match Accepted" in sent_email.subject
        assert "Your match was accepted!" in sent_email.body
        # Check channels_sent was updated
        notification.refresh_from_db()
        assert "email" in notification.channels_sent

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_no_email_when_user_has_no_email(self):
        user = UserFactory(email="")
        NotificationAdapter.send(user, "test_type", "Title", "Body")
        assert len(mail.outbox) == 0

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_email_includes_link(self):
        user = UserFactory(email="link@example.com")
        NotificationAdapter.send(
            user, "match_proposed", "New Match", "Someone proposed a match.", link="/community/test/matches/123/"
        )
        assert len(mail.outbox) == 1
        assert "/community/test/matches/123/" in mail.outbox[0].body

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_multiple_notifications_send_multiple_emails(self):
        user = UserFactory(email="multi@example.com")
        NotificationAdapter.send(user, "type_a", "First", "Body 1")
        NotificationAdapter.send(user, "type_b", "Second", "Body 2")
        assert len(mail.outbox) == 2
        assert Notification.objects.filter(recipient=user).count() == 2


@pytest.mark.django_db
class TestNotificationModel:
    def test_notification_defaults_to_unread(self):
        user = UserFactory()
        n = Notification.objects.create(
            recipient=user,
            type="test",
            title="Test",
            body="Body",
        )
        assert n.is_read is False

    def test_notification_mark_read(self):
        user = UserFactory()
        n = Notification.objects.create(
            recipient=user,
            type="test",
            title="Test",
            body="Body",
        )
        n.is_read = True
        n.save()
        n.refresh_from_db()
        assert n.is_read is True


@pytest.mark.django_db
class TestEmailBrandPalette:
    """Overhaul phase 6: the HTML email carries the Commons palette as inline
    hex constants (CSS vars don't exist in mail clients) — evergreen header/
    button, warm ink, stone background. The old pre-Commons green and cool
    zinc grays must be gone."""

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def _html(self):
        user = UserFactory(email="palette@example.com")
        NotificationAdapter.send(user, "match_accepted", "Title", "Body", link="/c/x/")
        assert len(mail.outbox) == 1
        alternatives = mail.outbox[0].alternatives
        assert alternatives, "HTML alternative missing"
        return alternatives[0][0]

    def test_email_on_commons_palette(self):
        html = self._html()
        assert "#275D4C" in html  # evergreen header + button
        assert "#2C2A29" in html  # espresso ink headline

    def test_email_sheds_old_brand(self):
        html = self._html()
        for old in ("#166534", "#18181b", "#3f3f46", "#a1a1aa", "#f4f4f5", "#e4e4e7"):
            assert old not in html, f"old palette hex {old} still in email"
