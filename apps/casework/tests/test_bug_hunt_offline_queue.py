"""2026-10 bug hunt: the offline visit queue belonged to the browser, not to the person.

Drafts queued on a shared device (a parish tablet) carried no author, and the next person to
sign in synced them, so their CaseNotes were filed under the wrong coordinator. A queued draft
now names its author; the client sends only the signed-in person's drafts, and the server
refuses a draft whose author is someone else. The JavaScript half cannot run under pytest; the
wiring it depends on is pinned below.
"""

import uuid
from pathlib import Path

import pytest
from django.conf import settings

from apps.casework.models import CaseNote

pytestmark = pytest.mark.django_db
SYNC_KW = {"content_type": "application/json"}


def _draft(world, **over):
    d = {
        "client_uuid": str(uuid.uuid4()),
        "case_id": str(world.case.pk),
        "kind": "visit",
        "occurred_at": "2026-06-12T15:04:00Z",
        "location_kind": "home",
        "actions": [],
        "body": "Offline visit note.",
        "finalize": True,
    }
    d.update(over)
    return d


def test_a_draft_queued_by_another_account_is_refused(world, auth, u):
    client = auth(world.coord_u)
    draft = _draft(world, author=str(world.admin_u.pk))

    results = client.post(u("sync"), {"drafts": [draft]}, **SYNC_KW).json()["results"]

    assert results[0]["status"] == "error"
    assert results[0]["error"] == "wrong_author"
    assert not CaseNote.objects.filter(client_uuid=draft["client_uuid"]).exists()


def test_the_authors_own_draft_syncs(world, auth, u):
    client = auth(world.coord_u)
    draft = _draft(world, author=str(world.coord_u.pk))
    results = client.post(u("sync"), {"drafts": [draft]}, **SYNC_KW).json()["results"]
    assert results[0]["status"] == "created"
    assert CaseNote.objects.get(client_uuid=draft["client_uuid"]).author == world.coordinator


def test_the_visit_form_tells_the_script_who_is_signed_in(world, auth, u):
    html = auth(world.coord_u).get(u("visit")).content.decode()
    assert f'data-user-id="{world.coord_u.pk}"' in html


def test_the_script_queues_and_sends_by_author():
    js = (Path(settings.BASE_DIR) / "static" / "casework" / "visit_offline.js").read_text()
    assert "form.dataset.userId" in js
    assert "author: userId" in js
    assert "isMine" in js
