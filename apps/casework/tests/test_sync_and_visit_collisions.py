"""
Offline sync + visit-capture collisions (bug-hunt batch 6b, #9 #34).

#9  SyncView._one looked the case up with .get(pk=item['case_id'], …) guarded by
    except (DoesNotExist, ValueError, TypeError). A non-UUID string makes Django's
    UUIDField raise django.core.exceptions.ValidationError, which is none of those,
    so it escaped _one and the unguarded batch loop as a 500. The client_uuid two
    lines above IS pre-validated, with a comment naming this exact failure —
    case_id was simply missed. One legacy short_code or corrupted IndexedDB entry
    500s the whole batch; visit_offline.js keeps the queue on failure and re-POSTs
    forever, so field notes stop syncing permanently.

#34 VisitCaptureView.post caught the IntegrityError from the globally-unique
    client_uuid unconditionally and redirected to ?saved={short_code}. On a mobile
    bfcache Back that restores a used client_uuid, an edited resubmit ("actually
    she needs the utility referral, not rent") collides with the earlier row: the
    corrected narrative is dropped and the page shows a green "Visit saved". The
    siblings (NoteCreateView/SyncView) scope the lookup to the case and tell a
    replay apart from a genuine collision; this view did neither.
"""

import uuid

import pytest

from apps.casework.models import CaseFile, CaseNote

pytestmark = pytest.mark.django_db

SYNC_KW = {"content_type": "application/json"}


def _draft(world, **over):
    d = {
        "client_uuid": str(uuid.uuid4()),
        "case_id": str(world.case.pk),
        "kind": "visit",
        "occurred_at": "2026-06-12T15:04:00Z",
        "duration_minutes": 25,
        "location_kind": "home",
        "actions": ["food_provided"],
        "aid_value_cents": 2500,
        "body": "Offline visit note.",
        "finalize": True,
    }
    d.update(over)
    return d


# ------------------------------------------------------------------------- #9
def test_sync_malformed_case_id_is_a_per_item_error_not_a_500(world, auth, u):
    """One poisoned item must not take the batch down — that is what wedges the
    offline queue, because the client re-POSTs the same batch forever."""
    client = auth(world.coord_u)
    drafts = [
        _draft(world, body="Before the bad one.", occurred_at="2026-06-10T09:00:00Z"),
        _draft(world, case_id="CASE-1234"),  # a legacy short_code, not a uuid
        _draft(world, body="After the bad one.", occurred_at="2026-06-11T09:00:00Z"),
    ]

    resp = client.post(u("sync"), {"drafts": drafts}, **SYNC_KW)

    assert resp.status_code == 200
    results = resp.json()["results"]
    assert [r["status"] for r in results] == ["created", "error", "created"]
    assert results[1]["error"] == "unknown case"
    assert results[1]["client_uuid"] == drafts[1]["client_uuid"], "the item is still identifiable to the client"
    assert CaseNote.objects.filter(case=world.case).count() == 2, "both good notes persisted"


def test_sync_empty_case_id_is_a_per_item_error(world, auth, u):
    client = auth(world.coord_u)

    resp = client.post(u("sync"), {"drafts": [_draft(world, case_id="")]}, **SYNC_KW)

    assert resp.status_code == 200
    assert resp.json()["results"][0]["status"] == "error"


def test_sync_still_creates_a_note_for_a_valid_case_id(world, auth, u):
    """The guard must not reject the ordinary path."""
    client = auth(world.coord_u)

    resp = client.post(u("sync"), {"drafts": [_draft(world)]}, **SYNC_KW)

    assert resp.json()["results"][0]["status"] == "created"
    assert CaseNote.objects.filter(case=world.case).count() == 1


# ------------------------------------------------------------------------ #34
def _visit_post(world, client_uuid, body):
    return {
        "case": str(world.case.pk),
        "kind": "visit",
        "occurred_at": "2026-06-12T15:04",
        "duration_minutes": "25",
        "location_kind": "home",
        "body": body,
        "client_uuid": str(client_uuid),
    }


def test_visit_capture_stale_client_uuid_does_not_report_a_false_save(world, auth, u):
    """A bfcache Back restores a used client_uuid; the visitor edits the note and
    resubmits. Dropping the edit under a green 'Visit saved' is the bug."""
    client = auth(world.coord_u)
    cu = uuid.uuid4()
    first = client.post(u("visit"), _visit_post(world, cu, "Rent arrears discussed."))
    assert first.status_code == 302
    note = CaseNote.objects.get(client_uuid=cu)

    resp = client.post(u("visit"), _visit_post(world, cu, "Actually she needs the utility referral, not rent."))

    assert resp.status_code == 409, "an edit that could not be stored must not be reported as saved"
    assert "saved=" not in resp.get("Location", ""), "no green banner over a dropped note"
    assert CaseNote.objects.filter(case=world.case).count() == 1
    note.refresh_from_db()
    assert note.body == "Rent arrears discussed.", "the stored note is untouched"


def test_visit_capture_identical_replay_is_still_idempotent(world, auth, u):
    """The dominant case — a double submit of the same note — must stay a quiet
    success, not become an error."""
    client = auth(world.coord_u)
    cu = uuid.uuid4()
    body = "Rent arrears discussed."
    first = client.post(u("visit"), _visit_post(world, cu, body))
    second = client.post(u("visit"), _visit_post(world, cu, body))

    assert first.status_code == 302
    assert second.status_code == 302
    assert "saved=" in second["Location"]
    assert CaseNote.objects.filter(case=world.case).count() == 1


def test_visit_capture_cross_case_collision_leaks_nothing(world, auth, u):
    """client_uuid is globally unique. A collision with a note in another case
    must not be reported as saved, and must not surface that note."""
    other_case = CaseFile.objects.create(
        community=world.community,
        subject_person=world.person,
        opened_by=world.coordinator,
        assigned_to=world.coordinator,
        consent=world.consent,
        sensitivity=CaseFile.SENS_STANDARD,
    )
    foreign = CaseNote(
        case=other_case,
        author=world.coordinator,
        kind="visit",
        occurred_at="2026-06-12T15:04:00Z",
        client_uuid=uuid.uuid4(),
    )
    foreign.body = "A note in a different case."
    foreign.save()
    client = auth(world.coord_u)

    resp = client.post(u("visit"), _visit_post(world, foreign.client_uuid, "New visit on my case."))

    assert resp.status_code == 409
    body = resp.content.decode()
    assert str(foreign.pk) not in body
    assert "A note in a different case." not in body
    assert CaseNote.objects.filter(case=world.case).count() == 0
