"""
Authorization matrix for case files (design §3.4). Single source of truth:
every view asks `case_access()`; tests lock the matrix down.

Levels: NONE < VIEWER < CONTRIBUTOR.
  standard   case: assigned_to, opened_by, coordinators, admins → CONTRIBUTOR
  restricted case: assigned_to, opened_by, admins              → CONTRIBUTOR
  active CaseAccessGrant adds VIEWER or CONTRIBUTOR explicitly.
The subject themself gets NONE on the record body (existence transparency
is a separate, list-level concern — design §3.4).
"""

from django.utils import timezone

NONE, VIEWER, CONTRIBUTOR = 0, 1, 2

COORDINATOR_ROLES = ("coordinator", "admin")


def get_membership(user, community):
    """Active Member for user in community, or None."""
    if not user.is_authenticated:
        return None
    from apps.communities.models import Member

    return Member.objects.filter(user=user, community=community, is_active=True).select_related("user").first()


def case_access(member, case) -> int:
    if member is None or member.community_id != case.community_id:
        return NONE
    if member.role == "admin":
        return CONTRIBUTOR
    if case.assigned_to_id == member.id or case.opened_by_id == member.id:
        return CONTRIBUTOR
    if case.sensitivity == "standard" and member.role in COORDINATOR_ROLES:
        return CONTRIBUTOR
    grant = (
        case.grants.filter(
            member=member,
            revoked_at__isnull=True,
        )
        .exclude(expires_at__lt=timezone.now())
        .first()
    )
    if grant:
        return CONTRIBUTOR if grant.role == "contributor" else VIEWER
    return NONE


def is_coordinator(member) -> bool:
    return bool(member and member.role in COORDINATOR_ROLES)


def is_admin(member) -> bool:
    return bool(member and member.role == "admin")
