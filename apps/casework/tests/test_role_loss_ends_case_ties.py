"""
Losing the coordinator role ends a person's casework access (the founder's call, 2026-10-13,
bug hunt L13).

The access matrix gave a case's opener and assignee CONTRIBUTOR with no condition on their role,
so a coordinator made a plain member again kept every case they had opened or held, restricted
ones included: their case list refused them, but a direct link and the visit picker still opened
those cases. The call: losing the role ends the access they had as opener or assignee, and the
open cases still assigned to them wait, unassigned, for an admin to hand on. Nothing is deleted,
and the audit log keeps what they did. An explicit grant still works: that is an admin's choice
about this person, not a leftover of their old role.
"""

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.casework import access
from apps.casework.models import CaseAccessGrant, CaseFile
from apps.casework.tests.conftest import make_user
from apps.communities.models import Member
from apps.moderation.services import leave_community, remove_member
from apps.notifications.models import Notification

pytestmark = pytest.mark.django_db


def _demote(client, world, member, role="member"):
    client.force_login(world.admin_u)
    return client.post(
        reverse("community-settings", kwargs={"slug": world.community.slug}),
        {"action": "change_role", "member_id": str(member.pk), "role": role},
    )


@pytest.fixture
def restricted(world):
    world.case.sensitivity = CaseFile.SENS_RESTRICTED
    world.case.save(update_fields=["sensitivity"])
    return world


def test_demoted_coordinator_loses_the_restricted_case_they_opened_and_held(client, restricted, auth, u):
    world = restricted
    _demote(client, world, world.coordinator)
    coord = Member.objects.get(pk=world.coordinator.pk)
    case = CaseFile.objects.get(pk=world.case.pk)
    assert coord.role == "member"

    assert access.case_access(coord, case) == access.NONE
    c = auth(world.coord_u)
    assert c.get(u("detail", pk=case.pk)).status_code == 403
    picker = c.get(u("visit")).context["form"].fields["case"].queryset
    assert case not in picker


def test_demoted_coordinator_loses_a_standard_case_they_opened(client, world, auth, u):
    # Hand the case on first, so only the opener tie is left.
    CaseFile.objects.filter(pk=world.case.pk).update(assigned_to=world.coordinator2)
    _demote(client, world, world.coordinator)
    coord = Member.objects.get(pk=world.coordinator.pk)

    assert access.case_access(coord, CaseFile.objects.get(pk=world.case.pk)) == access.NONE


def test_open_cases_wait_unassigned_for_an_admin(client, restricted, auth, u):
    world = restricted
    r = _demote(client, world, world.coordinator)
    case = CaseFile.objects.get(pk=world.case.pk)
    said = [str(m) for m in get_messages(r.wsgi_request)]
    assert said == [
        "Anne's role updated. The open case they held now has no one assigned. Hand it on from the case list."
    ]

    assert case.assigned_to_id is None
    assert case.opened_by_id == world.coordinator.pk  # history stays
    row = AuditLog.objects.get(action="case.unassigned", resource_id=case.pk)
    assert row.details["reason"] == "role_changed"
    assert row.details["from_member"] == str(world.coordinator.pk)
    note = Notification.objects.get(recipient=world.admin_u, type="case_unassigned")
    assert note.link == u("list")
    assert "Anne" in note.body
    # The admin hands it on in the usual way.
    c = auth(world.admin_u)
    r = c.post(
        u("assign", pk=case.pk),
        {"to_member": str(world.coordinator2.pk), "summary": "Weekly visits, Tuesdays after nine."},
    )
    assert r.status_code == 302
    assert CaseFile.objects.get(pk=case.pk).assigned_to_id == world.coordinator2.pk


def test_a_closed_case_keeps_its_assignee_on_record_but_not_the_assignees_powers(client, restricted, auth, u):
    world = restricted
    CaseFile.objects.filter(pk=world.case.pk).update(status=CaseFile.STATUS_CLOSED)
    _demote(client, world, world.coordinator)
    case = CaseFile.objects.get(pk=world.case.pk)
    assert case.assigned_to_id == world.coordinator.pk  # who held it, kept as history

    c = auth(world.coord_u)
    r = c.post(u("grant-create", pk=case.pk), {"member": str(world.plain.pk), "role": "viewer", "reason": "cover"})
    assert r.status_code == 403
    assert not CaseAccessGrant.objects.filter(case=case).exists()


def test_an_explicit_grant_still_counts_after_demotion(client, restricted, auth, u):
    world = restricted
    CaseAccessGrant.objects.create(
        case=world.case, member=world.coordinator, role="viewer", granted_by=world.admin, reason="cover"
    )
    _demote(client, world, world.coordinator)
    coord = Member.objects.get(pk=world.coordinator.pk)

    assert access.case_access(coord, CaseFile.objects.get(pk=world.case.pk)) == access.VIEWER


def test_an_admin_made_coordinator_keeps_the_cases_they_hold(client, restricted, auth, u):
    world = restricted
    second_admin = Member.objects.create(
        user=make_user("rosa"),
        community=world.community,
        role="admin",
        display_name="Rosa",
        is_active=True,
    )
    CaseFile.objects.filter(pk=world.case.pk).update(assigned_to=second_admin, opened_by=second_admin)
    _demote(client, world, second_admin, role="coordinator")
    rosa = Member.objects.get(pk=second_admin.pk)
    case = CaseFile.objects.get(pk=world.case.pk)

    assert rosa.role == "coordinator"
    assert case.assigned_to_id == rosa.pk
    assert access.case_access(rosa, case) == access.CONTRIBUTOR
    assert not AuditLog.objects.filter(action="case.unassigned").exists()


def test_a_coordinator_who_leaves_hands_their_open_cases_back(restricted):
    world = restricted
    leave_community(world.coordinator)

    assert CaseFile.objects.get(pk=world.case.pk).assigned_to_id is None
    assert AuditLog.objects.get(action="case.unassigned").details["reason"] == "left"
    assert Notification.objects.filter(recipient=world.admin_u, type="case_unassigned").exists()


def test_a_removed_coordinator_hands_their_open_cases_back(restricted):
    world = restricted
    remove_member(world.coordinator, by=world.admin)

    assert CaseFile.objects.get(pk=world.case.pk).assigned_to_id is None
    assert AuditLog.objects.get(action="case.unassigned").details["reason"] == "removed"
