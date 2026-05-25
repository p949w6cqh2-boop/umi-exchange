"""
Need expiration task — runs hourly via Django-Q2.
UMI Protocol Section 4.1: Needs past expiration with no accepted match are expired.
CRITICAL: Needs with at least one accepted match MUST NOT expire.
"""
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.notifications.adapter import NotificationAdapter

from .models import Need


def expire_stale_needs():
    """Expire open needs past their expiration date (without accepted matches)."""
    now = timezone.now()
    expirable = Need.objects.filter(
        status="open",
        expires_at__lt=now,
    ).exclude(
        matches__status="accepted"  # Protocol Section 4.1: MUST NOT expire with accepted match
    )

    count = 0
    for need in expirable:
        need.status = "expired"
        need.save(update_fields=["status", "updated_at"])

        # Cancel all proposed matches on this need
        need.matches.filter(status="proposed").update(status="expired")

        # Notify requester
        NotificationAdapter.send(
            need.requester.user,
            "need_expired",
            f'Your need "{need.title}" has expired.',
            "You can repost it if you still need help.",
            link=need.get_absolute_url(),
        )

        AuditLog.log(None, "update", "need", need.id, details={"status": ["open", "expired"]})
        count += 1

    return f"Expired {count} needs"
