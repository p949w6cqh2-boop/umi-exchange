import uuid

import pytest

from apps.casework.models import CaseNote

pytestmark = pytest.mark.django_db

SYNC_KW = {"content_type": "application/json"}


def _draft(world, **over):
    d = {"client_uuid": str(uuid.uuid4()), "case_id": str(world.case.pk),
         "kind": "visit", "occurred_at": "2026-06-12T15:04:00Z",
         "duration_minutes": 25, "location_kind": "home",
         "actions": ["food_provided"], "aid_value_cents": 2500,
         "body": "Offline visit note.", "finalize": True}
    d.update(over)
    return d


def test_sync_creates_finalized_notes(world, auth, u):
    client = auth(world.coord_u)
    drafts = [_draft(world, occurred_at=f"2026-06-1{i}T09:00:00Z")
              for i in (0, 1, 2)]
    resp = client.post(u("sync"), {"drafts": drafts}, **SYNC_KW)
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert [r["status"] for r in results] == ["created"] * 3
    assert CaseNote.objects.filter(case=world.case, status="final").count() == 3


def test_sync_replay_is_idempotent(world, auth, u):
    client = auth(world.coord_u)
    drafts = [_draft(world)]
    first = client.post(u("sync"), {"drafts": drafts}, **SYNC_KW).json()["results"]
    count = CaseNote.objects.count()
    second = client.post(u("sync"), {"drafts": drafts}, **SYNC_KW).json()["results"]
    assert second[0]["status"] == "duplicate"
    assert second[0]["note_id"] == first[0]["note_id"]
    assert CaseNote.objects.count() == count


def test_sync_flags_same_hour_duplicates(world, auth, u):
    client = auth(world.coord_u)
    drafts = [_draft(world, occurred_at="2026-06-12T10:00:00Z"),
              _draft(world, occurred_at="2026-06-12T10:20:00Z")]
    results = client.post(u("sync"), {"drafts": drafts},
                          **SYNC_KW).json()["results"]
    assert any(r.get("dup_warning") for r in results)


def test_sync_requires_fresh_sensitive_session(world, auth, u):
    client = auth(world.coord_u, stamp=False)  # logged in, 4h stamp missing
    resp = client.post(u("sync"), {"drafts": [_draft(world)]}, **SYNC_KW)
    assert resp.status_code == 403
    assert resp.json() == {"reauth": True}
    assert CaseNote.objects.count() == 0


def test_sync_forbidden_case_errors_per_item(world, auth, u):
    client = auth(world.plain_u)  # member with no case access
    results = client.post(u("sync"), {"drafts": [_draft(world)]},
                          **SYNC_KW).json()["results"]
    assert results[0]["status"] == "error"
    assert results[0]["error"] == "forbidden"
    assert CaseNote.objects.count() == 0
