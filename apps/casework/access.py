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


def subject_display(case) -> dict:
    """How much of the subject's identity this case may show.

    Gate item 5 (docs/ethics-and-safety.md): a person named in someone else's case
    who has never consented gets what is stored and shown about them limited until
    they can. Passing case_access() says a worker may see the FILE; it does not say
    the person in it agreed to be named. Those are different questions and this is
    the second one.

    Full name only when the subject speaks for themselves — they hold the account,
    or an active consent names THEM (not the coordinator who wrote it down).
    Otherwise initials, which is what every casework list already uses.

    Returns {"label", "limited", "note"} so templates render one thing.
    """
    person = case.subject_person
    if person is None:
        return {"label": "", "limited": False, "note": ""}

    spoke_for_themselves = bool(person.linked_user_id) or any(
        c.is_currently_active() for c in person.consents_about.all()
    )
    if spoke_for_themselves:
        return {"label": person.display_name or person.short_code, "limited": False, "note": ""}

    return {
        "label": person.initials or person.short_code,
        "limited": True,
        "note": (
            "Recorded by a coordinator. This person has not been asked directly, so their name is kept short here."
        ),
    }


def is_coordinator(member) -> bool:
    return bool(member and member.role in COORDINATOR_ROLES)


def is_admin(member) -> bool:
    return bool(member and member.role == "admin")
