"""Offer expiry (spec §10.6: "Needs and offers MUST expire on a schedule").

Offers carried an expires_at (90 days) that nothing read, so they never left the board (2026-10
bug hunt, L28). The sweep is registered with the needs sweeps (apps.needs.tasks.register_schedule),
so a deployment that already runs that step picks it up.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.audit.services import emit
from apps.notifications.adapter import NotificationAdapter

from .models import Offer


def expire_stale_offers():
    """Expire active offers past their date, then their proposals still waiting on an answer."""
    from apps.matches.models import Match
    from apps.needs.models import Need

    now = timezone.now()
    candidate_ids = list(Offer.objects.filter(status="active", expires_at__lt=now).values_list("pk", flat=True))
    count = 0
    for pk in candidate_ids:
        with transaction.atomic():
            # Locked and re-read: an offer matched or withdrawn since the list was taken is left alone.
            offer = Offer.objects.select_for_update().filter(pk=pk).select_related("offerer__user", "community").first()
            if offer is None or offer.status != "active" or offer.expires_at >= now:
                continue
            offer.status = "expired"
            offer.save(update_fields=["status", "updated_at"])
            emit("offer.updated", offer, details={"status": ["active", "expired"]})
        # Each proposal in its own transaction, Need then Match: the lock order every match write
        # takes. A proposal accepted a moment ago is no longer "proposed", so it is left as it is.
        for match_id, need_id in offer.matches.filter(status="proposed").order_by("pk").values_list("pk", "need_id"):
            with transaction.atomic():
                Need.objects.select_for_update().filter(pk=need_id).first()
                match = Match.objects.select_for_update(of=("self",)).filter(pk=match_id).first()
                if match is None or match.status != "proposed":
                    continue
                try:
                    match.transition_to("expired")
                except ValidationError:  # TransitionConflict subclasses it: the match moved meanwhile
                    continue
                emit("match.expired", match, details={"reason": "offer_expired"})
        if offer.offerer.is_active:  # not someone who left: the link would 404 for them
            NotificationAdapter.send(
                offer.offerer.user,
                "offer_expired",
                f'Your offer "{offer.title}" has expired.',
                "You can post it again if you can still help.",
                link=f"/c/{offer.community.slug}/offers/{offer.pk}/",
            )
        count += 1
    return f"Expired {count} offers"
