"""Which coordinator did what, scoped to one community (docs/specs/coordinator-activity.md, C13).

AuditLog has no community column, and it is append-only (the model refuses UPDATE and Postgres
revokes it), so a new column could never be backfilled: history would start the day it shipped.
Instead each action on this page is scoped through the resource it already names, in the database,
with one query:

  * the community itself          community.updated / theme_set / identity_set
  * a member of the community     member.role_changed / removed / reinstated
  * a resource, flag, need,       resource.*, flag.resolved / dismissed, content.*,
    offer, page or member tag     page.*, tag.verified / rejected / revoked
  * a vouch                       user.vouched records the community slug in details

The action list is an ALLOW-LIST on purpose. A member's private acts (member.blocked — "they
aren't told") and a reporter's identity (flag.created) must never reach a coordinator's screen, and
a new action type stays off this page until someone decides it belongs here.
"""

from django.db.models import Q

from apps.audit.models import AuditLog

# action -> how its resource_id ties to a community
COMMUNITY = ("community.updated", "community.theme_set", "community.identity_set")
MEMBER = ("member.role_changed", "member.removed", "member.reinstated")
RESOURCE = ("resource.added", "resource.archived")
FLAG = ("flag.resolved", "flag.dismissed")
CONTENT = ("content.hidden", "content.unhidden")
PAGE = ("page.created", "page.updated", "page.published", "page.unpublished", "page.archived", "page.restored")
TAG = ("tag.verified", "tag.rejected", "tag.revoked")
VOUCH = ("user.vouched",)

ACTIONS = COMMUNITY + MEMBER + RESOURCE + FLAG + CONTENT + PAGE + TAG + VOUCH

LABELS = {
    "community.updated": "changed the community settings",
    "community.theme_set": "changed the community's look",
    "community.identity_set": "changed the community's name or description",
    "member.role_changed": "changed a role",
    "member.removed": "removed a member",
    "member.reinstated": "reinstated a member",
    "resource.added": "added a resource",
    "resource.archived": "archived a resource",
    "flag.resolved": "acted on a flag",
    "flag.dismissed": "dismissed a flag",
    "content.hidden": "hid a post",
    "content.unhidden": "unhid a page",
    "page.created": "created a page",
    "page.updated": "edited a page",
    "page.published": "published a page",
    "page.unpublished": "unpublished a page",
    "page.archived": "archived a page",
    "page.restored": "restored a page",
    "tag.verified": "verified a tag",
    "tag.rejected": "declined a tag",
    "tag.revoked": "revoked a tag",
    "user.vouched": "vouched for a neighbor",
}


def scope(community) -> Q:
    """Rows of the allow-listed actions that belong to `community`, as one Q for one query."""
    from apps.communities.models import Member, Resource
    from apps.moderation.models import Flag
    from apps.needs.models import Need
    from apps.offers.models import Offer
    from apps.pages.models import CommunityPage
    from apps.tags.models import MemberTag

    def ids(qs):
        return qs.values("pk")

    return (
        Q(action__in=COMMUNITY, resource_id=community.pk)
        | Q(action__in=MEMBER, resource_id__in=ids(Member.objects.filter(community=community)))
        | Q(action__in=RESOURCE, resource_id__in=ids(Resource.objects.filter(community=community)))
        | Q(action__in=FLAG, resource_id__in=ids(Flag.objects.filter(community=community)))
        | Q(action__in=CONTENT, resource_id__in=ids(Need.objects.filter(community=community)))
        | Q(action__in=CONTENT, resource_id__in=ids(Offer.objects.filter(community=community)))
        | Q(action__in=CONTENT + PAGE, resource_id__in=ids(CommunityPage.objects.filter(community=community)))
        | Q(action__in=TAG, resource_id__in=ids(MemberTag.objects.filter(member__community=community)))
        | Q(action__in=VOUCH, details__community=community.slug)
    )


def events(community):
    return AuditLog.objects.filter(scope(community)).order_by("-timestamp", "-id")


def describe(rows, community):
    """Plain rows for the template. Only fields chosen here reach the page: never the raw
    details blob, the IP hash, or an email. People are named the way this community names them."""
    from apps.communities.models import Member

    rows = list(rows)
    members = {
        m.user_id: m.display_name
        for m in Member.objects.filter(community=community, user_id__in={r.user_id for r in rows if r.user_id})
    }
    targets = {
        m.pk: m.display_name
        for m in Member.objects.filter(community=community, pk__in={r.resource_id for r in rows if r.action in MEMBER})
    }
    out = []
    for r in rows:
        details = r.details or {}
        subject = ""
        if r.action in MEMBER:
            subject = targets.get(r.resource_id, "a former member")
            if r.action == "member.role_changed" and {"from", "to"} <= details.keys():
                subject += f" ({details['from']} → {details['to']})"
        elif r.action in VOUCH:
            subject = details.get("vouched_username", "")
        elif r.action in TAG:
            subject = details.get("tag_slug", "")
        elif r.action in RESOURCE:
            subject = details.get("category", "")
        out.append(
            {
                "when": r.timestamp,
                "who": members.get(r.user_id, "a former member") if r.user_id else "the system",
                "what": LABELS.get(r.action, r.action),
                "subject": subject,
            }
        )
    return out
