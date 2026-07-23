"""
Need expiration task — runs hourly via Django-Q2.
UMI Protocol Section 4.1: Needs past expiration with no accepted match are expired.
CRITICAL: Needs with at least one accepted match MUST NOT expire.

Register once (mirrors apps/casework, apps/matches, apps/federation):
    python manage.py shell -c "from apps.needs.tasks import register_schedule; register_schedule()"
"""

from django.utils import timezone

from apps.audit.models import AuditLog
from apps.audit.services import emit
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

        # Expire proposed matches individually so each leaves an audit entry
        # (§8.3) — was a silent bulk .update() that bypassed the audit trail.
        for m in need.matches.filter(status="proposed"):
            m.status = "expired"
            m.save(update_fields=["status"])
            emit("match.expired", m, details={"reason": "need_expired"})

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


def register_schedule():
    """Register the hourly need-expiry sweep (H-3). expire_stale_needs existed
    and was tested but nothing scheduled it, unlike every sibling task module —
    so no deployment ran it and past-due needs stayed 'open' forever. HOURLY
    matches the module docstring's stated cadence."""
    from django_q.models import Schedule

    Schedule.objects.update_or_create(
        name="needs-shred-aged-pii",
        defaults={
            "func": "apps.needs.tasks.shred_aged_need_pii",
            "schedule_type": Schedule.DAILY,
            "repeats": -1,
        },
    )
    Schedule.objects.update_or_create(
        name="needs-expire-stale",
        defaults={
            "func": "apps.needs.tasks.expire_stale_needs",
            "schedule_type": Schedule.HOURLY,
            "repeats": -1,
        },
    )


# Retention policy (Jasiah Williams's yes, 2026-07-11): terminal needs keep their
# encrypted on-behalf-of name for one year, then it is crypto-shredded.
NEED_PII_RETENTION_DAYS = 365


def shred_aged_need_pii():
    """Null BOTH envelope columns on aged terminal needs.

    Nulling ciphertext and DEK together (not DEK alone) keeps reads returning
    None instead of the fail-loud ciphertext-without-DEK state, and keeps
    `migrate_on_behalf_envelope --verify`'s unreadable count at zero.
    Idempotent: a shredded row no longer matches the dek filter. Each row is
    audited (§8.3) with PII-free details.
    """
    from datetime import timedelta

    cutoff = timezone.now() - timedelta(days=NEED_PII_RETENTION_DAYS)
    aged = Need.objects.filter(
        status__in=("fulfilled", "closed", "expired"),
        updated_at__lt=cutoff,
        on_behalf_of_dek__isnull=False,
    )
    count = 0
    for need in aged:
        Need.objects.filter(pk=need.pk).update(on_behalf_of=None, on_behalf_of_dek=None)
        emit("need.pii_shredded", need, details={"policy": f"retention_{NEED_PII_RETENTION_DAYS}d"})
        count += 1
    return f"Shredded on-behalf-of PII for {count} aged needs"
