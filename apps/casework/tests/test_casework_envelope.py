"""
Stage D tests: envelope round-trips for all four casework PII fields, a real
data-migration test proving a direct-KEK row (incl. a FINALIZED note) is
readable afterward, idempotency, the reverse migration, the census command,
and KEK rotation. Mirrors test_envelope_encryption.py.
"""

import io

import pytest
from cryptography.fernet import Fernet
from django.apps import apps as django_apps
from django.core.management import call_command
from django.utils import timezone

from apps.casework.envelope_backfill import forward_func, reverse_func
from apps.casework.models import CaseFile, CaseNote, FollowUp, WarmHandoff
from apps.people import crypto

pytestmark = pytest.mark.django_db


def _legacy_blob(text):
    """Direct-KEK ciphertext, as written before this migration."""
    return crypto.encrypt_str(text)


# ----------------------------------------------------- envelope round-trips
def test_casefile_summary_roundtrip(world):
    world.case.summary = "Family of four; rent arrears."
    world.case.save(update_fields=["summary_enc", "summary_enc_dek"])
    world.case.refresh_from_db()
    assert world.case.summary == "Family of four; rent arrears."
    assert world.case.summary_enc_dek is not None
    assert b"rent" not in bytes(world.case.summary_enc)


def test_casenote_body_roundtrip(world, make_note):
    note = make_note(body="She mentioned the eviction letter.")
    note.refresh_from_db()
    assert note.body == "She mentioned the eviction letter."
    assert note.body_enc_dek is not None
    assert b"eviction" not in bytes(note.body_enc)


def test_followup_detail_roundtrip(world):
    fu = FollowUp(
        case=world.case,
        created_by=world.coordinator,
        assigned_to=world.coordinator,
        title="Call back",
        due_date=timezone.localdate(),
    )
    fu.detail = "Ask about the deposit."
    fu.save()
    fu.refresh_from_db()
    assert fu.detail == "Ask about the deposit."
    assert fu.detail_enc_dek is not None
    assert b"deposit" not in bytes(fu.detail_enc)


def test_warmhandoff_summary_roundtrip(world):
    ho = WarmHandoff(case=world.case, from_member=world.coordinator, to_member=world.coordinator2)
    ho.summary = "Prefers afternoon visits."
    ho.save()
    ho.refresh_from_db()
    assert ho.summary == "Prefers afternoon visits."
    assert ho.summary_enc_dek is not None
    assert b"afternoon" not in bytes(ho.summary_enc)


def test_each_record_gets_its_own_dek(world, make_note):
    a = make_note(body="Same text")
    b = make_note(body="Same text")
    assert bytes(a.body_enc) != bytes(b.body_enc)
    assert bytes(a.body_enc_dek) != bytes(b.body_enc_dek)


def test_setter_rejects_bytes(world):
    with pytest.raises(TypeError):
        world.case.summary = b"pre-encrypted"


def test_clearing_nulls_both_columns(world, make_note):
    note = make_note(body="temp")
    note.body = None
    note.save(update_fields=["body_enc", "body_enc_dek"])
    note.refresh_from_db()
    assert note.body_enc is None and note.body_enc_dek is None
    assert note.body is None


# ------------------------------------------------- the data-migration proof
def _seed_legacy_casefile(world, text):
    case = CaseFile.objects.create(
        community=world.community,
        subject_person=world.person,
        opened_by=world.coordinator,
        assigned_to=world.coordinator,
        consent=world.consent,
    )
    CaseFile.objects.filter(pk=case.pk).update(summary_enc=_legacy_blob(text), summary_enc_dek=None)
    return case


def _seed_legacy_final_note(world, text):
    note = CaseNote(case=world.case, author=world.coordinator, status="draft")
    note.body = "placeholder"
    note.save()
    # Direct-KEK ciphertext, NULL DEK, status=final — via .update() so the
    # immutability guard doesn't block the seed (and proves the migration can
    # convert finalized notes that .save() would refuse).
    CaseNote.objects.filter(pk=note.pk).update(
        body_enc=_legacy_blob(text), body_enc_dek=None, status="final", finalized_at=timezone.now()
    )
    return note


def test_data_migration_converts_direct_kek_rows(world):
    case = _seed_legacy_casefile(world, "Legacy summary text")
    final_note = _seed_legacy_final_note(world, "Legacy FINAL note body")
    fu = FollowUp(
        case=world.case,
        created_by=world.coordinator,
        assigned_to=world.coordinator,
        title="t",
        due_date=timezone.localdate(),
    )
    fu.save()
    FollowUp.objects.filter(pk=fu.pk).update(detail_enc=_legacy_blob("Legacy detail"), detail_enc_dek=None)
    ho = WarmHandoff(case=world.case, from_member=world.coordinator, to_member=world.coordinator2)
    ho.save()
    WarmHandoff.objects.filter(pk=ho.pk).update(summary_enc=_legacy_blob("Legacy handoff"), summary_enc_dek=None)

    for obj, attr in (
        (case, "summary_enc_dek"),
        (final_note, "body_enc_dek"),
        (fu, "detail_enc_dek"),
        (ho, "summary_enc_dek"),
    ):
        obj.refresh_from_db()
        assert getattr(obj, attr) is None  # all start legacy

    forward_func(django_apps)  # the real migration logic

    case.refresh_from_db()
    final_note.refresh_from_db()
    fu.refresh_from_db()
    ho.refresh_from_db()
    assert case.summary_enc_dek and case.summary == "Legacy summary text"
    # headline requirement, incl. a FINALIZED note:
    assert final_note.body_enc_dek and final_note.body == "Legacy FINAL note body"
    assert fu.detail_enc_dek and fu.detail == "Legacy detail"
    assert ho.summary_enc_dek and ho.summary == "Legacy handoff"


def test_data_migration_is_idempotent(world):
    case = _seed_legacy_casefile(world, "Once")
    forward_func(django_apps)
    case.refresh_from_db()
    ct, dek = bytes(case.summary_enc), bytes(case.summary_enc_dek)
    forward_func(django_apps)  # second run = no-op
    case.refresh_from_db()
    assert bytes(case.summary_enc) == ct
    assert bytes(case.summary_enc_dek) == dek
    assert case.summary == "Once"


def test_reverse_migration_restores_direct_kek(world):
    case = _seed_legacy_casefile(world, "Roundtrip")
    forward_func(django_apps)
    case.refresh_from_db()
    assert case.summary_enc_dek is not None
    reverse_func(django_apps)
    case.refresh_from_db()
    assert case.summary_enc_dek is None
    assert crypto.decrypt_str(case.summary_enc) == "Roundtrip"
    assert case.summary == "Roundtrip"


def test_census_command_reports_state(world, make_note):
    _seed_legacy_casefile(world, "legacy one")
    make_note(body="envelope one")
    out = io.StringIO()
    call_command("casework_envelope_status", stdout=out)
    text = out.getvalue()
    assert "CaseFile.summary_enc:" in text
    assert "legacy=1" in text
    assert "envelope=1" in text


# ------------------------------------------------------------ KEK rotation
def test_rotation_rewraps_casework_deks(world, make_note, settings):
    old_key = settings.ENCRYPTION_KEY
    note = make_note(body="Rotate me")
    old_wrap = bytes(note.body_enc_dek)

    new_key = Fernet.generate_key().decode()
    settings.ENCRYPTION_KEYS = [new_key, old_key]
    call_command("rotate_keks")
    note.refresh_from_db()
    assert bytes(note.body_enc_dek) != old_wrap

    settings.ENCRYPTION_KEYS = [new_key]  # retire old KEK
    assert note.body == "Rotate me"  # survives rotation
