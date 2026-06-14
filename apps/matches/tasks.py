"""
§10.6 — expire stale match proposals (django-q2, daily).

Opt-in per community: an admin sets
    community.settings["match_expiry_days"] = 14
and proposals older than that window flip to "expired" with an audit row
and a notification to the proposer. Communities without the key are never
touched. Register once:

    python manage.py shell -c "from apps.matches.tasks import register_schedule; register_schedule()"

Field names follow the Lake 1 model (need, proposed_by, proposed_at,
status) — if yours drifted, the tests in
apps/casework/tests/test_s10_improvements.py will fail first and loudest.
"""
import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.audit.services import emit
from apps.matches.models import Match
from apps.notifications.models import Notification

logger = logging.getLogger(__name__)

SETTING_KEY = "match_expiry_days"


def expire_stale_proposals() -> int:
    """Returns the number of proposals expired in this run. Idempotent:
    a second run finds nothing still in 'proposed'."""
    from apps.communities.models import Community

    expired = 0
    for community in Community.objects.filter(is_active=True).iterator():
        days = (community.settings or {}).get(SETTING_KEY)
        try:
            days = int(days)
        except (TypeError, ValueError):
            continue  # opt-in only; absent/invalid setting = untouched
        if days <= 0:
            continue

        cutoff = timezone.now() - timedelta(days=days)
        stale_ids = list(
            Match.objects.filter(status="proposed",
                                 proposed_at__lt=cutoff,
                                 need__community=community)
            .values_list("pk", flat=True))

        for pk in stale_ids:
            with transaction.atomic():
                match = (Match.objects.select_for_update()
                         .select_related("need", "proposed_by__user")
                         .get(pk=pk))
                if match.status != "proposed":
                    continue  # accepted/cancelled while we were sweeping
                match.status = "expired"
                match.save(update_fields=["status"])

            emit("match.expired", match, details={"after_days": days})

            proposer = getattr(match.proposed_by, "user", None)
            if proposer is not None:
                try:
                    Notification.objects.create(
                        recipient=proposer, type="match_expired",
                        title="A match proposal expired",
                        body=(f"Your proposal on “{match.need.title}” went "
                              f"{days} days without acceptance and has "
                              f"expired. Re-propose it if it's still on."),
                        link=f"/c/{community.slug}/")
                except Exception:  # notifications must never break the sweep
                    logger.exception("match expiry notification failed")
            expired += 1

    return expired


def register_schedule():
    from django_q.models import Schedule
    Schedule.objects.update_or_create(
        name="matches-expiry-sweep",
        defaults={"func": "apps.matches.tasks.expire_stale_proposals",
                  "schedule_type": Schedule.DAILY, "repeats": -1},
    )
