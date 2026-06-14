"""In-app notifications (reuses apps.notifications rows; assumption A4)."""
from apps.notifications.models import Notification


def notify(user, ntype: str, title: str, body: str, link: str = ""):
    if user is None:
        return None
    return Notification.objects.create(
        recipient=user, type=ntype, title=title[:200], body=body, link=link[:500],
    )
