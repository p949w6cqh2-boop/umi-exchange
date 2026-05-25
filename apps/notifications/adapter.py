"""Notification adapter: in-app + email. SMS can be added later."""
from django.conf import settings as django_settings
from django.core.mail import send_mail

from .models import Notification


class NotificationAdapter:
    @staticmethod
    def send(recipient_user, notification_type, title, body, link=""):
        """Send notification through all enabled channels."""
        channels = ["in_app"]

        # Always create in-app notification
        Notification.objects.create(
            recipient=recipient_user,
            type=notification_type,
            title=title,
            body=body,
            link=link,
            channels_sent=channels,
        )

        # Email: send if user has an email address
        if recipient_user.email:
            try:
                send_mail(
                    subject=f"[UMI] {title}",
                    message=body,
                    from_email=django_settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[recipient_user.email],
                    fail_silently=True,
                )
                channels.append("email")
            except Exception:
                pass  # Email failure should never block the operation
