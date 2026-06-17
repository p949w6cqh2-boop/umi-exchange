"""
Person envelope encryption (Stages A–D): per-field round-trips (incl. the JSON
contact field), a real data-migration test proving direct-KEK rows convert and
stay readable, idempotency, reverse, the census command, and KEK rotation.
Mirrors apps/casework/tests/test_casework_envelope.py.
"""

import io

import pytest
from cryptography.fernet import Fernet
from django.apps import apps as django_apps
from django.core.management import call_command

from apps.people import crypto
from apps.people.envelope_backfill import forward_func, reverse_func
from apps.people.models import Person

pytestmark = pytest.mark.django_db


# ----------------------------------------------------- envelope round-trips
def test_display_name_roundtrip(person):
    person.refresh_from_db()
    assert person.display_name == "Maria Garcia"
    assert person.display_name_enc_dek is not None
    assert b"Maria" not in bytes(person.display_name_enc)


def test_contact_json_roundtrip(person):
    person.refresh_from_db()
    assert person.contact == {"phone": "555-0100", "email": "m@example.test"}
    assert person.contact_enc_dek is not None
    assert b"555-0100" not in bytes(person.contact_enc)


def test_dob_roundtrip(person):
    person.refresh_from_db()
    assert person.dob == "1980-04-12"
    assert person.dob_enc_dek is not None


def test_each_field_gets_its_own_dek(person):
    person.refresh_from_db()
    deks = {bytes(person.display_name_enc_dek), bytes(person.contact_enc_dek), bytes(person.dob_enc_dek)}
    assert len(deks) == 3  # distinct per-field DEKs


def test_setter_rejects_bytes(person):
    with pytest.raises(TypeError):
        person.display_name = b"pre-encrypted"
    with pytest.raises(TypeError):
        person.dob = b"pre-encrypted"


def test_clearing_nulls_both_columns(person):
    person.contact = None
    person.display_name = None
    person.save(update_fields=["contact_enc", "contact_enc_dek", "display_name_enc", "display_name_enc_dek"])
    person.refresh_from_db()
    assert person.contact_enc is None and person.contact_enc_dek is None
    assert person.display_name is None


# ------------------------------------------------- the data-migration proof
def _seed_legacy(member, name, contact, dob):
    """A Person written the old way: direct-KEK ciphertext, NULL DEKs."""
    p = Person.objects.create(created_in_community=member.community, created_by=member)
    Person.objects.filter(pk=p.pk).update(
        display_name_enc=crypto.encrypt_str(name),
        display_name_enc_dek=None,
        contact_enc=crypto.encrypt_json(contact),
        contact_enc_dek=None,
        dob_enc=crypto.encrypt_str(dob),
        dob_enc_dek=None,
    )
    return p


def test_data_migration_converts_direct_kek_rows(member):
    p = _seed_legacy(member, "Legacy Name", {"phone": "111"}, "1970-01-01")
    p.refresh_from_db()
    assert p.display_name_enc_dek is None and p.contact_enc_dek is None and p.dob_enc_dek is None

    forward_func(django_apps)  # the real migration logic

    p.refresh_from_db()
    assert p.display_name_enc_dek and p.display_name == "Legacy Name"
    assert p.contact_enc_dek and p.contact == {"phone": "111"}
    assert p.dob_enc_dek and p.dob == "1970-01-01"


def test_data_migration_is_idempotent(member):
    p = _seed_legacy(member, "Once", {"a": 1}, "2000-02-02")
    forward_func(django_apps)
    p.refresh_from_db()
    snap = (bytes(p.display_name_enc), bytes(p.display_name_enc_dek), bytes(p.contact_enc), bytes(p.contact_enc_dek))
    forward_func(django_apps)  # second run = no-op
    p.refresh_from_db()
    assert (
        bytes(p.display_name_enc),
        bytes(p.display_name_enc_dek),
        bytes(p.contact_enc),
        bytes(p.contact_enc_dek),
    ) == snap
    assert p.display_name == "Once" and p.contact == {"a": 1}


def test_reverse_migration_restores_direct_kek(member):
    p = _seed_legacy(member, "Roundtrip", {"x": "y"}, "1990-09-09")
    forward_func(django_apps)
    p.refresh_from_db()
    assert p.display_name_enc_dek is not None
    reverse_func(django_apps)
    p.refresh_from_db()
    assert p.display_name_enc_dek is None and p.contact_enc_dek is None
    assert crypto.decrypt_str(p.display_name_enc) == "Roundtrip"
    assert crypto.decrypt_json(p.contact_enc) == {"x": "y"}
    # Post-Stage-E the property no longer reads legacy: a DEK-less ciphertext
    # fails loud rather than silently decrypting.
    with pytest.raises(ValueError):
        _ = p.display_name


def test_census_command_reports_state(member, person):
    _seed_legacy(member, "Legacy One", {"p": 1}, "1960-06-06")  # legacy row
    out = io.StringIO()
    call_command("people_envelope_status", stdout=out)
    text = out.getvalue()
    assert "Person.display_name_enc:" in text
    assert "legacy=1" in text
    assert "envelope=1" in text  # the `person` fixture row


# ------------------------------------------------------------ KEK rotation
def test_rotation_rewraps_person_deks(person, settings):
    old_key = settings.ENCRYPTION_KEY
    person.refresh_from_db()
    old_wrap = bytes(person.display_name_enc_dek)

    new_key = Fernet.generate_key().decode()
    settings.ENCRYPTION_KEYS = [new_key, old_key]
    call_command("rotate_keks")
    person.refresh_from_db()
    assert bytes(person.display_name_enc_dek) != old_wrap

    settings.ENCRYPTION_KEYS = [new_key]  # retire old KEK
    assert person.display_name == "Maria Garcia"  # survives rotation
    assert person.contact == {"phone": "555-0100", "email": "m@example.test"}
