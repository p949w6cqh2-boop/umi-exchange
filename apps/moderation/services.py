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


def _cancel_in_flight_matches(member):
    """Cancel every proposed or accepted match `member` is a party to, and return them.

    Cancelling from accepted re-opens the counterpart's need or offer (Match.transition_to).
    Each match is locked Need first, the order MatchUpdateView and the hourly sweep take, and
    re-read under its lock: the ids were listed before the loop, so a match fulfilled or
    cancelled in between is left alone, not rewritten. (of=("self",): select_related pulls
    the nullable offer in as an outer join, and Postgres refuses FOR UPDATE on its nullable
    side.) Call it inside a transaction.
    """
    from apps.federation import mirror, outbox
    from apps.federation.models import FederatedMatch
    from apps.matches.models import Match
    from apps.needs.models import Need

    in_flight = list(
        Match.objects.filter(status__in=("proposed", "accepted"))
        .filter(Q(need__requester=member) | Q(offer__offerer=member) | Q(proposed_by=member))
        .order_by("pk")
        .values_list("pk", "need_id")
    )
    cancelled = []
    for pk, need_id in in_flight:
        Need.objects.select_for_update().get(pk=need_id)
        match = Match.objects.select_for_update(of=("self",)).select_related("need", "offer").get(pk=pk)
        if match.status not in ("proposed", "accepted"):
            continue
        match.transition_to("cancelled")
        # A federated match tells its peer and arms the contact-retention shred; a no-op for a
        # local match or with federation off (2026-10 bug hunt #17).
        outbox.queue_match_event(match, "cancelled")
        cancelled.append(match)
    # Where they are the helper on another instance's ask, ask that authority to cancel.
    for fmatch in FederatedMatch.objects.filter(role="mirror", offer__offerer=member).exclude(
        mirror_status__in=mirror.MIRROR_TERMINAL
    ):
        outbox.queue_cancel_request(fmatch)
    return cancelled


def leave_community(member, *, request=None):
    """A member's own choice to leave (founder's decision 2026-10-12, bug hunt #8).

    Leaving used to withdraw nothing: their asks stayed on the board, neighbours proposed on
    them, and they were emailed links that 404. Now it deactivates the membership, cancels the
    matches still in progress (nobody could answer them; each other person is told), and takes
    their open asks and active offers off the board: hidden, never deleted, and stamped
    hidden_on_leave_at, so that coming back reposts nothing until they choose (LeftPostsView).
    Unlike a removal there is no removal stamp: they can rejoin with the code. Returns the
    audited counts. Raises LastAdminError, changing nothing, for the community's last admin.
    """
    from apps.communities.models import LastAdminError, Member, lock_admin_seats
    from apps.needs.models import Need
    from apps.notifications.adapter import NotificationAdapter
    from apps.offers.models import Offer

    now = timezone.now()
    with transaction.atomic():
        # The last-admin check and the leave are one step under the community's lock (2026-10 bug
        # hunt, L2): checked outside it, two admins leaving at once both passed and left none.
        lock_admin_seats(member.community_id)
        member = Member.objects.select_related("community", "user").get(pk=member.pk)
        if not member.is_active:  # a double tap: the first one already left
            return {"matches_cancelled": 0, "needs_hidden": 0, "offers_hidden": 0}
        if member.is_last_active_admin:
            raise LastAdminError
        cancelled = _cancel_in_flight_matches(member)
        needs_hidden = Need.objects.filter(requester=member, status="open", moderation_hidden=False).update(
            moderation_hidden=True, hidden_on_leave_at=now
        )
        # "matched" too: an offer held by a match on another instance comes back to active when
        # that authority's cancel arrives, and must not reappear on the board then.
        offers_hidden = Offer.objects.filter(
            offerer=member, status__in=("active", "matched"), moderation_hidden=False
        ).update(moderation_hidden=True, hidden_on_leave_at=now)
        member.is_active = False
        member.save(update_fields=["is_active"])

    counts = {"matches_cancelled": len(cancelled), "needs_hidden": needs_hidden, "offers_hidden": offers_hidden}
    emit("member.left", member, user=member.user, request=request, details={"role": member.role, **counts})
    slug = member.community.slug
    for match in cancelled:
        for other in {match.need.requester, match.helper_member} - {member}:
            NotificationAdapter.send(
                other.user,
                "match_cancelled",
                f"Match on '{match.need.title}' was cancelled",
                "Open the match to see where things stand.",
                link=f"/c/{slug}/matches/{match.id}/",
            )
    return counts


def remove_member(member, *, by, request=None):
    """Durably remove `member` from their community.

    Deactivates the membership, stamps who/when, takes their still-open needs
    and active offers off the board (reversible hide), and cancels every
    in-flight match they are a party to (which re-opens the counterpart's need
    or offer). Returns the audited counts.
    """
    from apps.needs.models import Need
    from apps.offers.models import Offer

    with transaction.atomic():
        cancelled = len(_cancel_in_flight_matches(member))

        needs_hidden = Need.objects.filter(requester=member, status="open", moderation_hidden=False).update(
            moderation_hidden=True
        )
        offers_hidden = Offer.objects.filter(
            offerer=member, status__in=("active", "matched"), moderation_hidden=False
        ).update(moderation_hidden=True)

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
    coordinator can re-hide that one item from the queue. What their own leaving
    hid (hidden_on_leave_at) stays hidden: that is theirs to put back.
    """
    from apps.needs.models import Need
    from apps.offers.models import Offer

    with transaction.atomic():
        Need.objects.filter(
            requester=member, status="open", moderation_hidden=True, hidden_on_leave_at__isnull=True
        ).update(moderation_hidden=False)
        Offer.objects.filter(
            offerer=member, status="active", moderation_hidden=True, hidden_on_leave_at__isnull=True
        ).update(moderation_hidden=False)
        member.is_active = True
        member.removed_at = None
        member.removed_by = None
        member.save(update_fields=["is_active", "removed_at", "removed_by"])

    emit("member.reinstated", member, user=by.user, request=request, details={})
