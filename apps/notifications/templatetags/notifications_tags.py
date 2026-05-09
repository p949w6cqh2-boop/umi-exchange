from django import template
from apps.notifications.models import Notification

register = template.Library()

@register.simple_tag
def unread_count(user):
    """Return unread notification count for the given user."""
    if not user or not user.is_authenticated:
        return 0
    return Notification.objects.filter(recipient=user, is_read=False).count()
