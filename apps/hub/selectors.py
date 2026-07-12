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
    """The member's own live tags — terminal removed/revoked stay hidden,
    matching the my-tags page queryset (apps/tags/views.py)."""
    return list(
        MemberTag.objects.filter(member=member)
        .exclude(status__in=("removed", "revoked"))
        .select_related("tag")
        .order_by("tag__sort_order", "tag__label")
    )


# ── Hub v2 · "The Pulse" ─────────────────────────────

PULSE_CAP = 30
PULSE_WINDOW_DAYS = 30
SEASON_DAYS = 90

URGENCY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def pulse_events(community, cap=PULSE_CAP):
    """The community's recent life, merged newest-first: asks and offers
    landing, asks being answered, needs fulfilled, neighbours joining.
    Helpers are never named here — public celebration stays §8.2-shaped."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.needs.models import Need
    from apps.offers.models import Offer

    since = timezone.now() - timedelta(days=PULSE_WINDOW_DAYS)
    events = []
    needs = (
        Need.objects.filter(community=community, created_at__gte=since, moderation_hidden=False)
        .select_related("requester", "category")
        .order_by("-created_at")[:cap]
    )
    for need in needs:
        events.append(
            {
                "kind": "need_posted",
                "when": need.created_at,
                "title": need.title,
                "actor": need.requester.display_name,
                "urgency": need.urgency,
                "url": f"/c/{community.slug}/needs/{need.pk}/",
            }
        )
    offers = (
        Offer.objects.filter(community=community, created_at__gte=since, moderation_hidden=False)
        .select_related("offerer", "category")
        .order_by("-created_at")[:cap]
    )
    for offer in offers:
        events.append(
            {
                "kind": "offer_posted",
                "when": offer.created_at,
                "title": offer.title,
                "actor": offer.offerer.display_name,
                "url": f"/c/{community.slug}/offers/{offer.pk}/",
            }
        )
    answered = (
        Match.objects.filter(need__community=community, accepted_at__isnull=False, accepted_at__gte=since)
        .select_related("need")
        .order_by("-accepted_at")[:cap]
    )
    for match in answered:
        events.append(
            {
                "kind": "ask_answered",
                "when": match.accepted_at,
                "title": match.need.title,
                "actor": None,  # "a neighbour" — never the helper's name
                "url": f"/c/{community.slug}/needs/{match.need_id}/",
            }
        )
    fulfilled = (
        Match.objects.filter(need__community=community, fulfilled_at__isnull=False, fulfilled_at__gte=since)
        .select_related("need")
        .order_by("-fulfilled_at")[:cap]
    )
    for match in fulfilled:
        events.append(
            {
                "kind": "need_fulfilled",
                "when": match.fulfilled_at,
                "title": match.need.title,
                "actor": None,
                "url": f"/c/{community.slug}/needs/{match.need_id}/",
            }
        )
    joined = Member.objects.filter(community=community, is_active=True, joined_at__gte=since).order_by("-joined_at")[
        :cap
    ]
    for member in joined:
        events.append(
            {
                "kind": "member_joined",
                "when": member.joined_at,
                "title": member.display_name,
                "actor": member.display_name,
                "url": "",
            }
        )
    events.sort(key=lambda e: e["when"], reverse=True)
    return events[:cap]


def spotlight_need(member, cycle=0):
    """One ask, right now (the Tinder-focus mechanic without the swipe-shame):
    the most urgent, longest-waiting UNANSWERED ask that isn't the member's
    own. `cycle` walks the same queue and wraps — 'show me another' never
    dead-ends."""
    from django.db.models import Case, IntegerField, Value, When

    from apps.needs.models import Need

    qs = (
        Need.objects.filter(community=member.community, status="open", moderation_hidden=False)
        .exclude(requester=member)
        .exclude(matches__status__in=OPEN_MATCH_STATUSES)
        .select_related("requester", "category")
        .annotate(
            urgency_rank=Case(
                *[When(urgency=u, then=Value(r)) for u, r in URGENCY_RANK.items()],
                default=Value(9),
                output_field=IntegerField(),
            )
        )
        .order_by("urgency_rank", "created_at")
    )
    count = qs.count()
    if not count:
        return None
    return qs[cycle % count]


def season_impact(member) -> int:
    """Fulfilled matches this season where the member was the HELPER (offer
    owner or direct-volunteer proposer). A private, personal line — never a
    leaderboard, never shown for anyone else."""
    from datetime import timedelta

    from django.utils import timezone

    since = timezone.now() - timedelta(days=SEASON_DAYS)
    return (
        Match.objects.filter(status="fulfilled", fulfilled_at__gte=since, need__community=member.community)
        .filter(Q(offer__offerer=member) | Q(proposed_by=member))
        .exclude(need__requester=member)
        .distinct()
        .count()
    )


def week_stats(community) -> dict:
    """Collective pride, not scores: what the whole community did this week."""
    from datetime import timedelta

    from django.utils import timezone

    week = timezone.now() - timedelta(days=7)
    matches = Match.objects.filter(need__community=community)
    return {
        "hands_raised": matches.filter(proposed_at__gte=week).count(),
        "asks_answered": matches.filter(accepted_at__isnull=False, accepted_at__gte=week).count(),
        "fulfilled": matches.filter(fulfilled_at__isnull=False, fulfilled_at__gte=week).count(),
    }
