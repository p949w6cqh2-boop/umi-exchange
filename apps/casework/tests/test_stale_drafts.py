"""Stale draft cleanup (design §3.11): drafts untouched >72h are DISCARDED via
the state machine (not deleted), audited as a system event, idempotently."""

import pytest
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.casework.models import CaseNote
from apps.casework.tasks import discard_stale_drafts


def _age(note, hours):
    # auto_now would reset updated_at on save() — use .update() to backdate in-DB.
    CaseNote.objects.filter(pk=note.pk).update(updated_at=timezone.now() - timezone.timedelta(hours=hours))


@pytest.mark.django_db
class TestStaleDraftCleanup:
    def test_stale_draft_discarded_and_audited(self, world, make_note):
        note = make_note(status="draft", body="Visited Maria; all well.")
        _age(note, 80)
        result = discard_stale_drafts()
        note.refresh_from_db()
        assert note.status == "discarded"  # transitioned, not deleted
        assert CaseNote.objects.filter(pk=note.pk).exists()  # row preserved
        ev = AuditLog.objects.filter(action="note.draft_expired", resource_id=note.id)
        assert ev.count() == 1
        assert ev.get().user_id is None  # system event
        assert ev.get().resource_type == "casenote"
        assert "Visited" not in str(ev.get().details or "")  # no body/PII in details
        assert "1" in result

    def test_recent_draft_untouched(self, world, make_note):
        note = make_note(status="draft")  # updated_at = now via auto_now
        discard_stale_drafts()
        note.refresh_from_db()
        assert note.status == "draft"  # within the 72h window
        assert AuditLog.objects.filter(action="note.draft_expired").count() == 0

    def test_final_note_never_discarded(self, world, make_note):
        note = make_note(status="final")
        _age(note, 200)
        discard_stale_drafts()
        note.refresh_from_db()
        assert note.status == "final"  # only drafts are in scope
        assert AuditLog.objects.filter(action="note.draft_expired").count() == 0

    def test_idempotent_rerun(self, world, make_note):
        note = make_note(status="draft")
        _age(note, 80)
        discard_stale_drafts()
        discard_stale_drafts()  # re-run: already discarded → no-op, no second audit row
        assert AuditLog.objects.filter(action="note.draft_expired", resource_id=note.id).count() == 1
