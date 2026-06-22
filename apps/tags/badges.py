"""
Read-only surfacing of *verified* member tags as badges (feed, detail pages).

Only ``verified`` tags are surfaced on shared community surfaces — a
safety-critical rule: a self-reported authority claim (e.g. "priest") must
never read as endorsed. Visibility is honoured through
``MemberTag.is_visible_to(viewer)`` so a coordinators-only tag never leaks to
a plain member.
"""

from collections import defaultdict

from .models import MemberTag


def verified_badges_for(member_ids, viewer):
    """Map each member id → list of their verified, viewer-visible MemberTags.

    Runs a single query (``select_related('tag')``); ``is_visible_to`` then
    filters in memory with no further queries. Members with no visible verified
    tags are omitted. Ordered by the tag catalog's ``sort_order`` then ``label``.
    """
    member_ids = list(member_ids)
    if not member_ids:
        return {}
    badges = (
        MemberTag.objects.filter(member_id__in=member_ids, status="verified")
        .select_related("tag")
        .order_by("tag__sort_order", "tag__label")
    )
    result = defaultdict(list)
    for mt in badges:
        if mt.is_visible_to(viewer):
            result[mt.member_id].append(mt)
    return dict(result)
