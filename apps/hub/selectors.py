"""Read-only, bounded query helpers for the hub — the only place hub touches the ORM."""

from django.db.models import Q

from apps.communities.models import Member
from apps.matches.models import Match
from apps.tags.models import MemberTag

OPEN_MATCH_STATUSES = ("proposed", "accepted")
OPEN_MATCHES_CAP = 50
RECENT_NOTIFICATIONS_CAP = 8


def member_communities(user):
    """The user's active memberships in active communities, newest first.

    Filters `community__is_active` to match HubResolverView, so the switcher
    never lists a deactivated community that would 404 on click.
    """
    return list(
        Member.objects.filter(user=user, is_active=True, community__is_active=True)
        .select_related("community")
        .order_by("-joined_at")
    )


def open_matches_for(member):
    """Non-terminal matches in the member's focused community where they're a
    participant (requester, offerer, or proposer). Bounded, newest first."""
    return list(
        Match.objects.filter(
            Q(need__requester=member) | Q(offer__offerer=member) | Q(proposed_by=member),
            need__community=member.community,
            status__in=OPEN_MATCH_STATUSES,
        )
        .select_related("need", "need__community", "offer")
        .order_by("-proposed_at")
        .distinct()[:OPEN_MATCHES_CAP]
    )


def recent_notifications(user):
    """The user's most recent notifications. User-global (no community FK).

    Uses the ``notifications`` related_name on ``Notification.recipient``;
    ordering stays explicit so the panel doesn't silently follow a future
    change to the model's default ordering.
    """
    return list(user.notifications.order_by("-created_at")[:RECENT_NOTIFICATIONS_CAP])


def own_tags(member):
    """The member's own tags at ALL statuses (their verification state)."""
    return list(MemberTag.objects.filter(member=member).select_related("tag").order_by("tag__sort_order", "tag__label"))
