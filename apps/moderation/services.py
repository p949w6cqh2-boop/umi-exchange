"""Member moderation logic, kept thin so views stay small.

Coordinator removal must be *durable* (a removed member can't rejoin on the
same code), *reversible* (reinstate, never a delete — keyring: archive > delete),
and *complete* (their content leaves the board and their in-flight matches are
cancelled). Every action is audited (§8.3) with PII-free details.
"""

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from apps.audit.services import emit


def review_note(subject):
    """What the poster is told when a listed word flagged their text: the UI narrates its own
    restraint and names who will see it (voice rule 4)."""
    return f"{subject} uses a word on this community's review list, so a coordinator will take a look."


def flag_listed_words(target, target_type, *texts, author, request=None):
    """Put a saved post that uses a review-list word in front of the coordinators.

    The word list never refuses (founder's decision, 2026-10-12): help requests need those
    words. The post stays up, and an automatic flag (no reporter) joins the review queue; one
    open automatic flag per target, so a second note on the same match does not pile on.
    Every coordinator but the author is told, as for a member's report. Returns the listed
    word the text used (whether or not a new flag was needed), or None.
    """
    from apps.communities.models import Member
    from apps.communities.validators import find_listed_word
    from apps.notifications.adapter import NotificationAdapter

    from .models import Flag

    word = find_listed_word(*texts)
    if word is None:
        return None
    community = author.community
    try:
        # Inner atomic block: a duplicate's rollback stays contained instead of poisoning
        # the caller's transaction.
        with transaction.atomic():
            flag = Flag.objects.create(
                community=community,
                reporter=None,
                target_type=target_type,
                target_id=target.pk,
                reason="word_list",
                detail=word,
            )
    except IntegrityError:
        return word  # already waiting in the queue
    emit("flag.created", flag, request=request, details={"target_type": target_type, "automatic": True})
    for coordinator in (
        Member.objects.filter(community=community, is_active=True, role__in=("coordinator", "admin"))
        .exclude(pk=author.pk)
        .select_related("user")
    ):
        NotificationAdapter.send(
            coordinator.user,
            "flag_received",
            "A post needs a look",
            "Something on the board uses a word on the review list.",
            link=f"/c/{community.slug}/moderation/",
        )
    return word


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
        in_flight_ids = list(
            Match.objects.filter(status__in=("proposed", "accepted"))
            .filter(Q(need__requester=member) | Q(offer__offerer=member) | Q(proposed_by=member))
            .values_list("pk", flat=True)
        )
        cancelled = 0
        for pk in in_flight_ids:
            # Lock and re-read each row: the ids were listed before this loop, so a
            # match fulfilled or cancelled in between must be left alone, not
            # rewritten. (of=("self",): select_related pulls the nullable offer in
            # as an outer join, and Postgres refuses FOR UPDATE on its nullable side.)
            match = Match.objects.select_for_update(of=("self",)).select_related("need", "offer").get(pk=pk)
            if match.status not in ("proposed", "accepted"):
                continue
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
