"""Seven-year retention shred for closed cases (policy set 2026-07-11).
Bulk .update() is the point: finalized notes refuse save()-edits by design,
and a policy shred is not an edit."""

import datetime

from django.utils import timezone

from apps.audit.models import AuditLog
from apps.casework.models import CaseFile, CaseNote
from apps.casework.tasks import CASE_RETENTION_DAYS, shred_aged_cases


def _age_and_close(case, days):
    case.summary = "Sensitive family situation"
    case.save()
    note = CaseNote(case=case, author=case.opened_by)
    note.body = "Visited the family; details are sensitive."
    note.save()
    CaseFile.objects.filter(pk=case.pk).update(
        status=CaseFile.STATUS_CLOSED,
        closed_at=timezone.now() - datetime.timedelta(days=days),
    )
    return note


def test_aged_closed_case_is_shredded(world):
    note = _age_and_close(world.case, CASE_RETENTION_DAYS + 1)
    result = shred_aged_cases()
    case = CaseFile.objects.get(pk=world.case.pk)
    note.refresh_from_db()
    assert case.summary_enc is None and case.summary_enc_dek is None
    assert case.summary is None  # reads clean
    assert note.body_enc is None and note.body_enc_dek is None
    assert "1 aged closed cases" in result
    assert AuditLog.objects.filter(action="case.retention_shredded", resource_id=case.pk).count() == 1


def test_recently_closed_case_is_kept(world):
    _age_and_close(world.case, days=30)
    shred_aged_cases()
    case = CaseFile.objects.get(pk=world.case.pk)
    assert case.summary_enc is not None


def test_shred_is_idempotent(world):
    _age_and_close(world.case, CASE_RETENTION_DAYS + 1)
    shred_aged_cases()
    assert "0 aged closed cases" in shred_aged_cases()
