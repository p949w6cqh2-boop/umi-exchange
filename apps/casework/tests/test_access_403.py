import datetime

import pytest
from django.utils import timezone

from apps.casework.models import CaseAccessGrant, CaseFile

pytestmark = pytest.mark.django_db


def _restricted_case(world):
    return CaseFile.objects.create(
        community=world.community, subject_person=world.person,
        opened_by=world.coordinator, assigned_to=world.coordinator,
        consent=world.consent, sensitivity="restricted")


def test_plain_member_cannot_list_cases(world, auth, u):
    client = auth(world.plain_u)
    assert client.get(u("list")).status_code == 403


def test_non_member_gets_403(world, auth, u):
    from .conftest import make_user
    outsider = make_user("outsider")
    client = auth(outsider)
    assert client.get(u("list")).status_code == 403
    assert client.get(u("detail", pk=world.case.pk)).status_code == 403


def test_subject_cannot_read_own_case(world, auth, u):
    client = auth(world.subject_u)  # Maria, the case subject, is a member
    assert client.get(u("detail", pk=world.case.pk)).status_code == 403


def test_coordinator_without_grant_blocked_on_restricted(world, auth, u):
    case = _restricted_case(world)
    client = auth(world.coord2_u)  # coordinator, but not opener/assignee
    assert client.get(u("detail", pk=case.pk)).status_code == 403


def test_viewer_grant_reads_but_cannot_contribute(world, auth, u):
    case = _restricted_case(world)
    CaseAccessGrant.objects.create(case=case, member=world.plain,
                                   granted_by=world.coordinator,
                                   role="viewer", reason="covering visits")
    client = auth(world.plain_u)
    assert client.get(u("detail", pk=case.pk)).status_code == 200
    resp = client.post(u("note-create", pk=case.pk),
                       {"kind": "visit", "occurred_at": "2026-06-12T10:00",
                        "location_kind": "home", "body": "hello"})
    assert resp.status_code == 403


def test_revoked_grant_blocks(world, auth, u):
    case = _restricted_case(world)
    grant = CaseAccessGrant.objects.create(
        case=case, member=world.plain, granted_by=world.coordinator,
        role="viewer", reason="covering", revoked_at=timezone.now())
    assert grant.revoked_at
    client = auth(world.plain_u)
    assert client.get(u("detail", pk=case.pk)).status_code == 403


def test_expired_grant_blocks(world, auth, u):
    case = _restricted_case(world)
    CaseAccessGrant.objects.create(
        case=case, member=world.plain, granted_by=world.coordinator,
        role="contributor", reason="covering",
        expires_at=timezone.now() - datetime.timedelta(hours=1))
    client = auth(world.plain_u)
    assert client.get(u("detail", pk=case.pk)).status_code == 403


def test_non_author_cannot_finalize(world, auth, u, make_note):
    note = make_note(author=world.coordinator, status="draft")
    client = auth(world.coord2_u)  # has case access, isn't the author
    resp = client.post(u("note-finalize", pk=world.case.pk, note_id=note.pk))
    assert resp.status_code == 403
    note.refresh_from_db()
    assert note.status == "draft"


def test_export_requires_admin(world, auth, u):
    client = auth(world.coord_u)
    assert client.get(u("export", pk=world.case.pk)).status_code == 403


def test_export_requires_case_export_scope(world, auth, u):
    from apps.consent.models import Consent
    narrow = Consent.objects.create(
        participant=world.subject_u, granted_to=world.community.name,
        scope=["case_records"], purpose="no export", method="digital")
    case = CaseFile.objects.create(
        community=world.community, subject_person=world.person,
        opened_by=world.coordinator, assigned_to=world.coordinator,
        consent=narrow)
    client = auth(world.admin_u)
    assert client.get(u("export", pk=case.pk)).status_code == 403
