import pytest
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.casework.models import CaseAccessGrant, CaseFile, FollowUp, WarmHandoff
from apps.people.models import Person

pytestmark = pytest.mark.django_db


# ---- encryption round-trips ------------------------------------------------
def test_person_fields_round_trip(world):
    p = Person.objects.get(pk=world.person.pk)
    assert p.display_name == "Maria Garcia"
    assert p.contact == {"raw": "555-0100"}
    assert bytes(p.display_name_enc) != b"Maria Garcia"  # ciphertext at rest


def test_note_body_round_trip(world, make_note):
    note = make_note(body="She mentioned the eviction letter.")
    note.refresh_from_db()
    assert note.body == "She mentioned the eviction letter."
    assert b"eviction" not in bytes(note.body_enc)


def test_summary_detail_round_trip(world):
    world.case.summary = "Family of four; rent arrears."
    world.case.save(update_fields=["summary_enc"])
    assert CaseFile.objects.get(pk=world.case.pk).summary == "Family of four; rent arrears."

    ho = WarmHandoff(case=world.case, from_member=world.coordinator, to_member=world.coordinator2)
    ho.summary = "Prefers afternoons."
    ho.save()
    assert WarmHandoff.objects.get(pk=ho.pk).summary == "Prefers afternoons."

    fu = FollowUp(
        case=world.case,
        created_by=world.coordinator,
        assigned_to=world.coordinator,
        title="Call back",
        due_date=timezone.localdate(),
    )
    fu.detail = "Ask about the deposit."
    fu.save()
    assert FollowUp.objects.get(pk=fu.pk).detail == "Ask about the deposit."


# ---- audit events -----------------------------------------------------------
def _actions(resource):
    return list(AuditLog.objects.filter(resource_id=resource.pk).values_list("action", flat=True))


def test_case_opened_carries_consent_id(world, auth, u):
    client = auth(world.coord_u)
    client.post(
        u("create"),
        {
            "person": str(world.person.pk),
            "sensitivity": "standard",
            "intake_date": timezone.localdate().isoformat(),
            "consent_mode": "existing",
            "existing_consent": str(world.consent.pk),
        },
    )
    case = CaseFile.objects.exclude(pk=world.case.pk).get()
    row = AuditLog.objects.get(action="case.opened", resource_id=case.pk)
    assert row.details["consent_id"] == str(world.consent.pk)


def test_emergency_open_is_flagged_and_audited(world, auth, u):
    client = auth(world.coord_u)
    client.post(
        u("create"),
        {
            "new_person_name": "After Hours",
            "sensitivity": "standard",
            "intake_date": timezone.localdate().isoformat(),
            "consent_mode": "emergency",
            "emergency_justification": "Family stranded at 2am; consent to follow.",
        },
    )
    case = CaseFile.objects.exclude(pk=world.case.pk).get()
    assert case.emergency_opened and case.consent_id is None
    row = AuditLog.objects.get(action="case.opened_emergency", resource_id=case.pk)
    assert "stranded" in row.details["justification"]


def test_case_viewed_is_throttled_per_session(world, auth, u):
    client = auth(world.coord_u)
    client.get(u("detail", pk=world.case.pk))
    client.get(u("detail", pk=world.case.pk))  # same session, inside window
    assert AuditLog.objects.filter(action="case.viewed", resource_id=world.case.pk).count() == 1


def test_lifecycle_events_emitted(world, auth, u, make_note):
    client = auth(world.coord_u)
    note = make_note(status="draft")
    client.post(u("note-finalize", pk=world.case.pk, note_id=note.pk))
    assert AuditLog.objects.filter(action="note.finalized", resource_id=note.pk).exists()

    admin_client = auth(world.admin_u)
    admin_client.post(
        u("assign", pk=world.case.pk), {"to_member": str(world.coordinator2.pk), "summary": "Maria prefers afternoons."}
    )
    assert AuditLog.objects.filter(action="case.assigned", resource_id=world.case.pk).exists()

    ho = WarmHandoff.objects.get(case=world.case, status="pending")
    incoming = auth(world.coord2_u)
    incoming.post(u("handoff-ack", pk=world.case.pk, handoff_id=ho.pk))
    assert AuditLog.objects.filter(action="handoff.acknowledged", resource_id=ho.pk).exists()


def test_grant_events_and_export_scope(world, auth, u):
    admin_client = auth(world.admin_u)
    admin_client.post(
        u("grant-create", pk=world.case.pk),
        {"member": str(world.plain.pk), "role": "viewer", "reason": "Covering Saturday visits"},
    )
    grant = CaseAccessGrant.objects.get(case=world.case, member=world.plain)
    assert AuditLog.objects.filter(action="grant.granted", resource_id=grant.pk).exists()

    admin_client.post(u("grant-revoke", pk=world.case.pk, grant_id=grant.pk))
    assert AuditLog.objects.filter(action="grant.revoked", resource_id=grant.pk).exists()

    resp = admin_client.get(u("export", pk=world.case.pk))
    assert resp.status_code == 200
    assert b"CASE EXPORT" in resp.content
    row = AuditLog.objects.get(action="case.exported", resource_id=world.case.pk)
    assert "case_export" in row.details["scope"]


def test_all_emitted_actions_fit_widened_column(world):
    assert all(len(a) <= 32 for a in AuditLog.objects.values_list("action", flat=True))


# ---- consent gate / revocation freeze ---------------------------------------
def test_revoked_consent_freezes_notes_and_export(world, auth, u):
    world.consent.status = "revoked"
    world.consent.revoked_at = timezone.now()
    world.consent.save(update_fields=["status", "revoked_at"])

    client = auth(world.coord_u)
    resp = client.post(
        u("note-create", pk=world.case.pk),
        {"kind": "visit", "occurred_at": "2026-06-12T10:00", "location_kind": "home", "body": "should be frozen"},
    )
    assert resp.status_code == 403

    admin_client = auth(world.admin_u)
    assert admin_client.get(u("export", pk=world.case.pk)).status_code == 403

    # …but closing the case is still allowed
    assert client.post(u("status", pk=world.case.pk), {"status": "closed"}).status_code in (200, 302)
