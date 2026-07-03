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
