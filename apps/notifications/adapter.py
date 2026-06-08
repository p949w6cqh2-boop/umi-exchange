"""
Notification adapter: in-app + email. SMS can be added later.

Channels:
  - in_app: Always created (Notification model)
  - email:  Sent if user has an email address and EMAIL_BACKEND is configured

The adapter never blocks the calling operation — email failures are logged
but silently caught so that a misconfigured SMTP server does not prevent
a match from being accepted or a need from being posted.
"""

import logging

from django.conf import settings as django_settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

from .models import Notification

logger = logging.getLogger(__name__)


class NotificationAdapter:
    @staticmethod
    def send(recipient_user, notification_type, title, body, link=""):
        """Send notification through all enabled channels.

        Args:
            recipient_user: User instance (the recipient)
            notification_type: str — e.g. "match_proposed", "match_accepted", "need_expired"
            title: str — short notification title
            body: str — notification body text
            link: str — optional relative URL to the relevant page
        """
        channels_sent = ["in_app"]

        # 1. Always create in-app notification
        notification = Notification.objects.create(
            recipient=recipient_user,
            type=notification_type,
            title=title,
            body=body,
            link=link,
            channels_sent=channels_sent,
        )

        # 2. Email: send if user has an email address
        if recipient_user.email:
            email_sent = NotificationAdapter._send_email(recipient_user, title, body, link)
            if email_sent:
                channels_sent.append("email")
                notification.channels_sent = channels_sent
                notification.save(update_fields=["channels_sent"])

        return notification

    @staticmethod
    def _send_email(recipient_user, title, body, link=""):
        """Send email notification. Returns True on success, False on failure."""
        try:
            # Build absolute URL for the link
            site_url = getattr(django_settings, "SITE_URL", "http://localhost:8000")
            absolute_link = f"{site_url.rstrip('/')}{link}" if link else ""

            # Plain text body
            text_body = body
            if absolute_link:
                text_body += f"\n\nView: {absolute_link}"

            # Try to render HTML template; fall back to plain text
            html_body = None
            try:
                html_body = render_to_string(
                    "emails/notification.html",
                    {
                        "title": title,
                        "body": body,
                        "link": absolute_link,
                        "recipient": recipient_user,
                        "site_url": site_url,
                    },
                )
            except Exception:
                pass  # HTML template not found; plain text only

            # Send
            email = EmailMultiAlternatives(
                subject=f"[UMI] {title}",
                body=text_body,
                from_email=django_settings.DEFAULT_FROM_EMAIL,
                to=[recipient_user.email],
            )
            if html_body:
                email.attach_alternative(html_body, "text/html")

            email.send(fail_silently=False)
            logger.info(
                "Email sent to %s for notification type=%s",
                recipient_user.email,
                "notification",
            )
            return True

        except Exception as e:
            logger.warning(
                "Email failed for user %s: %s",
                recipient_user.pk,
                str(e),
            )
            return False
