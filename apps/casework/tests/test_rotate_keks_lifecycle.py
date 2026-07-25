"""
KEK-rotation lifecycle regressions (bug-hunt batch 1, #1 + #10).

#1  rotate_keks re-wraps each envelope DEK via obj.save(); for a *finalized*
    CaseNote that hits the A7 immutability guard (CaseNote.save raises), so the
    command aborts partway and every model after CaseNote in the registry is
    never rotated. The existing rotation test only used a *draft* note, so the
    guard never fired.
#10 CaseFile.emergency_justification_enc_dek is a real envelope DEK but was
    absent from ENVELOPE_DEK_FIELDS, so rotation silently skipped it; retiring
    the old KEK then makes the DV justification unrecoverable. Guard test pins
    the registry to the model layout so a new envelope column can't slip out.
"""

import pytest
from cryptography.fernet import Fernet
from django.apps import apps as django_apps
from django.core.management import call_command
from django.db import models

from apps.people.management.commands.rotate_keks import ENVELOPE_DEK_FIELDS

pytestmark = pytest.mark.django_db


def test_rotate_keks_completes_with_finalized_casenote(world, make_note, settings):
    """A finalized note in the DB must not abort KEK rotation (#1)."""
    old_key = settings.ENCRYPTION_KEY
    note = make_note(body="Sensitive narrative", status="final")
    old_wrap = bytes(note.body_enc_dek)

    new_key = Fernet.generate_key().decode()
    settings.ENCRYPTION_KEYS = [new_key, old_key]
    call_command("rotate_keks")  # must not raise on the finalized note

    note.refresh_from_db()
    assert bytes(note.body_enc_dek) != old_wrap  # its wrap was rotated

    settings.ENCRYPTION_KEYS = [new_key]  # retire the old KEK
    assert note.body == "Sensitive narrative"  # still decrypts under the new KEK alone


def test_rotate_keks_rewraps_emergency_justification(world, settings):
    """The emergency/DV justification DEK must be rotated like every other (#10)."""
    old_key = settings.ENCRYPTION_KEY
    case = world.case
    case.emergency_justification = "Consentless open — imminent DV risk"
    case.save(update_fields=["emergency_justification_enc", "emergency_justification_enc_dek"])
    case.refresh_from_db()
    old_wrap = bytes(case.emergency_justification_enc_dek)

    new_key = Fernet.generate_key().decode()
    settings.ENCRYPTION_KEYS = [new_key, old_key]
    call_command("rotate_keks")
    case.refresh_from_db()
    assert bytes(case.emergency_justification_enc_dek) != old_wrap  # rotated, not skipped

    settings.ENCRYPTION_KEYS = [new_key]  # retire the old KEK
    assert case.emergency_justification == "Consentless open — imminent DV risk"  # survives retirement


def test_envelope_dek_registry_covers_all_fields():
    """Every envelope DEK column in the schema must be registered for rotation (#10).

    A DEK left out of ENVELOPE_DEK_FIELDS is never re-wrapped, so retiring the
    old KEK destroys that field. Pin the registry to the model layout.
    """
    registered = {(app, model, field) for app, model, field in ENVELOPE_DEK_FIELDS}
    missing = []
    for model in django_apps.get_models():
        for field in model._meta.get_fields():
            if isinstance(field, models.BinaryField) and field.name.endswith("_dek"):
                key = (model._meta.app_label, model.__name__, field.name)
                if key not in registered:
                    missing.append(key)
    assert not missing, f"envelope DEK field(s) missing from rotate_keks ENVELOPE_DEK_FIELDS: {missing}"
