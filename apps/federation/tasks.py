"""
django-q2 scheduled tasks for federation inbound discovery (Stage B slice 2).
Both are no-ops when federation is disabled. Register with:
  python manage.py shell -c "from apps.federation.tasks import register_schedule; register_schedule()"
"""

from django.conf import settings
from django.utils import timezone


def poll_all_active_links() -> int:
    """Poll every active link's peer feed. Per-link failures are isolated
    (a dead peer never blocks the others). Returns total live rows."""
    if not getattr(settings, "FEDERATION_ENABLED", False):
        return 0
    from .models import FederationLink
    from .polling import poll_link

    total = 0
    for link in FederationLink.objects.filter(status="active").select_related("peer"):
        try:
            total += poll_link(link)
        except Exception:  # noqa: BLE001  # nosec B112 — one bad peer must not abort the sweep
            continue
    return total


def sweep_expired_shadows() -> int:
    """Delete inbound shadows past their TTL (§4.4). They carry no PII, so a
    bulk delete is appropriate; nothing durable is lost."""
    from .models import ShadowListing

    deleted, _ = ShadowListing.objects.filter(expires_at__lt=timezone.now()).delete()
    return deleted


def deliver_pending_events() -> int:
    """Stage C2 outbox pump (§6.3): deliver due match events with backoff.
    No-op when federation is off — nothing leaves the instance."""
    if not getattr(settings, "FEDERATION_ENABLED", False):
        return 0
    from .outbox import deliver_due_events

    return deliver_due_events()


def sweep_expired_contacts() -> int:
    """Shred exchanged contact payloads past their post-terminal grace (§4.4).
    Deliberately NOT flag-gated: retention is a privacy guarantee and must
    still run if federation is switched off with payloads at rest."""
    from .outbox import sweep_expired_contacts as _sweep

    return _sweep()


def register_schedule():
    from django_q.models import Schedule

    Schedule.objects.update_or_create(
        name="federation-poll-discovery",
        defaults={
            "func": "apps.federation.tasks.poll_all_active_links",
            "schedule_type": Schedule.MINUTES,
            "minutes": 15,
            "repeats": -1,
        },
    )
    Schedule.objects.update_or_create(
        name="federation-sweep-shadows",
        defaults={
            "func": "apps.federation.tasks.sweep_expired_shadows",
            "schedule_type": Schedule.DAILY,
            "repeats": -1,
        },
    )
    Schedule.objects.update_or_create(
        name="federation-deliver-events",
        defaults={
            "func": "apps.federation.tasks.deliver_pending_events",
            "schedule_type": Schedule.MINUTES,
            "minutes": 1,
            "repeats": -1,
        },
    )
    Schedule.objects.update_or_create(
        name="federation-sweep-contacts",
        defaults={
            "func": "apps.federation.tasks.sweep_expired_contacts",
            "schedule_type": Schedule.DAILY,
            "repeats": -1,
        },
    )
