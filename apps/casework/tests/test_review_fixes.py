"""Regression tests for the 2026-07-03 casework adversarial-review findings:
A) FollowUpStatusView leaked restricted-case detail to a no-access assignee;
B) SyncView._one 500'd the whole batch / silently corrupted timestamps on bad input;
C) the 4-hour reauth gate was under-tested and the stamp wasn't user-bound.
"""

import json
import time

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.casework.middleware import SESSION_KEY, SESSION_USER_KEY
from apps.casework.models import CaseFile, CaseNote, FollowUp

pytestmark = pytest.mark.django_db


def _restricted_case_with_followup(world, detail="SHELTER ADDRESS 12 Oak St"):
    case = CaseFile.objects.create(
        community=world.community,
        subject_person=world.person,
        opened_by=world.coordinator,
        assigned_to=world.coordinator,
        consent=world.consent,
        sensitivity="restricted",
    )
    fu = FollowUp(
        case=case,
        created_by=world.coordinator,
        assigned_to=world.coordinator2,  # assignee of the follow-up, NOT of the case
        title="check in",
        due_date=timezone.localdate(),
    )
    fu.detail = detail
    fu.save()
    return case, fu


# ── A: FollowUpStatusView must re-check case access before rendering detail ──


def test_followup_status_blocks_assignee_without_case_access(world, auth):
    case, fu = _restricted_case_with_followup(world)
    # coordinator2 is the follow-up's assignee but has NO access to this
    # restricted case (not case-assigned, not admin, no grant).
    client = auth(world.coord2_u)
    resp = client.post(
        reverse("casework:followup-status", kwargs={"slug": world.community.slug, "pk": fu.pk}),
        {"status": "done"},
        HTTP_HX_REQUEST="true",
    )
    assert resp.status_code == 403
    assert b"SHELTER ADDRESS" not in resp.content
    fu.refresh_from_db()
    assert fu.status == "open"  # unchanged


def test_followup_status_allows_admin(world, auth):
    case, fu = _restricted_case_with_followup(world)
    client = auth(world.admin_u)  # admin always has case access
    resp = client.post(
        reverse("casework:followup-status", kwargs={"slug": world.community.slug, "pk": fu.pk}),
        {"status": "done"},
        HTTP_HX_REQUEST="true",
    )
    assert resp.status_code == 200
    fu.refresh_from_db()
    assert fu.status == "done"


# ── B: SyncView input validation — bad items error per-item, never 500 the batch ──


def _sync(client, world, item):
    return client.post(
        reverse("casework:sync", kwargs={"slug": world.community.slug}),
        data=json.dumps({"drafts": [item]}),
        content_type="application/json",
    )


@pytest.fixture
def sync_client(world, auth):
    return auth(world.coord_u)  # coordinator has CONTRIBUTOR on the standard world.case


def test_malformed_client_uuid_is_per_item_error_not_500(world, sync_client):
    resp = _sync(sync_client, world, {"client_uuid": "not-a-uuid", "case_id": str(world.case.pk), "body": "x"})
    assert resp.status_code == 200
    assert resp.json()["results"][0]["error"] == "invalid client_uuid"
    assert CaseNote.objects.filter(case=world.case).count() == 0


def test_wrong_type_body_is_per_item_error(world, sync_client):
    import uuid

    resp = _sync(sync_client, world, {"client_uuid": str(uuid.uuid4()), "case_id": str(world.case.pk), "body": 123})
    assert resp.status_code == 200
    assert resp.json()["results"][0]["error"] == "body required"


def test_unparseable_occurred_at_is_error_not_silent_now(world, sync_client):
    """A present-but-garbage timestamp must be a per-item error, never silently
    stamped with now() (which would corrupt the record's legal time)."""
    import uuid

    resp = _sync(
        sync_client,
        world,
        {"client_uuid": str(uuid.uuid4()), "case_id": str(world.case.pk), "body": "visited", "occurred_at": "garbage"},
    )
    assert resp.status_code == 200
    assert resp.json()["results"][0]["error"] == "invalid occurred_at"
    assert CaseNote.objects.filter(case=world.case).count() == 0


def test_wrong_type_occurred_at_is_error(world, sync_client):
    import uuid

    resp = _sync(
        sync_client,
        world,
        {"client_uuid": str(uuid.uuid4()), "case_id": str(world.case.pk), "body": "v", "occurred_at": 1730000000},
    )
    assert resp.status_code == 200
    assert resp.json()["results"][0]["error"] == "invalid occurred_at"


def test_out_of_range_duration_is_error(world, sync_client):
    import uuid

    resp = _sync(
        sync_client,
        world,
        {
            "client_uuid": str(uuid.uuid4()),
            "case_id": str(world.case.pk),
            "body": "visited",
            "duration_minutes": 999999,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["results"][0]["error"] == "invalid duration_minutes"


def test_negative_aid_is_error(world, sync_client):
    import uuid

    resp = _sync(
        sync_client,
        world,
        {"client_uuid": str(uuid.uuid4()), "case_id": str(world.case.pk), "body": "v", "aid_value_cents": -5},
    )
    assert resp.status_code == 200
    assert resp.json()["results"][0]["error"] == "invalid aid_value_cents"


def test_valid_item_still_creates_note(world, sync_client):
    import uuid

    resp = _sync(
        sync_client,
        world,
        {"client_uuid": str(uuid.uuid4()), "case_id": str(world.case.pk), "body": "all well", "duration_minutes": 30},
    )
    assert resp.status_code == 200
    assert resp.json()["results"][0]["status"] == "created"


# ── C: the reauth gate — negative coverage + user binding ──


def test_absent_stamp_redirects_to_reauth(world, auth):
    client = auth(world.coord_u, stamp=False)
    resp = client.get(reverse("casework:detail", kwargs={"slug": world.community.slug, "pk": world.case.pk}))
    assert resp.status_code == 302
    assert "reauth" in resp["Location"]


def test_stamp_from_another_user_is_rejected(world, auth):
    client = auth(world.coord_u, stamp=False)
    s = client.session
    s[SESSION_KEY] = time.time()  # fresh…
    s[SESSION_USER_KEY] = str(world.admin_u.pk)  # …but earned by a different user
    s.save()
    resp = client.get(reverse("casework:detail", kwargs={"slug": world.community.slug, "pk": world.case.pk}))
    assert resp.status_code == 302
    assert "reauth" in resp["Location"]
