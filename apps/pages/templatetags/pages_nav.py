"""§I nav anchor: the footer's community-pages column.

Rendered from base.html on every view that carries a `community` in context;
silent everywhere else. Members see member-visible pages, everyone else the
pre-auth set — the same predicates the read surfaces use, so the footer can
never name a page its reader couldn't open."""

from django import template

from apps.communities.models import Member
from apps.pages.models import CommunityPage

register = template.Library()

FOOTER_CAP = 6


@register.inclusion_tag("community_pages/_footer_pages.html", takes_context=True)
def community_pages_footer(context):
    community = context.get("community")
    if community is None or not getattr(community, "is_active", False):
        return {"pages": None, "community": None}
    # Fast path: the rendering view usually resolved membership already.
    ctx_member = context.get("member")
    if (
        ctx_member is not None
        and getattr(ctx_member, "community_id", None) == community.id
        and getattr(ctx_member, "is_active", False)
    ):
        is_member = True
    else:
        request = context.get("request")
        user = getattr(request, "user", None)
        is_member = bool(
            user is not None
            and user.is_authenticated
            and Member.objects.filter(user=user, community=community, is_active=True).exists()
        )
    qs = (
        CommunityPage.objects.member_visible(community)
        if is_member
        else CommunityPage.objects.pre_auth_visible(community)
    )
    pages = list(qs.order_by("sort_order", "title")[:FOOTER_CAP])
    return {"pages": pages, "community": community}
