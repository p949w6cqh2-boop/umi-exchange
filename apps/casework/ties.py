"""
Handing cases back when someone stops coordinating (the founder's call, 2026-10-13, bug hunt L13).

access.case_access() already ends the access an opener or assignee had once they lose the
coordinator role. This module does the other half of the call: the open cases still assigned to
them wait, unassigned, for an admin to hand on, and the admins are told. Closed cases keep their
assignee as a record of who held them. Nothing is deleted, and each case's audit trail names who
held it and why it was let go.

Called from the three ways a person stops coordinating: an admin changes their role, they leave,
or they are removed.
"""

from django.urls import reverse

from apps.audit.services import emit

from .access import COORDINATOR_ROLES
from .notify import notify

REASONS = ("role_changed", "left", "removed")


def release_case_ties(member, *, reason, user=None, request=None) -> int:
    """Unassign `member`'s open and monitoring cases in their community and tell its admins.
    Returns how many cases were let go. Call inside the caller's transaction."""
    from apps.communities.models import Member

    from .models import CaseFile

    if reason not in REASONS:
        raise ValueError(f"unknown reason: {reason!r}")
    cases = list(
        CaseFile.objects.select_for_update(of=("self",))
        .filter(community_id=member.community_id, assigned_to=member)
        .exclude(status=CaseFile.STATUS_CLOSED)
    )
    for case in cases:
        case.assigned_to = None
        case.save(update_fields=["assigned_to", "updated_at"])
        emit(
            "case.unassigned",
            case,
            user=user,
            request=request,
            details={"from_member": str(member.pk), "reason": reason},
        )
    if cases:
        community = member.community
        count = len(cases)
        what = "1 open case they held has" if count == 1 else f"{count} open cases they held have"
        admins = (
            Member.objects.filter(community=community, is_active=True, role="admin")
            .exclude(pk=member.pk)
            .select_related("user")
        )
        for admin in admins:
            notify(
                admin.user,
                "case_unassigned",
                "Cases to hand on" if count > 1 else "A case to hand on",
                f"{member.display_name} no longer coordinates here, so {what} no one assigned. "
                "Hand each one to a coordinator from the case list.",
                reverse("casework:list", kwargs={"slug": community.slug}),
            )
    return len(cases)


def stops_coordinating(old_role, new_role) -> bool:
    return old_role in COORDINATOR_ROLES and new_role not in COORDINATOR_ROLES
