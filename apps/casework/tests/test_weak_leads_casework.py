"""The bug hunt's weaker leads, casework group (verified 2026-10-13 on Postgres, all real).

Casework holds nothing in production yet; these are fixed before a parish uses it.

L14  A recorder who was removed or left could still revoke the consents they recorded, freezing
     each case. Only a recorder still in the community may.
L18  Replaying a note's client_uuid showed another author's draft or a discarded note.
L19  The offline sync answered 500 to a body of the wrong shape.
L20  Renewing a member's expired grant was a 409 until someone revoked the dead one.
L21  Someone coordinating in two communities got only one community's overdue digest.
L22  Case search looked only at the 200 most recently updated cases.
L23  The warm-handoff screen decrypted the summary without a read audit.
L24  The re-auth redirect cut the gated URL at its first '&'.
L30  The export printed visit times in raw UTC with no zone, so evening visits had tomorrow's date.
L43  A handoff took no lock and checked no status: two at once both landed; a closed case took one.
L44  A closed case still took notes, follow-ups and synced visits.
L65  An HTMX save after the 4-hour stamp swapped the whole re-auth page into the notes list, and
     the no-JS path ended on a 405.
L69  An amendment had no length cap (notes have 8000).
"""

import json
import time
import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.casework import access
from apps.casework.middleware import MAX_AGE_SECONDS, SESSION_KEY, SESSION_USER_KEY
from apps.casework.models import CaseAccessGrant, CaseFile, CaseNote, FollowUp, WarmHandoff
from apps.casework.tasks import followup_overdue_digest
from apps.communities.models import Community, Member
from apps.consent.models import Consent
from apps.notifications.models import Notification
from apps.people.models import Person

pytestmark = pytest.mark.django_db

PASSWORD = "pw-Str0ng!pass"
NOTE = {"kind": "visit", "occurred_at": "2026-10-12T10:00", "location_kind": "home", "body": "Visit."}


# ── L14 ────────────────────────────────────────────────────────


@pytest.mark.parametrize("how", ["removed", "left"])
def test_a_recorder_who_is_gone_cannot_revoke(world, auth, how):
    from apps.moderation.services import leave_community, remove_member

    p = Person(created_in_community=world.community, created_by=world.coordinator)
    p.display_name = "B O"
    p.save()
    consent = Consent.objects.create(
        subject_person=p,
        recorded_by=world.coordinator,
        granted_to=world.community.name,
        grantee_type="community",
        grantee_id=world.community.id,
        scope=["case_records"],
        purpose="Case records",
        method="verbal",
    )
    if how == "removed":
        remove_member(world.coordinator, by=world.admin)
    else:
        leave_community(world.coordinator)

    resp = auth(world.coord_u).post(f"/consent/{consent.pk}/revoke/")

    assert resp.status_code == 404
    consent.refresh_from_db()
    assert consent.status == "active"


# ── L18 ────────────────────────────────────────────────────────


@pytest.mark.parametrize("status", ["draft", "discarded"])
def test_a_replayed_uuid_never_shows_what_the_case_page_hides(world, auth, u, make_note, status):
    hidden = make_note(author=world.coordinator, status=status, body="ANNE-PRIVATE-TEXT", client_uuid=uuid.uuid4())
    resp = auth(world.coord2_u).post(
        u("note-create", pk=world.case.pk), {**NOTE, "client_uuid": str(hidden.client_uuid)}, HTTP_HX_REQUEST="true"
    )
    assert resp.status_code == 409
    assert "ANNE-PRIVATE-TEXT" not in resp.content.decode()


def test_a_replay_of_your_own_note_still_returns_it(world, auth, u):
    c = auth(world.coord_u)
    cu = str(uuid.uuid4())
    c.post(u("note-create", pk=world.case.pk), {**NOTE, "body": "MINE", "client_uuid": cu})
    resp = c.post(
        u("note-create", pk=world.case.pk), {**NOTE, "body": "MINE", "client_uuid": cu}, HTTP_HX_REQUEST="true"
    )
    assert resp.status_code == 200 and "MINE" in resp.content.decode()


# ── L19 ────────────────────────────────────────────────────────


def _item(w, **o):
    return {"client_uuid": str(uuid.uuid4()), "case_id": str(w.case.pk), "body": "v", **o}


SHAPES = {
    "array": lambda w: [],
    "null": lambda w: None,
    "number": lambda w: 5,
    "drafts_int": lambda w: {"drafts": 5},
    "drafts_dict": lambda w: {"drafts": {"a": 1}},
    "kind_list": lambda w: {"drafts": [_item(w, kind=["visit"])]},
    "kind_dict": lambda w: {"drafts": [_item(w, kind={"a": 1})]},
    "location_list": lambda w: {"drafts": [_item(w, location_kind=["home"])]},
}


@pytest.mark.parametrize("shape", list(SHAPES))
def test_sync_answers_a_wrong_shape_without_a_500(world, auth, u, shape):
    c = auth(world.coord_u)
    c.raise_request_exception = False
    resp = c.post(u("sync"), data=json.dumps(SHAPES[shape](world)), content_type="application/json")
    assert resp.status_code in (200, 400)


# ── L20 ────────────────────────────────────────────────────────


def test_an_expired_grant_can_be_renewed(world, auth, u):
    CaseAccessGrant.objects.create(
        case=world.case,
        member=world.plain,
        role="viewer",
        granted_by=world.coordinator,
        reason="covering March",
        expires_at=timezone.now() - timedelta(days=1),
    )
    resp = auth(world.coord_u).post(
        u("grant-create", pk=world.case.pk), {"member": str(world.plain.pk), "role": "viewer", "reason": "April"}
    )
    assert resp.status_code == 302
    assert access.case_access(world.plain, world.case) == access.VIEWER


# ── L21 ────────────────────────────────────────────────────────


def test_each_community_gets_its_own_digest(world):
    FollowUp.objects.create(
        case=world.case,
        created_by=world.coordinator,
        assigned_to=world.coordinator,
        title="Utility call (St. Brigid)",
        due_date=timezone.localdate() - timedelta(days=1),
    )
    c2 = Community.objects.create(name="St. Anne Conference", slug="st-anne", created_by=world.admin_u)
    a2 = Member.objects.create(
        user=world.coord_u, community=c2, role="coordinator", display_name="Anne", is_active=True
    )
    p2 = Person(created_in_community=c2, created_by=a2)
    p2.display_name = "Pat Doe"
    p2.save()
    k2 = CaseFile.objects.create(
        community=c2, subject_person=p2, opened_by=a2, assigned_to=a2, emergency_opened=True, sensitivity="standard"
    )
    FollowUp.objects.create(
        case=k2,
        created_by=a2,
        assigned_to=a2,
        title="Groceries (St. Anne)",
        due_date=timezone.localdate() - timedelta(days=3),
    )

    followup_overdue_digest()

    bodies = " ".join(
        Notification.objects.filter(recipient=world.coord_u, type="followup_overdue").values_list("body", flat=True)
    )
    assert "St. Brigid" in bodies and "St. Anne" in bodies
    assert followup_overdue_digest() == 0  # still once a day each


# ── L22 ────────────────────────────────────────────────────────


def test_search_reaches_every_case(world, auth, u):
    kw = dict(
        community=world.community,
        subject_person=world.person,
        opened_by=world.coordinator,
        assigned_to=world.coordinator,
        consent=world.consent,
        sensitivity="standard",
    )
    old = CaseFile.objects.create(physical_ref="BOX-7-FOLDER-12", **kw)
    CaseFile.objects.filter(pk=old.pk).update(updated_at=timezone.now() - timedelta(days=400))
    CaseFile.objects.bulk_create([CaseFile(**kw) for _ in range(200)])
    c, link = auth(world.coord_u), u("detail", pk=old.pk)
    assert link in c.get(u("list"), {"q": "BOX-7"}).content.decode()
    assert link in c.get(u("list"), {"q": old.short_code.lower()}).content.decode()


# ── L23 ────────────────────────────────────────────────────────


def test_the_handoff_screen_writes_a_read_audit(world, auth, u):
    summary = "Ex-partner released Tuesday; never visit before 4pm."
    auth(world.admin_u).post(
        u("assign", pk=world.case.pk), {"to_member": str(world.coordinator2.pk), "summary": summary}
    )
    c = auth(world.coord2_u)
    before = set(AuditLog.objects.values_list("pk", flat=True))

    resp = c.get(u("detail", pk=world.case.pk))

    assert summary.encode() in resp.content
    assert AuditLog.objects.exclude(pk__in=before).filter(user=world.coord2_u, action="case.viewed").exists()


# ── L24, L65 ───────────────────────────────────────────────────


def _expired(auth, user):
    client = auth(user)
    s = client.session
    s[SESSION_KEY] = time.time() - MAX_AGE_SECONDS - 60
    s[SESSION_USER_KEY] = str(user.pk)
    s.save()
    return client


def test_reauth_returns_to_the_whole_url(world, auth, u):
    c = auth(world.coord_u, stamp=False)
    target = u("list") + "?status=open&mine=1&q=ABC"
    loc = c.get(target)["Location"]
    nxt = c.get(loc).context["next"]
    assert c.post(loc, {"password": PASSWORD, "next": nxt})["Location"] == target


def test_an_htmx_save_after_expiry_reloads_into_reauth(world, auth, u):
    resp = _expired(auth, world.coord_u).post(u("note-create", pk=world.case.pk), NOTE, HTTP_HX_REQUEST="true")
    assert resp.status_code == 204
    assert "reauth" in resp["HX-Redirect"]


def test_a_plain_save_after_expiry_comes_back_to_the_case_not_a_405(world, auth, u):
    c = _expired(auth, world.coord_u)
    loc = c.post(u("note-create", pk=world.case.pk), NOTE)["Location"]
    done = c.post(loc, {"password": PASSWORD, "next": c.get(loc).context["next"]})
    assert done["Location"] == u("detail", pk=world.case.pk)
    assert c.get(done["Location"]).status_code == 200


# ── L30 ────────────────────────────────────────────────────────


def test_the_export_shows_local_visit_times(world, auth, u):
    auth(world.coord_u).post(
        u("note-create", pk=world.case.pk),
        {
            "kind": "visit",
            "occurred_at": "2026-10-12T19:30",
            "location_kind": "home",
            "body": "Evening.",
            "finalize": "1",
        },
    )
    text = auth(world.admin_u).get(u("export", pk=world.case.pk)).content.decode()
    line = next(row for row in text.splitlines() if row.startswith("--- "))
    assert line.startswith("--- 2026-10-12 19:30")


# ── L43, L44 ───────────────────────────────────────────────────


def _close(world, auth, u):
    auth(world.admin_u).post(u("status", pk=world.case.pk), {"status": "closed"})
    world.case.refresh_from_db()
    assert world.case.status == "closed"


def test_a_closed_case_takes_no_new_writing(world, auth, u):
    _close(world, auth, u)
    c = auth(world.coord_u)
    assert c.post(u("note-create", pk=world.case.pk), NOTE).status_code == 409
    followup = {"title": "Check in", "due_date": "2026-10-01", "assigned_to": str(world.coordinator.pk)}
    assert c.post(u("followup-create", pk=world.case.pk), followup).status_code == 409
    sync = c.post(
        u("sync"),
        data=json.dumps({"drafts": [_item(world)]}),
        content_type="application/json",
    ).json()["results"][0]
    assert sync["error"] == "case_closed"
    handoff = c.post(
        u("assign", pk=world.case.pk), {"to_member": str(world.coordinator2.pk), "summary": "Rent hearing on Friday."}
    )
    assert handoff.status_code == 409
    assert not world.case.notes.exists() and not world.case.followups.exists()
    assert not WarmHandoff.objects.filter(case=world.case).exists()


def test_a_handoff_rechecks_the_assignee_under_the_lock(world, auth, u, monkeypatch):
    from apps.casework import views as cw_views

    real_is_valid = cw_views.AssignForm.is_valid

    def another_handoff_landed_first(self):
        CaseFile.objects.filter(pk=world.case.pk).update(assigned_to=world.coordinator2)
        return real_is_valid(self)

    monkeypatch.setattr(cw_views.AssignForm, "is_valid", another_handoff_landed_first)
    resp = auth(world.coord_u).post(
        u("assign", pk=world.case.pk), {"to_member": str(world.admin.pk), "summary": "Rent hearing on Friday."}
    )

    assert resp.status_code == 403  # no longer the assignee
    assert not WarmHandoff.objects.filter(case=world.case).exists()


# ── L69 ────────────────────────────────────────────────────────


def test_an_amendment_is_capped_like_a_note(world, auth, u, make_note):
    original = make_note(status="final")
    resp = auth(world.coord_u).post(
        u("note-amend", pk=world.case.pk, note_id=original.pk), {"body": "x" * 100_000, "finalize": "1"}
    )
    assert resp.status_code == 400
    assert not CaseNote.objects.filter(amends=original).exists()
