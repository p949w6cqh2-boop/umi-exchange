"""Regression tests for the 2026-07-13 adversarial bug-hunt — casework Batch-1:

- NoteAmendView honors the §3.6 consent-revocation freeze (was the one open
  write path post-revocation — an amendment is a fresh CaseNote row).
- The online-form client_uuid replay handler can't render another case's
  decrypted note body across the access boundary (client_uuid is globally unique).
- SyncView's duplicate check is scoped to the accessible case, so it can't leak
  a foreign note's id.
"""

import json
import uuid

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.casework.models import CaseFile, CaseNote

pytestmark = pytest.mark.django_db


def _foreign_case_with_note(world, *, cu, body):
    """A restricted case that world.coord_u has NO access to, seeded via the ORM
    with a note carrying client_uuid `cu`."""
    case_b = CaseFile.objects.create(
        community=world.community,
        subject_person=world.person,
        opened_by=world.coordinator2,
        assigned_to=world.coordinator2,
        consent=world.consent,
        sensitivity="restricted",
    )
    nb = CaseNote(
        case=case_b,
        author=world.coordinator2,
        kind="visit",
        occurred_at=timezone.now(),
        location_kind="home",
        client_uuid=str(cu),
    )
    nb.body = body
    nb.save()
    return case_b, nb


def test_amend_blocked_after_consent_revoked(world, auth, u, make_note):
    note = make_note(author=world.coordinator, status="final", body="original, consented")
    world.consent.status = "revoked"
    world.consent.revoked_at = timezone.now()
    world.consent.save(update_fields=["status", "revoked_at"])

    before = CaseNote.objects.filter(case=world.case).count()
    client = auth(world.coord_u)
    resp = client.post(
        u("note-amend", pk=world.case.pk, note_id=note.pk),
        {"body": "NEW pii written after the subject withdrew consent", "finalize": "1"},
    )
    assert resp.status_code == 403
    assert CaseNote.objects.filter(case=world.case).count() == before  # no new row written


def test_note_create_replay_does_not_leak_other_case_body(world, auth, u):
    cu = uuid.uuid4()
    _case_b, _nb = _foreign_case_with_note(world, cu=cu, body="SECRET-B-BODY-XYZ")

    client = auth(world.coord_u)  # CONTRIBUTOR on world.case; NO access to case_b
    resp = client.post(
        u("note-create", pk=world.case.pk),
        {
            "kind": "visit",
            "occurred_at": "2026-06-12T10:00",
            "location_kind": "home",
            "body": "my own note",
            "client_uuid": str(cu),
        },
        HTTP_HX_REQUEST="true",
    )
    assert resp.status_code == 409
    assert b"SECRET-B-BODY-XYZ" not in resp.content


def test_sync_replay_does_not_leak_foreign_note_id(world, auth):
    cu = uuid.uuid4()
    _case_b, nb = _foreign_case_with_note(world, cu=cu, body="secret-b")

    client = auth(world.coord_u)
    resp = client.post(
        reverse("casework:sync", kwargs={"slug": world.community.slug}),
        data=json.dumps({"drafts": [{"client_uuid": str(cu), "case_id": str(world.case.pk), "body": "mine"}]}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    result = resp.json()["results"][0]
    assert result.get("note_id") != str(nb.pk)  # foreign note id must never surface
