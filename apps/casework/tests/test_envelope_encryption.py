"""
§12.2 phase 1 — envelope encryption for Need.on_behalf_of.

Reuses the casework `world` fixture and the defensive Need builder from the
§10 tests. NOTE: when stage 4 removes the legacy read branch, delete
test_legacy_rows_dual_read along with it.
"""
import io
import uuid

import pytest
from cryptography.fernet import Fernet
from django.core.management import call_command

from apps.audit.models import AuditLog
from apps.people import crypto

from .test_s10_improvements import _make_need

pytestmark = pytest.mark.django_db


def _envelope_need(world, name="Maria Quiet"):
    need = _make_need(world, f"Envelope test {uuid.uuid4().hex[:6]}")
    need.on_behalf_of_name = name
    need.save(update_fields=["on_behalf_of", "on_behalf_of_dek"])
    need.refresh_from_db()
    return need


def _legacy_need(world, name="Old Style"):
    need = _make_need(world, f"Legacy test {uuid.uuid4().hex[:6]}")
    need.on_behalf_of = crypto.encrypt_str(name)   # direct-KEK, pre-envelope
    need.on_behalf_of_dek = None
    need.save(update_fields=["on_behalf_of", "on_behalf_of_dek"])
    need.refresh_from_db()
    return need


# ------------------------------------------------------------- round trips
def test_setter_envelopes_and_roundtrips(world):
    need = _envelope_need(world)
    assert need.on_behalf_of_name == "Maria Quiet"
    assert need.on_behalf_of_dek is not None
    assert b"Maria" not in bytes(need.on_behalf_of)


def test_each_need_gets_its_own_dek(world):
    a = _envelope_need(world, "Same Name")
    b = _envelope_need(world, "Same Name")
    assert bytes(a.on_behalf_of) != bytes(b.on_behalf_of)
    assert bytes(a.on_behalf_of_dek) != bytes(b.on_behalf_of_dek)


def test_setter_rejects_bytes_loudly(world):
    need = _make_need(world, "Bytes guard")
    with pytest.raises(TypeError):
        need.on_behalf_of_name = b"pre-encrypted-noise"


def test_clearing_nulls_both_columns(world):
    need = _envelope_need(world)
    need.on_behalf_of_name = None
    need.save(update_fields=["on_behalf_of", "on_behalf_of_dek"])
    need.refresh_from_db()
    assert need.on_behalf_of is None and need.on_behalf_of_dek is None
    assert need.on_behalf_of_name is None


def test_legacy_rows_dual_read(world):
    need = _legacy_need(world, "Old Style")
    assert need.on_behalf_of_dek is None
    assert need.on_behalf_of_name == "Old Style"


# ------------------------------------------------------------- backfill cmd
def test_backfill_converts_legacy_and_is_idempotent(world):
    legacy1 = _legacy_need(world, "Anna")
    legacy2 = _legacy_need(world, "Bea")
    already = _envelope_need(world, "Cleo")
    untouched_dek = bytes(already.on_behalf_of_dek)

    call_command("migrate_on_behalf_envelope")

    for need, name in ((legacy1, "Anna"), (legacy2, "Bea")):
        need.refresh_from_db()
        assert need.on_behalf_of_dek is not None
        assert need.on_behalf_of_name == name
    already.refresh_from_db()
    assert bytes(already.on_behalf_of_dek) == untouched_dek  # not re-touched

    snapshot = {n.pk: bytes(n.on_behalf_of_dek)
                for n in (legacy1, legacy2, already)}
    call_command("migrate_on_behalf_envelope")               # second run
    for need in (legacy1, legacy2, already):
        need.refresh_from_db()
        assert bytes(need.on_behalf_of_dek) == snapshot[need.pk]


def test_backfill_to_legacy_reverses_for_rollback(world):
    need = _envelope_need(world, "Rollback Row")
    call_command("migrate_on_behalf_envelope", to_legacy=True)
    need.refresh_from_db()
    assert need.on_behalf_of_dek is None
    assert crypto.decrypt_str(need.on_behalf_of) == "Rollback Row"
    assert need.on_behalf_of_name == "Rollback Row"          # legacy branch


def test_verify_census_output(world):
    _legacy_need(world)
    _envelope_need(world)
    out = io.StringIO()
    call_command("migrate_on_behalf_envelope", verify=True, stdout=out)
    text = out.getvalue()
    assert "legacy=1" in text and "envelope=1" in text and "unreadable=0" in text


# ------------------------------------------------------------- KEK rotation
def test_kek_rotation_rewraps_deks(world, settings):
    old_key = settings.ENCRYPTION_KEY
    need = _envelope_need(world, "Rotated Name")     # wrapped under old_key
    old_wrap = bytes(need.on_behalf_of_dek)

    new_key = Fernet.generate_key().decode()
    settings.ENCRYPTION_KEYS = [new_key, old_key]    # step 2 of the runbook
    assert need.on_behalf_of_name == "Rotated Name"  # MultiFernet still reads

    call_command("rotate_keks")                      # step 3
    need.refresh_from_db()
    assert bytes(need.on_behalf_of_dek) != old_wrap

    settings.ENCRYPTION_KEYS = [new_key]             # step 5: old key retired
    assert need.on_behalf_of_name == "Rotated Name"  # envelope survives


def test_direct_fields_need_old_kek_until_rewritten(world, settings):
    """Documents runbook step 4: direct-KEK fields (casework 🔒 columns)
    re-encrypt only when rewritten, so the old key must stay configured
    until phase 2 — retiring it early makes them unreadable."""
    old_key = settings.ENCRYPTION_KEY
    new_key = Fernet.generate_key().decode()

    settings.ENCRYPTION_KEYS = [new_key, old_key]
    assert world.person.display_name == "Maria Garcia"   # still reads

    settings.ENCRYPTION_KEYS = [new_key]                 # premature retirement
    with pytest.raises(ValueError):
        _ = world.person.display_name


# ------------------------------------------------------------- crypto-shred
def test_shred_command_destroys_and_audits(world):
    need = _envelope_need(world, "To Be Forgotten")
    call_command("shred_on_behalf", need_ids=[str(need.pk)])
    need.refresh_from_db()
    assert need.on_behalf_of is None and need.on_behalf_of_dek is None
    assert need.on_behalf_of_name is None
    row = AuditLog.objects.get(action="need.on_behalf_shredded",
                               resource_id=need.pk)
    assert row.details["reason"] == "erasure_request"
