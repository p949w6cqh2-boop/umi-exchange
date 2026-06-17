import pytest
from django.utils import timezone

from apps.casework.models import CaseFile, FollowUp, WarmHandoff

pytestmark = pytest.mark.django_db


def test_happy_path_open_note_finalize_followup_close(world, auth, u):
    client = auth(world.coord_u)

    # 1) open a case for a brand-new person, recording verbal consent
    resp = client.post(
        u("create"),
        {
            "new_person_name": "Jo Doe",
            "new_person_contact": "555-0199",
            "sensitivity": "standard",
            "intake_date": timezone.localdate().isoformat(),
            "physical_ref": "Binder 3",
            "summary": "Initial intake.",
            "consent_mode": "record",
            "record_method": "verbal",
            "include_export": "1",
            "assigned_to": str(world.coordinator.pk),
        },
    )
    assert resp.status_code == 302
    case = CaseFile.objects.exclude(pk=world.case.pk).get()
    assert case.consent_id and "case_records" in case.consent.scope
    assert case.subject_person.display_name == "Jo Doe"

    # 2) draft a visit note
    resp = client.post(
        u("note-create", pk=case.pk),
        {
            "kind": "visit",
            "occurred_at": "2026-06-12T10:00",
            "location_kind": "home",
            "duration_minutes": "30",
            "actions": ["food_provided", "prayer"],
            "aid_amount": "40.00",
            "body": "Delivered groceries; prayed together.",
        },
    )
    assert resp.status_code in (200, 302)
    note = case.notes.get()
    assert note.status == "draft" and note.aid_value_cents == 4000
    assert note.actions == ["food_provided", "prayer"]

    # 3) finalize it
    assert client.post(u("note-finalize", pk=case.pk, note_id=note.pk)).status_code in (200, 302)
    note.refresh_from_db()
    assert note.status == "final" and note.finalized_at

    # 4) follow-up → done
    resp = client.post(
        u("followup-create", pk=case.pk),
        {
            "title": "Check in re: pantry",
            "detail": "She asked about Tuesdays.",
            "due_date": timezone.localdate().isoformat(),
            "assigned_to": str(world.coordinator.pk),
        },
    )
    assert resp.status_code in (200, 302)
    fu = FollowUp.objects.get(case=case)
    assert client.post(u("followup-status", pk=fu.pk), {"status": "done"}).status_code in (200, 302)
    fu.refresh_from_db()
    assert fu.status == "done"

    # 5) close, then admin reopen
    assert client.post(u("status", pk=case.pk), {"status": "closed"}).status_code in (200, 302)
    case.refresh_from_db()
    assert case.status == "closed" and case.closed_at

    assert client.post(u("status", pk=case.pk), {"status": "open"}).status_code == 403  # coordinator
    admin_client = auth(world.admin_u)
    assert admin_client.post(u("status", pk=case.pk), {"status": "open"}).status_code in (200, 302)
    case.refresh_from_db()
    assert case.status == "open" and case.closed_at is None


def test_warm_handoff_gates_case_detail(world, auth, u):
    admin_client = auth(world.admin_u)
    resp = admin_client.post(
        u("assign", pk=world.case.pk),
        {"to_member": str(world.coordinator2.pk), "summary": "Maria prefers afternoon visits; rent is the live issue."},
    )
    assert resp.status_code == 302
    ho = WarmHandoff.objects.get(case=world.case, status="pending")
    world.case.refresh_from_db()
    assert world.case.assigned_to_id == world.coordinator2.pk
    assert world.case.notes.filter(kind="handoff", status="final").exists()

    incoming = auth(world.coord2_u)
    resp = incoming.get(u("detail", pk=world.case.pk))
    assert resp.status_code == 200
    assert b"handed to you" in resp.content  # the gate screen
    assert b"Open follow-ups" not in resp.content  # case body NOT rendered

    assert incoming.post(u("handoff-ack", pk=world.case.pk, handoff_id=ho.pk)).status_code == 302
    ho.refresh_from_db()
    assert ho.status == "acknowledged" and ho.acknowledged_at

    resp = incoming.get(u("detail", pk=world.case.pk))
    assert b"handed to you" not in resp.content


def test_only_receiver_can_acknowledge(world, auth, u):
    admin_client = auth(world.admin_u)
    admin_client.post(
        u("assign", pk=world.case.pk), {"to_member": str(world.coordinator2.pk), "summary": "Summary long enough."}
    )
    ho = WarmHandoff.objects.get(case=world.case, status="pending")
    other = auth(world.coord_u)
    assert other.post(u("handoff-ack", pk=world.case.pk, handoff_id=ho.pk)).status_code == 403


def test_double_close_returns_409(world, auth, u):
    client = auth(world.coord_u)
    assert client.post(u("status", pk=world.case.pk), {"status": "closed"}).status_code in (200, 302)
    resp = client.post(u("status", pk=world.case.pk), {"status": "closed"})
    assert resp.status_code == 409


def test_finalize_twice_returns_409(world, auth, u, make_note):
    note = make_note(status="draft")
    client = auth(world.coord_u)
    assert client.post(u("note-finalize", pk=world.case.pk, note_id=note.pk)).status_code in (200, 302)
    resp = client.post(u("note-finalize", pk=world.case.pk, note_id=note.pk))
    assert resp.status_code == 409


def test_discard_final_returns_409(world, auth, u, make_note):
    note = make_note(status="final")
    client = auth(world.coord_u)
    resp = client.post(u("note-discard", pk=world.case.pk, note_id=note.pk))
    assert resp.status_code == 409


def test_create_without_consent_choice_blocked(world, auth, u):
    client = auth(world.coord_u)
    before = CaseFile.objects.count()
    resp = client.post(
        u("create"),
        {
            "new_person_name": "No Consent",
            "sensitivity": "standard",
            "intake_date": timezone.localdate().isoformat(),
            "consent_mode": "existing",  # …but no consent selected
        },
    )
    assert resp.status_code == 200
    assert b"Pick the consent record" in resp.content
    assert CaseFile.objects.count() == before
