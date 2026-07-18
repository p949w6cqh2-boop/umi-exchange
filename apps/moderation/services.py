"""Member moderation logic, kept thin so views stay small.

Coordinator removal must be *durable* (a removed member can't rejoin on the
same code), *reversible* (reinstate, never a delete — keyring: archive > delete),
and *complete* (their content leaves the board and their in-flight matches are
cancelled). Every action is audited (§8.3) with PII-free details.
"""

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.audit.services import emit


def is_blocked_between(member_a, member_b):
    """True if either neighbour has blocked the other. Enforcement is symmetric:
    a single directed Block stops interaction both ways."""
    from .models import Block

    return Block.objects.filter(Q(blocker=member_a, blocked=member_b) | Q(blocker=member_b, blocked=member_a)).exists()


def blocked_member_ids(member):
    """The set of Member ids `member` is blocked-with, in either direction.
    Used to filter feeds and lists in one query rather than per-row checks."""
    from .models import Block

    made = Block.objects.filter(blocker=member).values_list("blocked_id", flat=True)
    got = Block.objects.filter(blocked=member).values_list("blocker_id", flat=True)
    return set(made) | set(got)


def remove_member(member, *, by, request=None):
    """Durably remove `member` from their community.

    Deactivates the membership, stamps who/when, takes their still-open needs
    and active offers off the board (reversible hide), and cancels every
    in-flight match they are a party to (which re-opens the counterpart's need
    or offer). Returns the audited counts.
    """
    from apps.matches.models import Match
    from apps.needs.models import Need
    from apps.offers.models import Offer

    with transaction.atomic():
        # In-flight matches where this member is any party → cancel. Cancelling
        # from "accepted" re-opens the counterpart's need/offer (see Match.transition_to).
        in_flight = (
            Match.objects.filter(status__in=("proposed", "accepted"))
            .filter(Q(need__requester=member) | Q(offer__offerer=member) | Q(proposed_by=member))
            .select_related("need", "offer")
        )
        cancelled = 0
        for match in in_flight:
            match.transition_to("cancelled")
            cancelled += 1

        needs_hidden = Need.objects.filter(requester=member, status="open", moderation_hidden=False).update(
            moderation_hidden=True
        )
        offers_hidden = Offer.objects.filter(offerer=member, status="active", moderation_hidden=False).update(
            moderation_hidden=True
        )

        member.is_active = False
        member.removed_at = timezone.now()
        member.removed_by = by
        member.save(update_fields=["is_active", "removed_at", "removed_by"])

    emit(
        "member.removed",
        member,
        user=by.user,
        request=request,
        details={
            "matches_cancelled": cancelled,
            "needs_hidden": needs_hidden,
            "offers_hidden": offers_hidden,
        },
    )
    return {"matches_cancelled": cancelled, "needs_hidden": needs_hidden, "offers_hidden": offers_hidden}


def reinstate_member(member, *, by, request=None):
    """Reverse a removal: re-activate the membership, clear the removal stamp,
    and put their still-open content back on the board.

    Note: this unhides their open needs / active offers. If a single item had
    also been hidden by a separate content flag, reinstating the member unhides
    it too — the `moderation_hidden` boolean does not distinguish who hid it. A
    coordinator can re-hide that one item from the queue.
    """
    from apps.needs.models import Need
    from apps.offers.models import Offer

    with transaction.atomic():
        Need.objects.filter(requester=member, status="open", moderation_hidden=True).update(moderation_hidden=False)
        Offer.objects.filter(offerer=member, status="active", moderation_hidden=True).update(moderation_hidden=False)
        member.is_active = True
        member.removed_at = None
        member.removed_by = None
        member.save(update_fields=["is_active", "removed_at", "removed_by"])

    emit("member.reinstated", member, user=by.user, request=request, details={})
