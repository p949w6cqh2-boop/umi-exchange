"""
Stage E contract tests: the legacy direct-KEK read branch is gone, so a
populated ciphertext with no DEK must FAIL LOUD (ValueError naming the field)
on every casework PII property — never silently mis-read. Empty rows still
return None and genuine envelope rows still decrypt.
"""

import pytest
from django.utils import timezone

from apps.casework.models import CaseFile, CaseNote, FollowUp, WarmHandoff
from apps.people import crypto

pytestmark = pytest.mark.django_db


def _dekless(model, pk, ct_field, text):
    """Write a direct-KEK ciphertext with a NULL DEK — a 'legacy' row that
    Stage E must refuse to read through the property."""
    model.objects.filter(pk=pk).update(**{ct_field: crypto.encrypt_str(text), f"{ct_field}_dek": None})


def _note(world, **kw):
    n = CaseNote(case=world.case, author=world.coordinator, status="draft", **kw)
    n.save()
    return n


def _followup(world):
    fu = FollowUp(
        case=world.case,
        created_by=world.coordinator,
        assigned_to=world.coordinator,
        title="t",
        due_date=timezone.localdate(),
    )
    fu.save()
    return fu


def _handoff(world):
    ho = WarmHandoff(case=world.case, from_member=world.coordinator, to_member=world.coordinator2)
    ho.save()
    return ho


# --------------------------------------------------- fail-loud, per field
def test_casefile_summary_dekless_raises(world):
    _dekless(CaseFile, world.case.pk, "summary_enc", "legacy")
    world.case.refresh_from_db()
    with pytest.raises(ValueError, match="CaseFile.summary"):
        _ = world.case.summary


def test_warmhandoff_summary_dekless_raises(world):
    ho = _handoff(world)
    _dekless(WarmHandoff, ho.pk, "summary_enc", "legacy")
    ho.refresh_from_db()
    with pytest.raises(ValueError, match="WarmHandoff.summary"):
        _ = ho.summary


def test_casenote_body_dekless_raises(world):
    note = _note(world)
    _dekless(CaseNote, note.pk, "body_enc", "legacy")
    note.refresh_from_db()
    with pytest.raises(ValueError, match="CaseNote.body"):
        _ = note.body


def test_followup_detail_dekless_raises(world):
    fu = _followup(world)
    _dekless(FollowUp, fu.pk, "detail_enc", "legacy")
    fu.refresh_from_db()
    with pytest.raises(ValueError, match="FollowUp.detail"):
        _ = fu.detail


# ------------------------------------------------------- happy paths intact
def test_empty_ciphertext_returns_none(world):
    # No summary ever set → no ciphertext → None, not an error.
    assert world.case.summary_enc is None
    assert world.case.summary is None


def test_envelope_row_still_reads(world):
    world.case.summary = "Family of four; rent arrears."
    world.case.save(update_fields=["summary_enc", "summary_enc_dek"])
    world.case.refresh_from_db()
    assert world.case.summary_enc_dek is not None
    assert world.case.summary == "Family of four; rent arrears."
