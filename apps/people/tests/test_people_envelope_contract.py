"""
Person Stage E contract: the legacy direct-KEK read branch is gone, so a
populated ciphertext with no DEK must FAIL LOUD (field-named ValueError) on
every Person PII property — never silently mis-read. Empty rows still return
None and genuine envelope rows still decrypt.
"""

import pytest

from apps.people import crypto
from apps.people.models import Person

pytestmark = pytest.mark.django_db


def _dekless(person, ct_field, blob):
    Person.objects.filter(pk=person.pk).update(**{ct_field: blob, f"{ct_field}_dek": None})


# --------------------------------------------------- fail-loud, per field
def test_display_name_dekless_raises(person):
    _dekless(person, "display_name_enc", crypto.encrypt_str("legacy"))
    person.refresh_from_db()
    with pytest.raises(ValueError, match="Person.display_name"):
        _ = person.display_name


def test_contact_dekless_raises(person):
    _dekless(person, "contact_enc", crypto.encrypt_json({"phone": "legacy"}))
    person.refresh_from_db()
    with pytest.raises(ValueError, match="Person.contact"):
        _ = person.contact


def test_dob_dekless_raises(person):
    _dekless(person, "dob_enc", crypto.encrypt_str("1970-01-01"))
    person.refresh_from_db()
    with pytest.raises(ValueError, match="Person.dob"):
        _ = person.dob


# ------------------------------------------------------- happy paths intact
def test_empty_returns_none(member):
    p = Person.objects.create(created_in_community=member.community, created_by=member)
    assert p.display_name_enc is None
    assert p.display_name is None
    assert p.contact is None
    assert p.dob is None


def test_envelope_rows_still_read(person):
    person.refresh_from_db()
    assert person.display_name == "Maria Garcia"
    assert person.contact == {"phone": "555-0100", "email": "m@example.test"}
    assert person.dob == "1980-04-12"
